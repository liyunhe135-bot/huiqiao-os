"""汇桥 OS 乐高积木动态注册、热插拔与自动降级加载器（BrickRegistry · 统一兼容版）."""

from __future__ import annotations

import importlib
import pathlib
from dataclasses import dataclass
from typing import Any

import yaml

from packages.core.contracts import CONTRACT_VERSION, BrickLayer, BrickManifest
from packages.core.errors import BrickNotFoundError, BrickRegistryError, ErrorCode
from packages.core.interfaces import (
    BrickProtocol,
    LLMGatewayProtocol,
    MemoryStoreProtocol,
    PolicyHookProtocol,
    RouterProtocol,
    SandboxProtocol,
    WorkerProtocol,
)

LAYER_PROTOCOLS: dict[BrickLayer, type] = {
    BrickLayer.ROUTER: RouterProtocol,
    BrickLayer.LLM_GATEWAY: LLMGatewayProtocol,
    BrickLayer.WORKER: WorkerProtocol,
    BrickLayer.SANDBOX: SandboxProtocol,
    BrickLayer.MEMORY: MemoryStoreProtocol,
    BrickLayer.GOVERNANCE: PolicyHookProtocol,
}


class NullBrick:
    """标准占位积木：在对应槽位尚未接入真实实现时提供清晰体检状态。"""

    def __init__(self, **kwargs: Any) -> None:
        self.config = kwargs

    def healthcheck(self) -> bool:
        return True


@dataclass
class RegisteredSlot:
    layer: BrickLayer
    active_name: str
    manifests: dict[str, BrickManifest]
    instance: Any | None = None
    active_manifest: BrickManifest | None = None
    used_fallback: bool = False


