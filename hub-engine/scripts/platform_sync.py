# @version V1.0 / 2026-09-15 / Hermes / platforms.yaml → 各平台 MCP 配置单点同步
"""platform_sync.py — 从 system/platforms.yaml 单点同步各平台的 agent-memory-hub MCP 块。

范式（见 system/platforms.yaml 顶部注释）：单点描述 → 单点同步 → 单点监控。
本脚本负责中间那一步：把 platforms.yaml 里每个 `type: mcp` 平台的 launcher 式 MCP 块
写回该平台自己的配置文件，取代"手工改 3 份 mcp.json/config.yaml"（T21 待办 A/1）。

设计要点（都是踩过坑后的选择）
- **默认 dry-run**：不带 --apply 只报告漂移，绝不写盘。
- **保注释/保格式**：绝不整文件 PyYAML/TOML dump。yaml 与 toml 走"定位块 → 只替换该块文本"；
  json 走 load/dump（2 空格缩进），因为 JSON 无注释可保。
- **写前必备份**：--apply 对每个被改文件落 `<file>.bak-<YYYYMMDD-HHMMSS>`。
- **幂等**：路径统一为前斜杠规范化后比较；重复 --apply 第二次必须报 "no change"。
- **资源路径不做"猜测"**：python / launcher / hub-root 全部来自全局段落或参数，平台条目只声明
  自己的 mcp_config_path 与 config_format。

用法
  python hub-engine/scripts/platform_sync.py --root ../AgentMemoryHub            # 只检查漂移
  python hub-engine/scripts/platform_sync.py --root ../AgentMemoryHub --apply    # 写回
  python hub-engine/scripts/platform_sync.py --root ../AgentMemoryHub --platform trae --json
退出码：0 = 一致（或 apply 成功）；1 = 存在漂移（dry-run）；2 = 用法/读取错误；3 = 写入失败。
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml 是中枢引擎既有依赖
    print("需要 PyYAML：pip install pyyaml", file=sys.stderr)
    sys.exit(2)

DEFAULT_HUB_ROOT = Path(__file__).resolve().parents[2]
# hermes 自己的 venv：从家目录推导（换机可用；可用 --python 覆盖）
DEFAULT_PYTHON = str(Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "venv" / "Scripts" / "python.exe")
PLATFORMS_REL = "system/platforms.yaml"
DEFAULT_SERVER_KEY = "agent-memory-hub"
SERVER_KEY_ALIASES = ("agent-memory-hub", "agent_memory_hub")
# 每个格式"由本脚本托管"的块内额外键（其余键一律保留，不做增删）
FORMAT_EXTRAS = {
    "yaml": {"connect_timeout": 60, "enabled": True},
    "json": {"disabled": False},
    "toml": {"type": "stdio", "startup_timeout_sec": 60},
}


def _norm(value) -> str:
    """比较用规范化：反斜杠→斜杠、折叠重复分隔符。"""
    return re.sub(r"/+", "/", str(value).replace("\\", "/"))


def _p(value) -> str:
    """写入用规范形：前斜杠（Windows/POSIX 通用，避免 JSON/TOML/YAML 各自的转义歧义）。"""
    return _norm(value)


def load_platforms(hub_root: Path) -> dict:
    p = hub_root / PLATFORMS_REL
    if not p.is_file():
        print(f"platforms.yaml 不存在：{p}", file=sys.stderr)
        sys.exit(2)
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def resolve_config_path(raw: str) -> Path:
    """平台条目里的 mcp_config_path 允许写成 HOME 相对路径。"""
    p = Path(raw)
    return p if p.is_absolute() else Path.home() / raw


def expected_argv(platform: str, cfg: Path, hub_root: Path, launcher: Path) -> list:
    return [
        _p(launcher),
        "--platform",
        platform,
        "--config",
        _p(cfg),
        "--hub-root",
        _p(hub_root),
        "--heal",
    ]


def expected_block(platform: str, cfg: Path, hub_root: Path, launcher: Path, python: str, fmt: str) -> dict:
    block = {
        "command": _p(python),
        "args": expected_argv(platform, cfg, hub_root, launcher),
    }
    block.update(FORMAT_EXTRAS.get(fmt, {}))
    return block


# ---------------------------------------------------------------- 读：当前块
def _find_server_key(mapping: dict) -> str:
    for key in SERVER_KEY_ALIASES:
        if key in mapping:
            return key
    return ""


def read_current(fmt: str, cfg: Path, server_key: str):
    """返回 (server_key, block|None)。文件不存在/解析失败返回 (server_key, None)。"""
    if not cfg.is_file():
        return server_key, None
    try:
        if fmt == "yaml":
            with open(cfg, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            servers = data.get("mcp_servers") or data.get("mcpServers") or {}
        elif fmt == "toml":
            import tomllib

            with open(cfg, "rb") as fh:
                data = tomllib.load(fh)
            servers = data.get("mcp_servers") or {}
        else:
            with open(cfg, encoding="utf-8") as fh:
                data = json.load(fh)
            servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    except Exception as exc:
        print(f"  解析失败: {cfg.name}: {exc}", file=sys.stderr)
        return server_key, None
    found = _find_server_key(servers)
    return (found or server_key), servers.get(found) if found else None


def block_matches(current, expected: dict) -> bool:
    """只比对受管核心键（command/args）：其余键（enabled/disabled/type/timeout 等）视为平台本地保留，
    不做增删，避免同步动作顺手改掉平台自己的设置。"""
    if not isinstance(current, dict):
        return False
    if _norm(current.get("command", "")) != _norm(expected["command"]):
        return False
    cur_args = [_norm(a) for a in (current.get("args") or [])]
    exp_args = [_norm(a) for a in expected["args"]]
    return cur_args == exp_args


# ---------------------------------------------------------------- 写：三格式各自保格式写回
def _dump_yaml_block(block: dict, indent: int) -> str:
    text = yaml.safe_dump(
        {"agent-memory-hub": block},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )
    pad = " " * indent
    return "".join(pad + line if line.strip() else line for line in text.splitlines(True))


def write_yaml(cfg: Path, server_key: str, block: dict, indent: int) -> None:
    lines = cfg.read_text(encoding="utf-8").splitlines(True)
    rendered = _dump_yaml_block(block, indent).replace("agent-memory-hub:", f"{server_key}:", 1)
    idx = next((i for i, ln in enumerate(lines) if re.match(r"^mcp_servers:\s*$", ln)), None)
    if idx is None:
        cfg.write_text(
            "".join(lines).rstrip("\n") + "\nmcp_servers:\n" + rendered,
            encoding="utf-8",
        )
        return
    start = None
    for i in range(idx + 1, len(lines)):
        if re.match(r"^\S", lines[i]):  # 下一个顶层键 → mcp_servers 段结束
            break
        if re.match(r"^ {2}[^\s].*:\s*$", lines[i]):
            if start is not None:
                break
            start = i
    if start is None:  # mcp_servers 段为空 → 直接插入
        lines.insert(idx + 1, rendered)
        cfg.write_text("".join(lines), encoding="utf-8")
        return
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("    ")):
        end += 1
    lines[start:end] = [rendered]
    cfg.write_text("".join(lines), encoding="utf-8")


def write_toml(cfg: Path, server_key: str, block: dict) -> None:
    text = cfg.read_text(encoding="utf-8")
    header = f"[mcp_servers.{server_key}]"
    block_lines = [
        header,
        f'type = "{block.get("type", "stdio")}"',
        f"command = '{block['command']}'",
        "args = [" + ", ".join(f"'{a}'" for a in block["args"]) + "]",
        f"startup_timeout_sec = {block.get('startup_timeout_sec', 60)}",
        "",
    ]
    rendered = "\n".join(block_lines)
    # 行锚定 + 负向断言：只吃到"下一个以 [ 开头的表头行"之前，绝不跨行吞掉后续段落
    # （旧写法 `(?:[^\[].*\n?)*` 里的 `[^\[].` 会跨换行匹配，曾把块后的 [desktop] 段整段吃掉）
    pattern = re.compile(rf"^{re.escape(header)}[ \t]*\n(?:(?!^\[)[^\n]*\n?)*", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(rendered + "\n", text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + rendered
    cfg.write_text(text, encoding="utf-8")


def write_json(cfg: Path, server_key: str, block: dict) -> None:
    data = {}
    if cfg.is_file():
        try:
            with open(cfg, encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError:
            data = {}
    root_key = "mcpServers" if ("mcpServers" in data or "mcp_servers" not in data) else "mcp_servers"
    servers = data.setdefault(root_key, {})
    existing = _find_server_key(servers)
    if existing:
        servers[existing] = {**servers[existing], **block}
    else:
        servers[server_key] = block
    with open(cfg, "w", encoding="utf-8", newline="") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


WRITERS = {"yaml": write_yaml, "toml": write_toml, "json": write_json}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="platforms.yaml → 各平台 MCP 配置单点同步")
    ap.add_argument("--root", required=True, help="中枢根目录（含 system/platforms.yaml）")
    ap.add_argument("--platform", action="append", help="只处理指定平台（可重复）")
    ap.add_argument("--apply", action="store_true", help="写回（默认 dry-run）")
    ap.add_argument(
        "--python",
        default=os.environ.get("HUB_MCP_PYTHON", DEFAULT_PYTHON),
        help="MCP 子进程解释器",
    )
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args(argv)

    hub_root = Path(args.root).resolve()
    project_root = hub_root.parent
    data = load_platforms(hub_root)
    launcher_rel = (data.get("global") or {}).get("launcher") or "hub-engine/scripts/hub_mcp_launcher.py"
    launcher = hub_root / launcher_rel
    if not launcher.is_file():
        launcher = project_root / launcher_rel
    if not launcher.is_file():
        print(f"launcher 不存在：{launcher_rel}", file=sys.stderr)
        return 2

    results, drift_total = [], 0
    for name, info in (data.get("platforms") or {}).items():
        if args.platform and name not in args.platform:
            continue
        entry = {
            "platform": name,
            "format": info.get("config_format"),
            "status": "skipped",
            "detail": "",
        }
        if info.get("type") != "mcp" or not info.get("mcp_config_path"):
            entry["detail"] = "非 mcp 平台（file/hook），本脚本不处理"
            results.append(entry)
            continue
        fmt = str(info.get("config_format") or "json").lower()
        if fmt not in WRITERS:
            entry["status"] = "error"
            entry["detail"] = f"不支持的 config_format: {fmt}"
            results.append(entry)
            continue
        cfg = resolve_config_path(info["mcp_config_path"])
        expected = expected_block(name, cfg, hub_root, launcher, args.python, fmt)
        server_key, current = read_current(fmt, cfg, info.get("server_key") or DEFAULT_SERVER_KEY)
        if block_matches(current, expected):
            entry["status"] = "ok"
            entry["detail"] = f"一致（{cfg.name}）"
        else:
            drift_total += 1
            entry["status"] = "drift"
            entry["detail"] = f"需同步（{cfg.name}，server_key={server_key}）"
            if args.apply:
                backup = cfg.with_name(cfg.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
                if cfg.is_file():
                    shutil.copy2(cfg, backup)
                try:
                    if fmt == "yaml":
                        WRITERS[fmt](cfg, server_key, expected, info.get("indent", 2))
                    else:
                        WRITERS[fmt](cfg, server_key, expected)
                    entry["status"] = "applied"
                    entry["detail"] = f"已写回（备份 {backup.name}）"
                except Exception as exc:
                    entry["status"] = "error"
                    entry["detail"] = f"写入失败: {exc}"
                    results.append(entry)
                    _emit(results, args.json)
                    return 3
        results.append(entry)

    _emit(results, args.json)
    if any(r["status"] == "error" for r in results):
        return 3
    if drift_total and not args.apply:
        return 1
    return 0


def _emit(results: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print("=== platform_sync：platforms.yaml → 各平台 MCP 块 ===")
    for r in results:
        icon = {
            "ok": "✅",
            "drift": "⚠️",
            "applied": "✍️",
            "skipped": "•",
            "error": "❌",
        }.get(r["status"], "?")
        print(f"  {icon} {r['platform']:10} [{r['format'] or '-'}] {r['detail']}")


if __name__ == "__main__":
    sys.exit(main())
