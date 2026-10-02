# @version V1.0 / 2026-10-02 / pi / 提交门禁执行器（3 道 scope-gated）——两个 pre-commit 钩子的唯一实现
"""gate_runner —— 提交门禁的**唯一实现**（架构重构 M0.5/Task 6）。

## 从 bash 搬到 Python 的两个理由

1. **可测**：门禁逻辑此前写在两个 bash 钩子里（外层 6 道 + 中枢 3 道），9 处 exit code、
   零单测。搬到 Python 后作用域判定（`common.gate_scope`）与执行都有单测与负样本。
2. **单一实现**：两个钩子（外层 / 中枢）此前是两份各自演化的脚本 ⇒ 必然漂移
   （实测：编码检查与渲染检查**各被实现两遍**）。现在钩子只是 3 行 wrapper。

## 3 道门禁（触发范围由 **staged 内容**决定，见 `common/gate_scope`）

| 门禁 | 内容 | 为何这样分组 |
|---|---|---|
| `code` | `ruff check` + `ruff format --check`（staged `.py`） | 快（<1s），且每个 py 提交都该跑 |
| `text` | `check_encoding` + markdownlint（staged 文本） | 同样快，且与文件类型强相关 |
| `l0` | `startup_budget` + `render_index --check` | **只有改到 L0 面才跑**——它是趋势类检查，且此前"无条件跑"会因他人未提交改动阻断任何人 |

退出码（收敛为 4 个）：
    0 = 通过（含"无门禁触发"）
    1 = `code` 门禁未通过
    2 = `text` 门禁未通过
    3 = `l0` 门禁未通过
    4 = 环境问题（找不到工具/脚本；**不阻断**，打印警告后 0）

用法：
    python -m scripts.gate_runner --repo outer|hub [--staged-from-git] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.gate_scope import classify  # noqa: E402

EXIT_CODE = {"code": 1, "text": 2, "l0": 3}


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    except FileNotFoundError:
        return 127, f"找不到命令：{cmd[0]}"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def staged_paths(repo_root: Path) -> list[str]:
    code, out = _run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd=repo_root)
    if code != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _python() -> str:
    """优先用仓库 `.venv`（系统 python 缺 jieba ⇒ 检索类测试会静默跳过＝假绿）。"""
    venv = _HUB_ENGINE.parent / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.is_file() else sys.executable


def gate_code(staged: list[str], repo_root: Path, repo: str) -> tuple[bool, str]:
    pys = [p for p in staged if p.endswith(".py")]
    if not pys:
        return True, "无 .py staged"
    py = _python()
    msgs: list[str] = []
    for label, args in (("ruff check", ["check"]), ("ruff format", ["format", "--check"])):
        code, out = _run([py, "-m", "ruff", *args, "--force-exclude", *pys], cwd=repo_root)
        if code == 127 or "No module named ruff" in out:
            return True, "ruff 未安装，跳过（不阻断）"
        if code != 0:
            return False, f"{label} 未通过\n{out.strip()}"
        msgs.append(label)
    return True, " + ".join(msgs) + " 通过"


def gate_text(staged: list[str], repo_root: Path, repo: str) -> tuple[bool, str]:
    py = _python()
    enc_script = _HUB_ENGINE / "scripts" / "check_encoding.py"
    texts = [
        p
        for p in staged
        if Path(p).suffix.lower()
        in {
            ".py",
            ".ps1",
            ".bat",
            ".cmd",
            ".vbs",
            ".js",
            ".ts",
            ".tsx",
            ".cs",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".xml",
            ".csv",
        }
        or Path(p).name == "pre-commit"
    ]

    def _disk(p: str) -> Path:
        """staged 路径 → **待检查的磁盘路径**（优先 index 物化版，退化到工作树）。

        为何优先 index：见 `_materialize_index` 的 docstring（漏放 + 误伤两个缺陷）。
        物化失败（不可能在正常仓里发生）才退到工作树，并在输出里说明。
        """
        base = repo_root if repo == "outer" else (_HUB_ENGINE.parent / "AgentMemoryHub")
        if index_root is not None:
            cand = index_root / p
            if cand.is_file():
                return cand
        return base / p

    index_root = _materialize_index(repo_root)
    existing = [p for p in texts if _disk(p).is_file()]
    msgs: list[str] = []
    if len(existing) != len(texts):
        msgs.append(f"跳过 {len(texts) - len(existing)} 个已不在待提交内容里的文件")
    if existing and enc_script.is_file():
        args = [str(enc_script), *[str(_disk(p)) for p in existing]]
        code, out = _run([py, *args], cwd=_HUB_ENGINE)
        bad = [ln for ln in out.splitlines() if ln.startswith("[FAIL]") or ln.startswith("[WARN]")]
        if code != 0:
            return False, "编码/行尾门禁未通过（**针对即将提交的内容**）：\n" + "\n".join(bad or [out.strip()])
        msgs.append(f"编码 {len(existing)} 文件（index 物化）" if index_root else f"编码 {len(existing)} 文件")

    mds = [p for p in staged if p.endswith(".md")]
    if mds:
        # markdownlint 走 PATH（node 工具）；缺工具不阻断（与既有口径一致）
        code, out = _run(["markdownlint", *mds], cwd=repo_root)
        if code == 127:
            msgs.append("markdownlint 未安装，跳过")
        elif code != 0:
            return False, f"markdownlint 未通过\n{out.strip()}"
        else:
            msgs.append(f"markdownlint {len(mds)} 文件")
    return True, " + ".join(msgs) or "无文本 staged"


def _materialize_index(repo_root: Path) -> Path | None:
    """把 **git index（即"即将提交"的内容）** 写到临时目录，返回该目录。

    为何要这一步（本任务的核心）：门禁若直接読**工作树**，就存在两个真实缺陷——
      1. 工作树里**任何人**未提交的卡改动会把别人的提交打红（→ 训练大家用 `--no-verify`）；
      2. **staged 内容与工作树不一致时，检查的不是真正要提交的东西**
         （2026-10-02 实测：`rules/global-rules.md` 的 blob 带着双 CR 进了仓，
         而当时编码门禁读的是已被 `--fix` 修好的工作树 ⇒ 漏放）。

    `git checkout-index -a --prefix=<tmp>/` 取的是 **index**：
      ① 门禁语义变成"你即将提交的东西是否合规"（既不误伤他人，也不漏放自己）；
      ② 对"staged 后又改了工作树"的情形也算得准。
    """
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="gate-index-"))
    code, _out = _run(["git", "checkout-index", "-a", f"--prefix={tmp}{os.sep}"], cwd=repo_root)
    return tmp if code == 0 else None


def gate_l0(staged: list[str], repo_root: Path, repo: str) -> tuple[bool, str]:
    py = _python()
    msgs: list[str] = []
    # 启动链预算 + L0 形状 + L1 形状（読工作树：它审的就是本人正在改的那几个 L0 文件）
    code, out = _run([py, "-m", "scripts.startup_budget"], cwd=_HUB_ENGINE)
    if code == 127:
        msgs.append("startup_budget 跳过")
    elif code != 0:
        keep = [ln for ln in out.splitlines() if ln.startswith(("[OVER]", "FAIL", "[SHAPE]"))]
        return False, "预算/形状门禁未通过：\n" + "\n".join(keep or [out.strip()])
    else:
        total = next((ln for ln in out.splitlines() if ln.startswith("[TOTAL]")), "")
        msgs.append(total or "预算 OK")

    # 渲染产物可复现性。中枢仓：**只看即将提交的内容**（index 物化）
    tmp_index = _materialize_index(repo_root) if repo == "hub" else None
    root_arg = ["--root", str(tmp_index)] if (repo == "hub" and tmp_index) else []
    if repo == "hub" and not root_arg:
        msgs.append("渲染检查跳过（无法物化 index）")
        return True, " + ".join(msgs)
    import shutil

    code, out = _run([py, "-m", "scripts.render_index", "--check", *root_arg], cwd=_HUB_ENGINE)
    if tmp_index:
        shutil.rmtree(tmp_index, ignore_errors=True)
    if code != 0:
        fails = [ln for ln in out.splitlines() if ln.startswith("FAIL")]
        return False, "渲染产物与卡文件不一致（针对**即将提交的内容**）：\n" + "\n".join(fails or [out.strip()])
    msgs.append("渲染一致（staged）" if root_arg else "渲染一致")
    return True, " + ".join(msgs)


GATES_FN = {"code": gate_code, "text": gate_text, "l0": gate_l0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="提交门禁执行器（3 道 scope-gated）")
    ap.add_argument("--repo", choices=("outer", "hub"), default="outer")
    ap.add_argument("--staged", nargs="*", default=None, help="显式给 staged 路径（默认从 git 取）")
    ap.add_argument("--repo-root", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true", help="只打印将跑哪些门禁")
    args = ap.parse_args(argv)

    repo_root = args.repo_root or (
        _HUB_ENGINE.parent if args.repo == "outer" else _HUB_ENGINE.parent / "AgentMemoryHub"
    )
    paths = args.staged if args.staged is not None else staged_paths(repo_root)
    flags = classify(paths)
    todo = [g for g in ("code", "text", "l0") if flags[g]]

    print(f"[gate] repo={args.repo} staged={len(paths)} → 触发门禁：{', '.join(todo) or '（无）'}")
    if args.dry_run:
        return 0
    for name in todo:
        ok, detail = GATES_FN[name](paths, repo_root, args.repo)
        if ok:
            print(f"[gate] ✅ {name}: {detail}")
        else:
            print(f"[gate] ❌ {name}: {detail}")
            print(f"[gate] commit 阻断（exit {EXIT_CODE[name]}）；修好后重试，勿用 --no-verify")
            return EXIT_CODE[name]
    print("[gate] ✅ 全部门禁通过，commit 允许")
    return 0


if __name__ == "__main__":
    sys.exit(main())
