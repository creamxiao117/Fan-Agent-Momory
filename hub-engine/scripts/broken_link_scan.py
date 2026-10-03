"""断链 Junction 扫描/清理（**常驻工具**，非一次性脚本）。

用法：`python -m scripts.broken_link_scan`（只报）｜`--apply`（清理）。


**为什么值得常驻**：客户端技能目录普遍是 **Junction 聚合多来源**（实测 76 个活联接指向
`.agents` / `.bailian` / `.cc-switch` / SkillHub 等外部仓）。外部仓一改名/移动 ⇒ **断链**，
而**客户端不会报错、只会静默跳过** ⇒ 断链可以长期潜伏（实测 33 处）。
删它**没有信息损失**（目标本来就不存在），且**可证明**（先验证目标不存在才动手）。

安全要点：移除 Junction 必须用 `cmd /c rmdir`（只删链接本身）。
PowerShell 的 `Remove-Item` 在部分版本会**穿透删掉目标目录的内容**。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HUB = REPO / "AgentMemoryHub"


def junctions(skills_dir: Path) -> list[Path]:
    out: list[Path] = []
    if not skills_dir.is_dir():
        return out
    for child in skills_dir.iterdir():
        try:
            # ⚠️ 不能要求 `child.is_dir()`：**断链 Junction 的 is_dir() 返回 False**
            # （目标不存在 ⇒ 目录语义不成立）—— 先前正是因此整类漏检 28 个。
            # 判据只能是 lstat 上的 reparse point 属性。
            if child.is_symlink() or _is_junction(child):
                out.append(child)
        except OSError:
            continue
    return out


def _is_junction(p: Path) -> bool:
    """Windows junction 在 `os.path.islink` 上为 False，须看 reparse point 属性。"""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return bool(getattr(st, "st_reparse_tag", 0)) or bool(st.st_file_attributes & 0x400)  # type: ignore[attr-defined]


def target_of(p: Path) -> str:
    try:
        r = subprocess.run(
            ["cmd", "/c", "dir", "/al", str(p.parent)],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="ignore",
        )
        for line in r.stdout.splitlines():
            if f"] {p.name} " in line or line.strip().endswith(p.name):
                parts = line.split("]")
                if len(parts) > 1:
                    return parts[1].strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        return os.readlink(p)
    except OSError:
        return "?"


def main(argv: list[str] | None = None) -> int:
    apply = "--apply" in (argv or sys.argv[1:])
    caps = json.loads((HUB / "system" / "capabilities.json").read_text(encoding="utf-8"))
    broken: list[dict] = []
    ok = 0
    for plat, info in (caps.get("skills") or {}).items():
        d = info.get("skills_dir")
        if not d:
            continue
        root = Path(d)
        for link in junctions(root):
            tgt = target_of(link)
            # 目标不存在（且不是"读不到 target"）⇒ 断链
            alive = tgt not in {"?", ""} and Path(tgt).exists()
            if alive:
                ok += 1
                continue
            broken.append({"platform": plat, "link": str(link), "target": tgt})

    print(f"扫描完成：**活的 Junction {ok} 个**；**断链 {len(broken)} 个**\n")
    for b in broken:
        print(f"  [{b['platform']:10s}] {b['link'].replace(str(Path.home()), '~')}")
        print(f"                  → 目标不存在：{b['target']}")

    manifest = HUB / ".sync" / "state" / "broken_junctions_removed.json"
    if not apply:
        print(f"\n（未执行移除。加 --apply 才会动手；会写下清单到 {manifest}）")
        return 0

    removed = []
    for b in broken:
        link = Path(b["link"])
        if not link.exists() and not os.path.lexists(link):
            continue
        # **必须用 rmdir**：Remove-Item 可能穿透删目标内容
        r = subprocess.run(["cmd", "/c", "rmdir", str(link)], capture_output=True, text=True, errors="ignore")
        gone = not os.path.lexists(link)
        removed.append({**b, "rc": r.returncode, "removed": gone})
        flag = "✅" if gone else "❌"
        print(f"  {flag} rmdir {link.name}（rc={r.returncode}）{'' if gone else ' :: ' + r.stderr.strip()[:80]}")

    manifest.write_text(json.dumps(removed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已移除 {sum(1 for r in removed if r['removed'])}/{len(removed)}；清单：{manifest}")
    print("注：Junction 只删链接，**目标目录未被触碰**（rmdir 语义）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
