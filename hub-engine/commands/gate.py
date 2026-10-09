# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 gate（engine.py P1 拆分）
"""CLI 子命令：`hub gate` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_gate(args) -> int:
    """质量门禁编排：lint -> pytest -> ruff -> 向量召回回归。"""
    import subprocess

    root = Path(args.root).resolve()
    # ⚠️ 2026-10-09 体检修复（第二条路径缺陷）：子进程 cwd = hub-engine，而 `--root` 是**调用者
    # cwd 下的相对路径**（如巡检/CI 写 `--root AgentMemoryHub`）⇒ 子进程按 hub-engine/AgentMemoryHub
    # 找中枢，找不到就静默 0% 且 exit 0（假绿）。resolve() 先钉成绝对路径，与 cwd 无关。
    # ⚠️ 2026-10-09 修复（体检发现）：原为 `Path(__file__).resolve().parent`（= hub-engine/commands），
    # 三处连带失真：① pytest 在 commands/ 下**收集到 0 个用例**（exit=5）却只被记为 fail_code 11，
    # 门禁"全绿"其实从未跑过 769 个测试；② ruff 只扫 commands/（漏掉 tools/ common/ scripts/）；
    # ③ `engine_dir/scripts/vector_bench.py` 解析成 commands/scripts/vector_bench.py（不存在 → exit=2）。
    # 正确根是 hub-engine（tests/ scripts/ pyproject.toml 都在这一层）。
    engine_dir = Path(__file__).resolve().parent.parent
    steps: dict[str, tuple[list[str], int]] = {}
    results: dict[str, int] = {}

    from tools.lint import lint as _lint

    rep = _lint(root)
    lh = len(rep["orphans"]) + len(rep["ghosts"]) + len(rep["stale"]) + rep["invalid"]
    print(
        f"[gate] lint: 孤儿 {len(rep['orphans'])} · 幽灵 {len(rep['ghosts'])} · "
        f"陈旧 {len(rep['stale'])} · 无效 {rep['invalid']}"
    )
    results["lint"] = 2 if lh else 0
    if lh and not args.keep_going:
        return 2

    if not args.skip_pytest:
        steps["pytest"] = ([sys.executable, "-m", "pytest", "-q"], 11)
    if not args.skip_ruff:
        steps["ruff"] = ([sys.executable, "-m", "ruff", "check", "."], 12)
    if not args.skip_vector:
        argv = [
            sys.executable,
            str(engine_dir / "scripts" / "vector_bench.py"),
            "--real",
            str(root),
        ]
        if args.fail_below is not None:
            argv += ["--fail-below", str(args.fail_below)]
        steps["vector_regression"] = (argv, 3)

    fail = 0
    for name, (argv, fail_code) in steps.items():
        try:
            r = subprocess.run(
                argv,
                cwd=engine_dir,
                capture_output=True,
                text=True,
                timeout=args.timeout,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            print(f"[gate] {name}: 无法运行（{exc}），视作环境缺失 127")
            fail = max(fail, 127)
            results[name] = 127
            if not args.keep_going:
                return fail
            continue
        last = (r.stderr or r.stdout or "(无输出)").strip().splitlines() or ["(无输出)"]
        print(f"[gate] {name}: exit={r.returncode}  {last[-1]}")
        results[name] = r.returncode
        if r.returncode != 0:
            mapped = r.returncode if r.returncode in (3, 127) else fail_code
            fail = max(fail, mapped)
            if not args.keep_going:
                return fail

    print((f"[gate] 结果：fail_code={fail}（keep_going={args.keep_going}）") if fail else "[gate] 结果：全绿 (0)")
    for k, v in results.items():
        print(f"   {k}: exit={v}")
    return fail