class BrickRegistry:
    """乐高积木槽位注册中心：同时支持按层槽位（resolve/hot_swap）与按名装配（load/swap）。"""

    def __init__(
        self,
        manifests: list[BrickManifest] | None = None,
        *,
        expected_contract_version: str = CONTRACT_VERSION,
    ) -> None:
        self.expected_contract_version = expected_contract_version
        self._slots: dict[BrickLayer, RegisteredSlot] = {}
        self._by_name: dict[str, BrickManifest] = {}
        self._name_instances: dict[str, Any] = {}
        self.degraded: set[str] = set()

        if manifests:
            for m in manifests:
                key = m.name or m.brick_id
                self._by_name[key] = m
                self.register_manifest(key, m, set_active=True)

    @classmethod
    def from_yaml(
        cls,
        yaml_path: pathlib.Path | str,
        *,
        expected_contract_version: str = CONTRACT_VERSION,
    ) -> BrickRegistry:
        path = pathlib.Path(yaml_path)
        if not path.exists():
            raise BrickRegistryError(
                ErrorCode.BRICK_NOT_FOUND,
                f"未找到积木装配文件: {path}",
                {"path": str(path)},
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        schema_ver = raw.get("schema_version", CONTRACT_VERSION)
        if schema_ver != expected_contract_version:
            raise BrickRegistryError(
                ErrorCode.BRICK_CONTRACT_MISMATCH,
                f"bricks.yaml schema_version 不匹配: 期望 {expected_contract_version}，实际 {schema_ver}",
            )

        registry = cls(expected_contract_version=expected_contract_version)

        # 兼容格式 1：扁平 bricks 列表（M00 CLI 与 test_registry 使用）
        for item in raw.get("bricks", []) or []:
            manifest = BrickManifest(**item)
            key = manifest.name or manifest.brick_id
            registry._by_name[key] = manifest
            if manifest.layer not in registry._slots:
                registry.register_manifest(key, manifest, set_active=True)
            else:
                registry.register_manifest(key, manifest, set_active=False)

        # 兼容格式 2：分层 slots 字典（热插拔多候选槽位）
        slots_data = raw.get("slots", {}) or {}
        for slot_key, slot_cfg in slots_data.items():
            layer = BrickLayer(slot_key)
            active_name = slot_cfg.get("active", "")
            bricks_raw = slot_cfg.get("bricks", {}) or {}
            manifests = {name: BrickManifest(**cfg) for name, cfg in bricks_raw.items()}
            for name, manifest in manifests.items():
                registry._validate_manifest(manifest, expected_layer=layer)
                if name not in registry._by_name:
                    registry._by_name[name] = manifest
            registry._slots[layer] = RegisteredSlot(
                layer=layer,
                active_name=active_name,
                manifests=manifests,
            )
        return registry

    def register_manifest(
        self,
        name: str,
        manifest: BrickManifest,
        *,
        set_active: bool = False,
    ) -> None:
        self._validate_manifest(manifest, expected_layer=manifest.layer)
        self._by_name[name] = manifest
        slot = self._slots.get(manifest.layer)
        if slot is None:
            slot = RegisteredSlot(
                layer=manifest.layer,
                active_name=name,
                manifests={name: manifest},
            )
            self._slots[manifest.layer] = slot
        else:
            slot.manifests[name] = manifest
            if set_active:
                slot.active_name = name
                slot.instance = None
                slot.active_manifest = None
                slot.used_fallback = False

    def _validate_manifest(
        self,
        manifest: BrickManifest,
        *,
        expected_layer: BrickLayer,
    ) -> None:
        if manifest.contract_version != self.expected_contract_version:
            raise BrickRegistryError(
                ErrorCode.BRICK_CONTRACT_MISMATCH,
                (
                    f"积木 {manifest.brick_id} 契约版本不匹配: "
                    f"期望 {self.expected_contract_version}，实际 {manifest.contract_version}"
                ),
                {"brick_id": manifest.brick_id},
            )
        if manifest.layer != expected_layer:
            raise BrickRegistryError(
                ErrorCode.CONTRACT_VIOLATION,
                f"积木 {manifest.brick_id} 声明层 {manifest.layer.value} 与槽位 {expected_layer.value} 不一致",
            )

    @staticmethod
    def _import_and_build(entrypoint: str, config: dict[str, Any]) -> Any:
        module_name, attr_name = entrypoint.split(":", 1)
        module = importlib.import_module(module_name)
        cls_or_factory = getattr(module, attr_name)
        return cls_or_factory(**config)

    def _instantiate(self, manifest: BrickManifest, *, strict_protocol: bool = True) -> Any:
        try:
            instance = self._import_and_build(manifest.entrypoint, manifest.config)
        except Exception as exc:
            raise BrickRegistryError(
                ErrorCode.BRICK_LOAD_FAILED,
                f"加载积木 {manifest.brick_id} ({manifest.entrypoint}) 失败: {exc}",
                {"brick_id": manifest.brick_id, "entrypoint": manifest.entrypoint},
            ) from exc

        if strict_protocol:
            if not isinstance(instance, BrickProtocol):
                raise BrickRegistryError(
                    ErrorCode.CONTRACT_VIOLATION,
                    f"积木 {manifest.brick_id} 缺少 healthcheck() 协议方法",
                )
            if not isinstance(instance, NullBrick):
                proto = LAYER_PROTOCOLS.get(manifest.layer)
                if proto is not None and not isinstance(instance, proto):
                    raise BrickRegistryError(
                        ErrorCode.CONTRACT_VIOLATION,
                        f"积木 {manifest.brick_id} 未实现层 {manifest.layer.value} 所需协议 {proto.__name__}",
                    )
            health_fn = getattr(instance, manifest.healthcheck, None)
            if not callable(health_fn) or not bool(health_fn()):
                raise BrickRegistryError(
                    ErrorCode.BRICK_UNHEALTHY,
                    f"积木 {manifest.brick_id} 健康检查未通过",
                    {"brick_id": manifest.brick_id},
                )
        else:
            health_fn = getattr(instance, manifest.healthcheck, None)
            if callable(health_fn) and not bool(health_fn()):
                raise BrickRegistryError(
                    ErrorCode.BRICK_UNHEALTHY,
                    f"积木 {manifest.brick_id} 健康检查未通过",
                    {"brick_id": manifest.brick_id},
                )
        return instance

    # --- 按名装配接口（兼容 test_registry / M00 CLI） ---
    def load(self, name: str, *, force_reload: bool = False) -> Any:
        if name not in self._by_name:
            raise BrickNotFoundError(f"未注册积木: {name}", {"name": name})
        if name in self._name_instances and not force_reload:
            return self._name_instances[name]

        manifest = self._by_name[name]
        try:
            inst = self._instantiate(manifest, strict_protocol=False)
            self._name_instances[name] = inst
            self.degraded.discard(name)
            return inst
        except BrickRegistryError:
            if manifest.fallback_impl:
                try:
                    inst = self._import_and_build(manifest.fallback_impl, manifest.config)
                    self._name_instances[name] = inst
                    self.degraded.add(name)
                    return inst
                except Exception as exc:
                    raise BrickNotFoundError(
                        f"积木 {name} 主实现与 fallback_impl 均加载失败: {exc}"
                    ) from exc
            raise

    def swap(self, name: str, new_impl: str) -> Any:
        """按名热替换指定积木实现路径并刷新缓存。"""
        if name not in self._by_name:
            raise BrickNotFoundError(f"热替换失败：未注册积木 '{name}'")
        old = self._by_name[name]
        updated = old.model_copy(update={"entrypoint": new_impl, "impl": new_impl})
        inst = self._instantiate(updated, strict_protocol=False)
        self._by_name[name] = updated
        self._name_instances[name] = inst
        self.degraded.discard(name)
        return inst

    # --- 按层槽位装配接口（强协议校验 + 热替换 + 自动降级） ---
    def resolve(
        self,
        layer: BrickLayer,
        *,
        strict_protocol: bool = True,
        force_reload: bool = False,
    ) -> Any:
        slot = self._slots.get(layer)
        if slot is None:
            raise BrickRegistryError(
                ErrorCode.BRICK_NOT_FOUND,
                f"未注册积木槽位: {layer.value}",
            )
        if slot.instance is not None and not force_reload:
            return slot.instance

        primary = slot.manifests.get(slot.active_name)
        if primary is None:
            raise BrickRegistryError(
                ErrorCode.BRICK_NOT_FOUND,
                f"槽位 {layer.value} 找不到活跃积木 '{slot.active_name}'",
            )

        try:
            inst = self._instantiate(primary, strict_protocol=strict_protocol)
            slot.instance = inst
            slot.active_manifest = primary
            slot.used_fallback = False
            return inst
        except BrickRegistryError:
            if primary.fallback_brick and primary.fallback_brick in slot.manifests:
                fb = slot.manifests[primary.fallback_brick]
                inst = self._instantiate(fb, strict_protocol=strict_protocol)
                slot.instance = inst
                slot.active_manifest = fb
                slot.used_fallback = True
                return inst
            raise

    def hot_swap(
        self,
        layer: BrickLayer,
        target_name: str,
        *,
        strict_protocol: bool = True,
    ) -> Any:
        slot = self._slots.get(layer)
        if slot is None or target_name not in slot.manifests:
            raise BrickRegistryError(
                ErrorCode.BRICK_NOT_FOUND,
                f"热替换失败：槽位 {layer.value} 不存在积木 '{target_name}'",
            )
        prev_name = slot.active_name
        prev_inst = slot.instance
        prev_manifest = slot.active_manifest
        prev_fb = slot.used_fallback

        slot.active_name = target_name
        slot.instance = None
        try:
            return self.resolve(layer, strict_protocol=strict_protocol, force_reload=True)
        except Exception:
            slot.active_name = prev_name
            slot.instance = prev_inst
            slot.active_manifest = prev_manifest
            slot.used_fallback = prev_fb
            raise

    def health_report(self) -> dict[str, Any]:
        """输出融合体检报告：同时包含汇总指标（ok/degraded/failed/total）与按层明细。"""
        ok_names: list[str] = []
        degraded_names: list[str] = []
        failed_items: list[dict[str, str]] = []

        # 1. 按扁平注册名体检（仅统计 enabled=True 的正式/mock积木）
        enabled_named = [(k, m) for k, m in self._by_name.items() if m.enabled]
        for name, _manifest in enabled_named:
            try:
                self.load(name)
                if name in self.degraded:
                    degraded_names.append(name)
                else:
                    ok_names.append(name)
            except Exception as exc:  # noqa: BLE001
                failed_items.append({"name": name, "error": str(exc)})

        report: dict[str, Any] = {
            "total": len(enabled_named),
            "ok": ok_names,
            "degraded": degraded_names,
            "failed": failed_items,
        }

        # 2. 按层槽位明细
        for layer, slot in self._slots.items():
            active = slot.manifests.get(slot.active_name)
            enabled = bool(active.enabled) if active else False
            status = "standby"
            if enabled:
                try:
                    self.resolve(layer, strict_protocol=True)
                    status = "fallback_healthy" if slot.used_fallback else "healthy"
                except BrickRegistryError as exc:
                    status = f"error:{exc.code.value}"
            report[layer.value] = {
                "active_name": slot.active_name,
                "brick_id": slot.active_manifest.brick_id
                if slot.active_manifest
                else (active.brick_id if active else None),
                "enabled": enabled,
                "used_fallback": slot.used_fallback,
                "status": status,
                "registered_count": len(slot.manifests),
            }
        return report
