# @version V1.0 / 2026-10-02 / pi / 能力实测态扫描（MCP / Skill / CLI）+ 渲染产物 + --check
"""capability_scan —— 各 agent 平台的**能力实测态**扫描（架构重构 M0/Task 4）。

## 为什么要有它

"哪些能力装在哪些 agent 上"此前**没有任何单一真相**：
- 各平台的 MCP 配置散在 `~/.trae-cn/mcp.json`、`~/.codex/config.toml`、pi 的
  `<agent-dir>/mcp.json` 等 6+ 处，**无登记**；
- 唯一一份"清单"是 `methodology/agent-tool-inventory.md`——一张 **2026-08-18 的手写快照卡**，
  按其性质必然过期（本仓"手写枚举→漂移"已复发 3 次：L0 INDEX 枚举行 / `L1_CARDS` / `tier` 覆盖）。

本模块把"实测态"做成**渲染产物**：事实源 = 各平台配置文件与目录本身，
每次扫描按目录签名重算，`--check` 与磁盘不一致即非 0（口径同 `ruff format --check`）。

## 定位（与 Task 17 的分工）

- **实测态**（本模块）：从平台配置/目录**读出来**的事实。
- **声明态**（SkillHub 账本，M2/Task 16）：我们**期望**装什么（含 `deploy_scope`/`install`/`verify`）。
- 两者对账 = M2/Task 17。本模块只负责"实测"这一半，不猜测、不补全。

用法：
    python -m scripts.capability_scan                     # 打印人读报告
    python -m scripts.capability_scan --json              # 打印 JSON（stdout）
    python -m scripts.capability_scan --write             # 写产物（capabilities.json + .md）
    python -m scripts.capability_scan --check             # 与磁盘产物比对（0 一致 / 3 不一致）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tomllib

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.config import platform_meta  # noqa: E402

CST = timezone(timedelta(hours=8))

JSON_NAME = "capabilities.json"
MD_NAME = "capabilities.md"
OUT_DIR_REL = Path("system")

# 技能目录的常见布局：<skills_dir>/<name>/SKILL.md 或 <skills_dir>/*.md / *。（一层子目录）
SKILL_ENTRY = "SKILL.md"
SKILL_MD = "SKILL.md"

# 常驻「发现成本」口径（M2/Task 18）：每个能力**每次会话都要付**的描述 token，无论是否用到。
# `methodology/agent-tool-inventory`（2026-08-18 快照）早已指出这是能力通胀的真成本，
# 但当时**没有任何计量**——这里把它变成产物里的一列数字。
# 口径：token ≈ 字符数 / 4（与 pi 扩展的预算估算同口径）；MCP server 无法在不连接的情况下
# 枚举工具，故只计「server 条目」本身固定开销（实测 pi-mcp-adapter 的代理工具 ~200 token）。


def _skills_dir(info: dict) -> Path | None:
    """平台技能目录（登记在 hub.config.yaml 的 `skills_dir`；HOME 相对路径也支持）。"""
    raw = info.get("skills_dir")
    if not raw:
        return None
    p = Path(str(raw).replace("\\", "/"))
    if not p.is_absolute():
        p = Path.home() / p
    return p


def list_skills(skills_dir: Path) -> list[str]:
    """列技能名：优先 `<dir>/<name>/SKILL.md` 形态，退回一层目录名。"""
    if not skills_dir or not skills_dir.is_dir():
        return []
    out: list[str] = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir():
            if (child / SKILL_ENTRY).is_file() or any(child.glob("*.md")):
                out.append(child.name)
        elif child.suffix == ".md" and child.stem.lower() not in {"readme", "index"}:
            out.append(child.stem)
    return out


def _load_config(path: Path, fmt: str) -> dict:
    """读客户端配置（json/yaml/toml）；失败返回空 dict（不抛，扫描器不该被单个平台拖死）。"""
    try:
        if fmt == "toml":
            with open(path, "rb") as fh:
                return tomllib.load(fh)
        text = path.read_text(encoding="utf-8", errors="ignore")
        if fmt == "yaml":
            import yaml

            return yaml.safe_load(text) or {}
        return json.loads(text)
    except Exception:  # noqa: BLE001 - 坏配置由 platform_healthcheck 报红，这里只跳过
        return {}


def _servers(data: dict) -> dict:
    """从客户端配置里取 mcp server 映射（三种键名都认）。"""
    if not isinstance(data, dict):
        return {}
    for key in ("mcpServers", "mcp_servers", "servers"):
        v = data.get(key)
        if isinstance(v, dict):
            return v
    return {}


def scan_mcp(root: Path) -> dict[str, list[dict]]:
    """各平台的 MCP server 实测态。"""
    out: dict[str, list[dict]] = {}
    for name, info in platform_meta(root)["platforms"].items():
        info = info or {}
        raw = info.get("mcp_config_path")
        if not raw:
            continue
        cfg = Path(str(raw).replace("\\", "/"))
        if not cfg.is_absolute():
            cfg = Path.home() / cfg
        if not cfg.is_file():
            out[name] = []
            continue
        servers = _servers(_load_config(cfg, str(info.get("config_format") or "json").lower()))
        rows = []
        for sname in sorted(servers):
            blk = servers[sname] if isinstance(servers[sname], dict) else {}
            rows.append(
                {
                    "server": sname,
                    "command": str(blk.get("command", ""))[:200],
                    "args_count": len(blk.get("args") or []),
                }
            )
        out[name] = rows
    return out


def scan_skills(root: Path) -> dict[str, dict]:
    """各平台技能实测态（`skills_dir` 未登记的平台记 `skills_dir: null`）。"""
    out: dict[str, dict] = {}
    for name, info in platform_meta(root)["platforms"].items():
        d = _skills_dir(info or {})
        names = list_skills(d) if d else []
        out[name] = {"skills_dir": str(d) if d else None, "count": len(names), "skills": names}
    return out


CHARS_PER_TOKEN = 4
MCP_SERVER_DISCOVERY_TOKENS = 200


def skill_discovery_tokens(skills_dir: Path | None, names: list[str]) -> dict[str, int]:
    """逐技能的常驻成本：只读 `SKILL.md` 的 `description:`（那是唯一被常驻注入的部分）。

    返回 `{技能名: token}`——**逐技能**而不是只给合计，因为「成本太高」的下一步动作是
    「砍掉谁」，只给一个总数是没法行动的（M2/Task 18 修订）。
    """
    if not skills_dir or not names:
        return {}
    out: dict[str, int] = {}
    for name in names:
        f = skills_dir / name / SKILL_MD
        if not f.is_file():
            out[name] = 20  # 无 SKILL.md 的目录按「名字 + 一行」粗算
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")[:4000]
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        out[name] = len(m.group(1) if m else name) // CHARS_PER_TOKEN
    return out


def discovery_cost(root: Path) -> dict[str, dict]:
    """各平台**单会话常驻发现成本**（该平台每次会话必付的 token）——M2/Task 18 的计量入口。

    ⚠️ **不要把各平台加总当成本**：不同平台是不同客户端，各自会话只付各自那一份。
    2026-10-02 实测教训：曾把 7 个平台的求和（8836）当成「每会话成本」并设帽 —— 那个数字
    **不约束任何一次真实会话**（最贵单平台也才 3264），属于「用错误的量做治理」。
    求和量仍然记录（`fleet_tokens`），但**只作库存参考、不设帽**。
    """
    meta = platform_meta(root)["platforms"]
    mcp = scan_mcp(root)
    skills = scan_skills(root)
    out: dict[str, dict] = {}
    for name, info in meta.items():
        d = _skills_dir(info or {})
        per_skill = skill_discovery_tokens(d, skills.get(name, {}).get("skills", []))
        m_tokens = len(mcp.get(name, [])) * MCP_SERVER_DISCOVERY_TOKENS
        out[name] = {
            "skills_tokens": sum(per_skill.values()),
            "mcp_tokens": m_tokens,
            "mcp_servers": len(mcp.get(name, [])),
            "per_session_tokens": sum(per_skill.values()) + m_tokens,
            # 降级候选：最贵的技能在前（超目标时据此裁）
            # 排序必须是**全序**（token 相同再按名字）：否则同分项次序随目录枚举顺序漂移，
            # 会让 `--check` 误报产物不一致（2026-10-02 实测）
            # 输出 **list[list]** 而不是 tuple：JSON 往返会把 tuple 变 list，否则 `--check` 永真
            "top_skills": [[n, t] for n, t in sorted(per_skill.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
        }
    return out


def fleet_tokens(costs: dict[str, dict]) -> int:
    """全平台求和 —— **仅库存参考，不是任何会话的成本**，不得当帽（见 `discovery_cost` docstring）。"""
    return sum(c["per_session_tokens"] for c in costs.values())


def scan_cli() -> dict:
    """本仓可被 agent 调用的 CLI 面（engine 子命令 + 带 __main__ 的脚本）。"""
    engine = _HUB_ENGINE / "engine.py"
    subs: list[str] = []
    if engine.is_file():
        subs = sorted(set(re.findall(r'sub\.add_parser\(\s*"([a-z0-9-]+)"', engine.read_text(encoding="utf-8"))))
    scripts = sorted(
        p.stem
        for p in (_HUB_ENGINE / "scripts").rglob("*.py")
        if "__pycache__" not in p.parts and "__main__" in p.read_text(encoding="utf-8")
    )
    return {"engine_subcommands": subs, "scripts_with_main": scripts}


def scan(root: Path) -> dict:
    """全量扫描（纯读，不写盘）。"""
    return {
        "generated_at": datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "source": "各平台客户端配置 + 技能目录（实测态；事实源即文件本身，非本产物）",
        "mcp": scan_mcp(root),
        "skills": scan_skills(root),
        "cli": scan_cli(),
        "discovery_cost": discovery_cost(root),
        "fleet_tokens": fleet_tokens(discovery_cost(root)),  # 仅库存参考；**不得当帽**
        "totals": {},
    }


def _totals(data: dict, root: Path | None = None) -> dict:
    mcp = sum(len(v) for v in data["mcp"].values())
    skills = sum(v["count"] for v in data["skills"].values())
    registered = len(platform_meta(root)["platforms"]) if root else len(set(data["mcp"]) | set(data["skills"]))
    return {
        "platforms_registered": registered,
        "platforms_with_mcp": len(data["mcp"]),
        "mcp_servers": mcp,
        "skills": skills,
        "engine_subcommands": len(data["cli"]["engine_subcommands"]),
        "scripts_with_main": len(data["cli"]["scripts_with_main"]),
    }


def render_markdown(data: dict) -> str:
    t = data["totals"]
    lines = [
        "# 能力实测态（渲染产物，禁手改）",
        "",
        "> 由 `python -m scripts.capability_scan --write` 生成（架构重构 M0/Task 4）。",
        "> **事实源 = 各平台客户端配置与技能目录本身**，本文件只是它们的投影；",
        "> 与磁盘不一致会被 `--check` 打红（口径同 `ruff format --check`）。",
        "> 声明态（期望装什么、怎么装、怎么卸）在 SkillHub 账本（M2/Task 16），两者对账见 Task 17。",
        "",
        f"- 生成时间：{data['generated_at']}",
        f"- 平台（登记 {t['platforms_registered']} / 有 MCP 配置 {t['platforms_with_mcp']}） · "
        f"MCP server {t['mcp_servers']} 个 · 技能 {t['skills']} 个 · "
        f"CLI 子命令 {t['engine_subcommands']} 个 · 带 `__main__` 脚本 {t['scripts_with_main']} 个",
        "",
        "## MCP server（按平台）",
        "",
        "| 平台 | server | command | args |",
        "| --- | --- | --- | --- |",
    ]
    for plat, rows in data["mcp"].items():
        if not rows:
            lines.append(f"| {plat} | （无） | | |")
        for r in rows:
            lines.append(f"| {plat} | {r['server']} | `{r['command']}` | {r['args_count']} |")
    lines += ["", "## 技能（按平台）", "", "| 平台 | 目录 | 数量 |", "| --- | --- | --- |"]
    for plat, v in data["skills"].items():
        lines.append(f"| {plat} | `{v['skills_dir'] or '（未登记）'}` | {v['count']} |")
    lines += [
        "",
        "## 常驻发现成本（**单会话**必付的 token；M2/Task 18）",
        "",
        "每个平台是一个独立客户端：**它自己的会话只付它自己那一份**。下表按单平台升序列出。",
        "",
        "| 平台 | 技能描述 | MCP server | **单会话合计** |",
        "| --- | --- | --- | --- |",
    ]
    costs = data.get("discovery_cost") or {}
    for plat, c in sorted(costs.items(), key=lambda kv: -kv[1]["per_session_tokens"]):
        lines.append(
            f"| {plat} | {c['skills_tokens']} | {c['mcp_tokens']}（{c['mcp_servers']} 个） | **{c['per_session_tokens']}** |"
        )
    fleet = sum(c["per_session_tokens"] for c in costs.values())
    lines.append("")
    lines.append(
        f"> 全平台求和 **{fleet}**（库存参考，**不是任何会话的成本**，**不设帽**）——"
        "2026-10-02 教训：这个求和曾被当成「每会话成本」设帽，它对真实会话毫无约束。"
    )
    worst = max(costs.items(), key=lambda kv: kv[1]["per_session_tokens"], default=("（无）", {}))
    if worst[1]:
        top = "、".join(f"{n}({t})" for n, t in worst[1].get("top_skills") or [])
        lines.append(
            f"> 最贵单平台：**{worst[0]} {worst[1]['per_session_tokens']} token/会话**"
            + (f"；最贵的技能：{top}" if top else "")
        )
    lines += [
        "",
        "## 本仓 CLI 面",
        "",
        f"- `engine.py` 子命令（{t['engine_subcommands']}）：{', '.join(data['cli']['engine_subcommands'])}",
        f"- 带 `__main__` 的脚本（{t['scripts_with_main']}）：{', '.join(data['cli']['scripts_with_main'])}",
        "",
    ]
    return "\n".join(lines)


def _paths(root: Path) -> tuple[Path, Path]:
    d = root / OUT_DIR_REL
    return d / JSON_NAME, d / MD_NAME


def write_products(root: Path) -> int:
    data = scan(root)
    data["totals"] = _totals(data, root)
    json_path, md_path = _paths(root)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    print(f"[OK] 已渲染 {json_path.name} + {md_path.name}")
    return 0


def check(root: Path) -> list[str]:
    """与磁盘产物比对；返回违规说明（空 = 通过）。"""
    json_path, md_path = _paths(root)
    errs: list[str] = []
    if not md_path.is_file() or not json_path.is_file():
        return [f"产物缺失（先跑 `--write`）：{md_path.name} / {json_path.name}"]
    data = scan(root)
    data["totals"] = _totals(data, root)
    old = json.loads(json_path.read_text(encoding="utf-8"))
    # generated_at 不参与比对（时间必然变）
    for d in (data, old):
        d.pop("generated_at", None)
    if data != old:
        errs.append(f"{json_path.name} 与实测态不一致（配置/目录已变，未重渲）→ 跑 `--write` 修复")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="能力实测态扫描（MCP/Skill/CLI）")
    ap.add_argument("--root", type=Path, default=None, help="中枢根（默认仓库内 AgentMemoryHub）")
    ap.add_argument("--json", action="store_true", help="打印 JSON")
    ap.add_argument("--write", action="store_true", help="写产物")
    ap.add_argument("--check", action="store_true", help="与磁盘产物比对")
    args = ap.parse_args(argv)

    root = args.root or (_HUB_ENGINE.parent / "AgentMemoryHub")
    if args.write:
        return write_products(root)
    if args.check:
        errs = check(root)
        for e in errs:
            print(f"FAIL: {e}")
        if not errs:
            print(f"PASS: {MD_NAME} / {JSON_NAME} 与实测态一致")
        return 3 if errs else 0
    data = scan(root)
    data["totals"] = _totals(data, root)
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
