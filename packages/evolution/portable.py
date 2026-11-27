"""M11 (B09) 高配反哺低配普惠便携技能包导出与防篡改导入（.hqskill.zip）."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import zipfile
from typing import Any

import yaml

from packages.core.contracts import SkillManifest, SkillStatus
from packages.evolution.gates import run_constitution_uplift_gate, run_objective_sandbox_gate
from packages.evolution.models import PortableSkillCard
from packages.sandbox import SandboxManager

_PRIVACY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("personal_path", re.compile(r"[A-Za-z]:\\Users\\[^\\]+|/Users/[^/]+|/home/[^/]+", re.I)),
    ("api_secret", re.compile(r"sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}")),
    ("private_key_pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

_DEFAULT_SMOKE_TEST = (
    "import types\n"
    "from packages.core.contracts import WorkMode\n"
    "out = execute(types.SimpleNamespace(\n"
    "    raw_input='测试普惠便携技能运行样例',\n"
    "    input=types.SimpleNamespace(text='测试普惠便携技能运行样例', attachments=[]),\n"
    "    constraints=types.SimpleNamespace(work_mode=WorkMode.ASK, offline_only=True),\n"
    "    metadata={},\n"
    "), {})\n"
    "assert isinstance(out, dict) and 'summary' in out\n"
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_portable_privacy_hygiene(files: dict[str, str]) -> list[str]:
    """导出普惠包前执行隐私防泄密体检，严禁把本机用户名/路径/API密钥打包分享给他人。"""
    hits: list[str] = []
    for rel_name, text in files.items():
        for label, pat in _PRIVACY_PATTERNS:
            if pat.search(text):
                hits.append(f"PRIVACY_LEAK:{label}:{rel_name}")
    return hits


def _is_safe_zip_member(member_name: str) -> bool:
    """防 Zip-Slip 路径穿越：仅允许相对安全文件名，严禁 '..'、前导 '/' 或盘符。"""
    if not member_name or member_name.startswith(("/", "\\")):
        return False
    if ":" in member_name:
        return False
    parts = pathlib.PurePosixPath(member_name.replace("\\", "/")).parts
    if any(p in ("..", "") for p in parts):
        return False
    return True


def export_portable_skill(
    skill_dir: pathlib.Path | str,
    output_zip: pathlib.Path | str,
    *,
    sandbox: SandboxManager | None = None,
    require_sandbox_verify: bool = True,
) -> PortableSkillCard:
    """将已验收技能打包为低配设备（8GB RAM / CPU-only / 零云端）可直接离线导入运行的 .hqskill.zip。"""
    src = pathlib.Path(skill_dir).resolve()
    manifest_path = src / "manifest.yaml"
    skill_md_path = src / "SKILL.md"
    handler_path = src / "handler.py"
    smoke_path = src / "tests_smoke.py"

    for req_file in (manifest_path, skill_md_path, handler_path):
        if not req_file.exists():
            raise FileNotFoundError(f"导出普惠技能包失败，缺少必备文件: {req_file.name}")

    manifest_raw = manifest_path.read_text(encoding="utf-8")
    manifest_obj = SkillManifest.model_validate(yaml.safe_load(manifest_raw) or {})
    skill_md = skill_md_path.read_text(encoding="utf-8")
    handler_code = handler_path.read_text(encoding="utf-8")
    smoke_code = smoke_path.read_text(encoding="utf-8") if smoke_path.exists() else _DEFAULT_SMOKE_TEST

    bundle_files = {
        "manifest.yaml": manifest_raw,
        "SKILL.md": skill_md,
        "handler.py": handler_code,
        "tests_smoke.py": smoke_code,
    }

    # 1. 导出前强制隐私脱敏体检
    privacy_hits = scan_portable_privacy_hygiene(bundle_files)
    if privacy_hits:
        raise ValueError(f"普惠技能导出被隐私门禁拦截: {', '.join(privacy_hits)}")

    # 2. 导出前强制通过 Gate 2 C00 增上四问审查
    audit = run_constitution_uplift_gate(
        name=manifest_obj.name,
        description=manifest_obj.description,
        manifest_yaml=manifest_raw,
        skill_markdown=skill_md,
        handler_code=handler_code,
        portable_lite_ready=True,
    )
    if not audit.passed:
        raise ValueError(f"普惠技能导出被 C00 宪章否决: {audit.rationale}")

    # 3. 导出前可选在独立 M08 沙箱复验零依赖可运行性
    if require_sandbox_verify:
        g1 = run_objective_sandbox_gate(
            manifest_yaml=manifest_raw,
            skill_markdown=skill_md,
            handler_code=handler_code,
            smoke_test_code=smoke_code,
            sandbox=sandbox,
        )
        if not g1.passed:
            raise ValueError(f"普惠技能导出未通过 Gate 1 沙箱客观验证: {g1.stderr or g1.issues}")

    # 规范化 manifest.yaml 中的 portable_lite_ready 标记
    norm_manifest = manifest_obj.model_copy(
        update={"portable_lite_ready": True, "status": SkillStatus.ACTIVE}
    )
    norm_manifest_yaml = yaml.safe_dump(
        norm_manifest.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )
    bundle_files["manifest.yaml"] = norm_manifest_yaml

    checksums = {
        fname: _sha256_bytes(content.encode("utf-8"))
        for fname, content in sorted(bundle_files.items())
    }
    card = PortableSkillCard(
        skill_id=norm_manifest.skill_id,
        name=norm_manifest.name,
        version=norm_manifest.version,
        description=norm_manifest.description,
        portable_lite_ready=True,
        constitution_attestation=audit,
        file_sha256=checksums,
    )

    out_path = pathlib.Path(output_zip).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, content in sorted(bundle_files.items()):
            zf.writestr(fname, content.encode("utf-8"))
        zf.writestr(
            "PORTABLE_CARD.json",
            json.dumps(card.model_dump(mode="json"), ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return card


def import_portable_skill(
    zip_path: pathlib.Path | str,
    target_skills_dir: pathlib.Path | str,
    *,
    sandbox: SandboxManager | None = None,
    require_dual_gate: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """在接收端（如低配离线电脑）安全校验并导入 .hqskill.zip（防 Zip-Slip + SHA-256 防篡改 + 复跑双闸门）。"""
    archive = pathlib.Path(zip_path).resolve()
    if not archive.exists():
        raise FileNotFoundError(f"未找到普惠技能包: {archive}")

    extracted: dict[str, bytes] = {}
    with zipfile.ZipFile(archive, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not _is_safe_zip_member(info.filename):
                raise ValueError(f"检测到非法 Zip-Slip 路径穿越条目，已安全拒绝: {info.filename}")
            extracted[info.filename] = zf.read(info.filename)

    if "PORTABLE_CARD.json" not in extracted:
        raise ValueError("技能包缺少 PORTABLE_CARD.json 完整性名片，拒绝导入。")

    card = PortableSkillCard.model_validate_json(extracted["PORTABLE_CARD.json"].decode("utf-8"))

    # 1. 全文件 SHA-256 防篡改核验
    for req_name in ("manifest.yaml", "SKILL.md", "handler.py", "tests_smoke.py"):
        if req_name not in extracted or req_name not in card.file_sha256:
            raise ValueError(f"技能包结构不完整，缺少 {req_name}")
        actual_hash = _sha256_bytes(extracted[req_name])
        expected_hash = card.file_sha256[req_name]
        if actual_hash != expected_hash:
            raise ValueError(
                f"SHA-256 完整性核验失败（文件 {req_name} 可能已被篡改）: "
                f"expected={expected_hash[:12]} actual={actual_hash[:12]}"
            )

    manifest_raw = extracted["manifest.yaml"].decode("utf-8")
    skill_md = extracted["SKILL.md"].decode("utf-8")
    handler_code = extracted["handler.py"].decode("utf-8")
    smoke_code = extracted["tests_smoke.py"].decode("utf-8")
    manifest = SkillManifest.model_validate(yaml.safe_load(manifest_raw) or {})

    # 2. 接收端本地零信任复跑双闸门（不盲信外部打包声明）
    gate1_passed = True
    gate2_passed = True
    if require_dual_gate:
        g2 = run_constitution_uplift_gate(
            name=manifest.name,
            description=manifest.description,
            manifest_yaml=manifest_raw,
            skill_markdown=skill_md,
            handler_code=handler_code,
            portable_lite_ready=manifest.portable_lite_ready,
        )
        gate2_passed = g2.passed
        if not g2.passed:
            raise ValueError(f"导入技能未通过本地 C00 增上宪章复审: {g2.rationale}")

        g1 = run_objective_sandbox_gate(
            manifest_yaml=manifest_raw,
            skill_markdown=skill_md,
            handler_code=handler_code,
            smoke_test_code=smoke_code,
            sandbox=sandbox,
        )
        gate1_passed = g1.passed
        if not g1.passed:
            raise ValueError(f"导入技能未通过本地 M08 沙箱冒烟单测: {g1.stderr or g1.issues}")

    # 3. 安全落盘至 target_skills_dir/<skill_id>/
    dest_root = pathlib.Path(target_skills_dir).resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_dir = dest_root / manifest.skill_id
    if dest_dir.exists() and not overwrite:
        raise FileExistsError(f"目标技能已存在 ({manifest.skill_id})，如需覆盖请传入 overwrite=True")
    dest_dir.mkdir(parents=True, exist_ok=True)

    for fname, raw_bytes in extracted.items():
        (dest_dir / fname).write_bytes(raw_bytes)

    return {
        "skill_id": manifest.skill_id,
        "name": manifest.name,
        "version": manifest.version,
        "installed_dir": str(dest_dir),
        "gate1_passed": gate1_passed,
        "gate2_passed": gate2_passed,
        "portable_lite_ready": card.portable_lite_ready,
        "compatibility": card.compatibility,
    }
