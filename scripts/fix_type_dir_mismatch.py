# @version V1.0 / 2026-09-18 / Hermes / 修复卡 type↔目录不一致 + 跨目录去重
import shutil
from pathlib import Path

HUB = Path(__file__).resolve().parents[1] / "AgentMemoryHub"
DIR2TYPE = {
    "rules": "rule",
    "blueprints": "blueprint",
    "methodology": "methodology",
    "projects": "project",
    "longterm": "longterm",
    "experience": "exp",
}
DUP = [
    ("librecad-cad-application-architecture-blueprint", "experience", "blueprints"),
    ("skillhub-tool-to-skill-registration-workflow", "experience", "methodology"),
]


def fix(path: Path, want: str) -> str:
    """把 frontmatter 里的 type 改成 want；返回 '改' / '插' / ''（已一致）。"""
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("\n---", 1)
    head = parts[0]
    for line in head.splitlines():
        if line.startswith("type:"):
            cur = line.split(":", 1)[1].strip()
            if cur == want:
                return ""
            return "改" if _sub(path, raw, line, want) else ""
    return "插" if _ins(path, raw, want) else ""


def _sub(path: Path, raw: str, line: str, want: str) -> bool:
    new = raw.replace(line, f"type: {want}", 1)
    path.write_text(new, encoding="utf-8")
    return True


def _ins(path: Path, raw: str, want: str) -> bool:
    new = raw.replace("---", f"---\ntype: {want}", 1)
    path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    arc = HUB / "archive" / "experience"
    arc.mkdir(parents=True, exist_ok=True)
    for name, drop, keep in DUP:
        src = HUB / drop / f"{name}.md"
        if src.exists():
            shutil.move(str(src), str(arc / f"{name}.md"))
            print(f"  去重: {drop}/{name} -> archive/experience/  (保留 {keep}/)")
    n = 0
    for d, want in DIR2TYPE.items():
        for p in sorted((HUB / d).glob("*.md")):
            act = fix(p, want)
            if act:
                n += 1
                print(f"  {act} type={want}: {d}/{p.name}")
    print(f"\n对齐 {n} 张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
