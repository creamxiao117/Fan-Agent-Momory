"""MCP 权限与路径策略：路径防逃逸 / platform 白名单 / 候选 type 白名单"""

from pathlib import Path

from common.config import HubConfig

AUTHORITY_DIRS = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "experience",
    "libs",
    "retro",
    "blueprints",
)
CANDIDATE_TYPES = {"exp", "note", "project"}


class PolicyError(ValueError):
    """策略违规；code 对应用户可见的稳定错误码"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def resolve_rel(root: Path, rel: str) -> Path:
    """相对中枢根解析路径；越界抛 PolicyError(path_escape)"""
    root_r = root.resolve()
    p = (root / rel).resolve()
    try:
        p.relative_to(root_r)
    except ValueError:
        raise PolicyError("path_escape", f"路径越界: {rel}") from None
    return p


def resolve_slug(root: Path, slug: str) -> Path:
    """slug/相对路径 → 权威目录唯一卡片路径。

    - 含 '/' 或 .md 后缀 → 按相对路径解析（越权或不存在时报 not_found）
    - 纯 slug → 在 AUTHORITY_DIRS 下找唯一 {slug}.md
    """
    if "/" in slug or slug.endswith(".md"):
        p = resolve_rel(root, slug)
        if not p.exists():
            raise FileNotFoundError(f"not_found: {slug}")
        return p
    name = f"{slug}.md"
    hits = [root / sub / name for sub in AUTHORITY_DIRS if (root / sub / name).exists()]
    if len(hits) > 1:
        raise PolicyError("ambiguous", f"slug 多命中: {slug}")
    if not hits:
        raise FileNotFoundError(f"not_found: {slug}")
    return hits[0]


def allowed_platforms(root: Path, extra: tuple[str, ...] = ()) -> set[str]:
    """hub.config.yaml platforms 键 ∪ 显式 extra"""
    return set(HubConfig.load(root).platforms) | set(extra)


def assert_candidate_type(type_: str) -> str:
    """候选卡类型白名单；非法抛 PolicyError(type_forbidden)"""
    if type_ not in CANDIDATE_TYPES:
        raise PolicyError("type_forbidden", f"候选 type 不允许: {type_}")
    return type_
