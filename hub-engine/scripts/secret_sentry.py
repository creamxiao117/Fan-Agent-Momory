#!/usr/bin/env python3
"""凭证泄漏巡检哨兵：扫描中枢 .md 卡片，检测不应出现的凭证。

## 为什么重写（2026-09-24）

旧实现在**非版本控制目录**（`D:\\AIwork\\traework\\<hash>\\scripts\\`），其四条模式里
**三条按构造必然误报**：

| 模式 | 缺陷 | 实际误报样态 |
| -- | -- | -- |
| `sk-key` | **缺 `\\b` 词边界** | 匹配词内 `sk-`：`ta`**`sk-t`**`rigger-…`、`autode`**`sk-f`**`orge-…`、`open`**`sk-e`**`mbedded-…` |
| `authorization` | 只匹配**字段名** | 任何鉴权文档必然命中：`Authorization: Bearer $KEY` |
| `api-key-field` | 值不做**形态校验** | `api_key=duoyuanx`（厂商名）被当作密钥 |

后果：实测 **26 条"高危"**，抽样 6 条**全为误报**；任务每晚 `exit 2`
→ 永久红灯 → **告警疲劳，真泄漏会被淹没**。这比不扫描更糟。

## 本实现的三层精度

1. **`known-key`（最高精度）**：与 `provider_keys.yaml` 的真值做**精确比对**。
   真密钥一旦入卡，必被抓住——这是唯一不依赖形态猜测的通道。
2. **通用模式 + 形态校验**：正则先取候选，再由 `_looks_like_secret()` 判断
   "看起来像不像密钥"（长度 / 含数字 / 非连字符 slug）。
3. **占位符与文档示例豁免**：`<KEY>`、`${VAR}`、`your-key`、`example`、`已脱敏` 等。

## 分级（按"能否被检索到"）

- **高危**：`known-key` 命中（任意位置，真密钥入仓就是风险）；
  或通用模式命中**权威区**（可被检索、会被注入上下文）
- **低危**：通用模式命中**非权威区**（归档/.backup）；或本地嵌入 key

## 退出码

- `0` 干净 ／ `1` 仅低危 ／ `2` 高危

用法：
    python scripts/secret_sentry.py [--root AgentMemoryHub] [--quiet]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# 计划任务/无终端环境 stdout 常为 GBK，无法编码 ✓ 等字符；强制 UTF-8 防中断。
if hasattr(sys.stdout, "reconfigure"):  # Python 3.7+
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 中枢根：由脚本位置推导，**不硬编码 worktree 绝对路径** ──────────────────
# 旧实现把 HUB_ROOT 写死到一个 worktree；worktree 一移/一删，任务就静默扫空。
# hub-engine/scripts/secret_sentry.py → parents[2] = 仓库根
_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "AgentMemoryHub"

# 权威区：会被检索、会被注入上下文 ⇒ 命中即高危
AUTHORITY_DIRS = frozenset(
    {
        "rules",
        "methodology",
        "experience",
        "blueprints",
        "longterm",
        "projects",
        "notes",
    }
)

# ── 通用凭证模式 ────────────────────────────────────────────────────────────
# 每个模式都**必须**捕获候选值到 group(1)，交由 _looks_like_secret() 做形态校验。
# 关键修复：`\b` 词边界——否则 `ta|sk-`、`autode|sk-`、`open|sk-` 全部误判。
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # sk- 系（OpenAI / Anthropic / OpenRouter 等）
    ("sk-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")),
    # Bearer <token>：token 本身须像密钥（$KEY / <TOKEN> 不匹配）
    ("bearer", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9_\-.]{20,})")),
    # Authorization 后必须跟真值（旧实现只匹配字段名，任何文档都命中）
    (
        "authorization",
        re.compile(
            r"(?i)\bauthorization\s*[:=]\s*[\"']?(?:bearer\s+)?([A-Za-z0-9_\-.]{20,})"
        ),
    ),
    # api_key/apiKey/api-key = 值（值须像密钥；厂商名如 duoyuanx 不算）
    (
        "api-key-field",
        re.compile(r"(?i)\bapi[_\s\-]?key\s*[:=]\s*[\"']?([A-Za-z0-9_\-.]{20,})"),
    ),
    # 带标签的裸密钥："Bearer API Key（…）：<value>"、"令牌：<value>" 等。
    # 此模式由实测补入：`experience/local-vision-architecture-ai-minillm.md` 中的真实泄漏
    # 写作 `- Bearer API Key（8081/8082 /v1）：F2ant3…`——**前三种模式都拓不到**，
    # 旧实现仅靠**硬编码该串**才命中。删掉硬编码而不补本模式 = 修掉 26 个误报的同时漏掉 1 个真泄漏。
    (
        "labeled-secret",
        re.compile(
            # 标签后必须 `\b`：否则 `tokenize` 里的 `token` 会被当标签（实测误报来源）。
            # 标签与冒号间隔收窄到 20 字符；值字符集**剔除 `/` 与 `\`**
            # （实测：路径 `/AgentMemoryT1/…-2026-09-07/` 曾被吃成"密钥"）。
            r"(?i)\b(?:api[\s_\-]?key|secret|token|password|passwd|密钥|令牌|密码)\b"
            r"\s*[（(]?[^:：\n]{0,20}?[:：]\s*([A-Za-z0-9_\-+=]{20,})"
        ),
    ),
]

# 占位符 / 文档示例 / 已脱敏（对整行判定）
_PLACEHOLDER_RE = re.compile(
    r"(?i)<[^>\s]{1,60}>"  # <KEY> <YOUR_TOKEN>
    r"|\$\{?\w+\}?"  # $KEY ${TOKEN}
    r"|your[-_]?(?:secret|key|api|token|credential)"
    r"|set-your-"
    r"|xxxx+"
    r"|example|dummy|placeholder|redacted|已脱敏|示例|占位"
)

# 连字符小写 slug（如 task-trigger-phrases-for-orchestration）：不是密钥
_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){2,}")


def _looks_like_secret(value: str) -> bool:
    """形态校验：判断候选串"像不像真密钥"。

    三条判据（缺一不可），全部由实测误报反推而来：
    1. **长度 ≥ 20** —— 排除 `duoyuanx` 之类短词
    2. **含至少 1 位数字** —— 真 API key 几乎必含数字；排除
       `task-trigger-phrases-for-orchestration`、`autodesk-forge-forge-api-dotnet-cli`
    3. **不是连字符 slug** —— 进一步排除 `embedded-fido2-firmware-blueprint`（含数字"2"）
    4. **不含路径分隔符** —— 排除 `/AgentMemoryT1/…-2026-09-07/` 这类被误吃的路径
    """
    if len(value) < 20:
        return False
    if "/" in value or "\\" in value:
        return False
    if not any(c.isdigit() for c in value):
        return False
    if _SLUG_RE.fullmatch(value):
        return False
    # 至少 8 个字母（防纯数字串被当作密钥）
    letters = sum(c.isalpha() for c in value)
    return letters >= 8


def _load_known_keys(root: Path) -> list[str]:
    """provider_keys.yaml 中的**真值**（合法存储点，但不得进任何卡片）。"""
    path = root / "provider_keys.yaml"
    if not path.is_file():
        return []
    try:
        import yaml  # 延迟导入：仅在需要时
    except ImportError:
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    out: list[str] = []
    for value in data.values():
        if isinstance(value, str) and value.strip():
            out.append(value.strip())
    return out


def _load_local_keys(root: Path) -> list[str]:
    """配置中的本地嵌入 key。

    旧实现把一个 key **硬编码进脚本**——现已过期（配置改为 `lm-studio` 占位），
    但那个值仍遗留在一张卡片里。改为**动态读配置**：配置变，本检查跟着变。
    """
    path = root / "system" / "config.yaml"
    if not path.is_file():
        return []
    try:
        import yaml
    except ImportError:
        return []
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    out: list[str] = []
    for section in ("embed", "llm", "chat"):
        block = cfg.get(section)
        if isinstance(block, dict):
            key = str(block.get("api_key") or "").strip()
            # 占位值（如本地服务的 `lm-studio`）不是密钥，跳过
            if key and _looks_like_secret(key):
                out.append(key)
    return out


def _is_authority(path: Path, root: Path) -> bool:
    """卡片是否位于权威区（决定严重性：可被检索到 = 真风险）。"""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] in AUTHORITY_DIRS


def _redact(value: str, keep: int = 4) -> str:
    """脱敏：只露前 4 / 后 4 字符（避免把泄漏抄进日报）。"""
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}...{value[-keep:]}"


def _scan(root: Path) -> tuple[list[dict], list[dict]]:
    """遍历全部 .md，返回 (高危, 低危)。"""
    high: list[dict] = []
    low: list[dict] = []
    known_keys = _load_known_keys(root)
    local_keys = _load_local_keys(root)

    for path in sorted(root.rglob("*.md")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        authority = _is_authority(path, root)
        for lineno, line in enumerate(lines, 1):
            # ① known-key：真值精确比对（最高精度，不过形态猜测）
            for key in known_keys:
                if key in line:
                    high.append(
                        {
                            "file": path,
                            "line": lineno,
                            "kind": "known-key",
                            "match": _redact(key),
                        }
                    )
            # ② 本地嵌入 key
            for key in local_keys:
                if key in line:
                    low.append(
                        {
                            "file": path,
                            "line": lineno,
                            "kind": "local-embed-key",
                            "match": _redact(key),
                        }
                    )
            # ③ 通用模式 + 形态校验（占位符整行豁免）
            if _PLACEHOLDER_RE.search(line):
                continue
            seen_kinds: set[str] = set()
            for kind, pattern in _PATTERNS:
                if kind in seen_kinds:
                    continue
                match = pattern.search(line)
                if not match:
                    continue
                candidate = match.group(1) if match.groups() else match.group(0)
                if not _looks_like_secret(candidate):
                    continue
                seen_kinds.add(kind)
                entry = {
                    "file": path,
                    "line": lineno,
                    "kind": kind,
                    "match": _redact(candidate),
                }
                (high if authority else low).append(entry)
    return high, low


def _render(root: Path, high: list[dict], low: list[dict]) -> str:
    """渲染日报正文。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005
    status = "高危" if high else ("低危" if low else "干净")
    lines = [
        "# 凭证泄漏巡检日报",
        "",
        f"- 时间：{now}",
        f"- 扫描根：{root}",
        f"- 状态：{status}（高危 {len(high)} / 低危 {len(low)}）",
        "",
        "---",
        "",
        f"扫描中枢：{root}",
        "",
    ]
    if not high and not low:
        lines.append("✓ 干净：未发现凭证泄漏。")
    if high:
        lines.append(f"【高危】{len(high)} 处（权威区命中即可被检索，视为真实泄漏）")
        for item in high[:30]:
            rel = item["file"].relative_to(root)
            lines.append(
                f"  ! [{item['kind']}] {rel}:{item['line']} 命中 {item['match']}"
            )
    if low:
        lines.append(
            f"\n【低危】{len(low)} 处（归档区 / 本地嵌入 key，不构成即时风险）"
        )
        for item in low[:20]:
            rel = item["file"].relative_to(root)
            lines.append(
                f"  ~ [{item['kind']}] {rel}:{item['line']} 命中 {item['match']}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="中枢凭证泄漏巡检哨兵")
    parser.add_argument(
        "--root",
        type=Path,
        default=_DEFAULT_ROOT,
        help=f"中枢根目录（默认由脚本位置推导：{_DEFAULT_ROOT}）",
    )
    parser.add_argument("--quiet", action="store_true", help="不打印正文，只写日报")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"[error] 中枢根不存在：{root}", file=sys.stderr)
        return 2

    high, low = _scan(root)
    body = _render(root, high, low)

    if not args.quiet:
        print(body)

    report_dir = root / ".sync"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "secret_sentry_report.md"
    report.write_text(body, encoding="utf-8")
    print(f"[report] 已更新 {report}")

    # 退出码：0=干净，1=仅低危，2=高危
    if high:
        return 2
    if low:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
