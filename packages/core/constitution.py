"""C00 众生和谐增上宪章加载器与增上四问审查内核（M00 Core）."""

from __future__ import annotations

import hashlib
import pathlib
import re
from dataclasses import dataclass

from packages.core.contracts import UpliftAuditResult
from packages.core.errors import ConstitutionError, ErrorCode

DEFAULT_CONSTITUTION_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "workspace" / "CONSTITUTION.md"
)

_DIGEST_PATTERN = re.compile(
    r"<!--\s*COMPACT_DIGEST_START\s*-->(.*?)<!--\s*COMPACT_DIGEST_END\s*-->",
    re.DOTALL,
)

REQUIRED_AXIOM_MARKERS = ("A1", "A2", "A3", "A4", "A5")


@dataclass(frozen=True)
class LoadedConstitution:
    """已加载并验真的 C00 宪章快照。"""

    path: pathlib.Path
    full_text: str
    compact_digest: str
    axiom_markers_present: tuple[str, ...]

    def as_system_prefix(self) -> str:
        """用于上下文前缀缓存锁与压缩后强制重注的精炼前缀块。"""
        return self.compact_digest

    @property
    def sha256(self) -> str:
        """当前宪章正文的确定性 SHA-256 指纹（供网关与终端健康核验）。"""
        return hashlib.sha256(self.full_text.encode("utf-8")).hexdigest()

    @property
    def version(self) -> str:
        return "huiqiao-constitution/v1.0"


def load_constitution(path: pathlib.Path | str | None = None) -> LoadedConstitution:
    """读取并校验 workspace/CONSTITUTION.md，缺失或核心公理不完整时显式报错。"""
    target = pathlib.Path(path) if path is not None else DEFAULT_CONSTITUTION_PATH
    if not target.exists():
        raise ConstitutionError(
            ErrorCode.CONSTITUTION_MISSING,
            f"未找到最高宪章文件: {target}",
            {"path": str(target)},
        )

    text = target.read_text(encoding="utf-8").strip()
    if not text:
        raise ConstitutionError(
            ErrorCode.CONSTITUTION_MISSING,
            f"宪章文件为空: {target}",
            {"path": str(target)},
        )

    present = tuple(m for m in REQUIRED_AXIOM_MARKERS if m in text)
    if len(present) < len(REQUIRED_AXIOM_MARKERS):
        missing = [m for m in REQUIRED_AXIOM_MARKERS if m not in present]
        raise ConstitutionError(
            ErrorCode.CONSTITUTION_REJECTED,
            f"宪章缺少核心公理标记: {missing}",
            {"missing_axioms": missing},
        )

    match = _DIGEST_PATTERN.search(text)
    if match:
        digest = match.group(1).strip()
    else:
        # 优雅兜底：无显式标记时取前 12 行作为紧凑摘要，不僵化崩溃
        digest = "\n".join(text.splitlines()[:12]).strip()

    return LoadedConstitution(
        path=target,
        full_text=text,
        compact_digest=digest,
        axiom_markers_present=present,
    )


def evaluate_uplift_audit(
    *,
    preserves_human_agency: bool,
    no_harm_or_lockin: bool,
    enables_uplift_and_accessibility: bool,
    transparent_and_reversible: bool,
    rationale: str = "",
    improvement_suggestions: list[str] | None = None,
) -> UpliftAuditResult:
    """执行 C00 增上四问一票否决判定（任何一项底线不通过即否决）。"""
    passed = all(
        (
            preserves_human_agency,
            no_harm_or_lockin,
            enables_uplift_and_accessibility,
            transparent_and_reversible,
        )
    )
    reasons: list[str] = []
    if not preserves_human_agency:
        reasons.append("违背 A1: 削弱人类主体性或存在人矿化倾向")
    if not no_harm_or_lockin:
        reasons.append("违背 A2/A4: 存在黑盒锁死、去技能化或外部性伤害风险")
    if not enables_uplift_and_accessibility:
        reasons.append("违背 A3: 不利于强扶弱增上或普惠赋能")
    if not transparent_and_reversible:
        reasons.append("违背透明可逆底线: 不可审阅或不可一键回滚")

    final_rationale = rationale.strip()
    if reasons:
        joined = "；".join(reasons)
        final_rationale = f"{final_rationale}（拦截原因：{joined}）" if final_rationale else joined

    return UpliftAuditResult(
        passed=passed,
        preserves_human_agency=preserves_human_agency,
        no_harm_or_lockin=no_harm_or_lockin,
        enables_uplift_and_accessibility=enables_uplift_and_accessibility,
        transparent_and_reversible=transparent_and_reversible,
        rationale=final_rationale or "通过 C00 增上四问审查",
        improvement_suggestions=improvement_suggestions or [],
    )
