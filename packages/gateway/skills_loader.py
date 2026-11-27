"""M07 创世种子与工作区技能加载器（渐进式加载：平时仅驻留极简 SkillManifest，按需读取 SKILL.md 与 handler）."""

from __future__ import annotations

import importlib.util
import pathlib
from types import ModuleType
from typing import Any, Callable

import yaml

from packages.core.contracts import SkillManifest, SkillStatus, TaskEnvelope

SkillHandlerFn = Callable[[TaskEnvelope, dict[str, Any]], dict[str, Any]]


class SkillRegistry:
    """扫描 `workspace/skills/*/manifest.yaml` 的标准技能注册表。"""

    def __init__(self, skills_root: pathlib.Path | str | None = None) -> None:
        default_root = pathlib.Path(__file__).resolve().parents[2] / "workspace" / "skills"
        self.skills_root = pathlib.Path(skills_root) if skills_root is not None else default_root
        self._manifests: dict[str, SkillManifest] = {}
        self._dirs: dict[str, pathlib.Path] = {}
        self._handlers: dict[str, SkillHandlerFn] = {}
        self.reload()

    def reload(self) -> list[SkillManifest]:
        self._manifests.clear()
        self._dirs.clear()
        self._handlers.clear()
        if not self.skills_root.exists():
            return []

        for manifest_path in sorted(self.skills_root.glob("*/manifest.yaml")):
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            manifest = SkillManifest.model_validate(raw)
            self._manifests[manifest.skill_id] = manifest
            self._dirs[manifest.skill_id] = manifest_path.parent
        return self.list_manifests()

    def list_manifests(self, *, active_only: bool = False) -> list[SkillManifest]:
        items = list(self._manifests.values())
        if active_only:
            items = [m for m in items if m.status == SkillStatus.ACTIVE]
        return items

    def get_manifest(self, skill_id: str) -> SkillManifest | None:
        return self._manifests.get(skill_id)

    def read_skill_markdown(self, skill_id: str) -> str:
        """渐进式披露：仅在查看详情或执行需要时才读取完整 SKILL.md。"""
        skill_dir = self._dirs.get(skill_id)
        if skill_dir is None:
            raise KeyError(f"未找到技能: {skill_id}")
        md_path = skill_dir / "SKILL.md"
        return md_path.read_text(encoding="utf-8") if md_path.exists() else ""

    def load_handler(self, skill_id: str) -> SkillHandlerFn:
        if skill_id in self._handlers:
            return self._handlers[skill_id]
        skill_dir = self._dirs.get(skill_id)
        if skill_dir is None:
            raise KeyError(f"未找到技能目录: {skill_id}")
        handler_path = skill_dir / "handler.py"
        if not handler_path.exists():
            raise FileNotFoundError(f"技能 {skill_id} 缺少可执行入口 handler.py")

        mod_name = f"huiqiao_skill_{skill_id.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(mod_name, handler_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载技能模块: {handler_path}")
        module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fn = getattr(module, "execute", None)
        if not callable(fn):
            raise AttributeError(f"技能 {skill_id}/handler.py 必须提供可调用的 execute(envelope, state)")
        self._handlers[skill_id] = fn
        return fn

    def execute_skill(
        self,
        skill_id: str,
        envelope: TaskEnvelope,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fn = self.load_handler(skill_id)
        return fn(envelope, state if state is not None else {})
