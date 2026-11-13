"""幂等创建 AgentMemoryHub 中枢骨架（Obsidian 根 / 唯一事实源）"""

import subprocess
import sys
from pathlib import Path

# 引导：允许被外部调度器用绝对路径 + 任意 cwd 调用（见 tests/test_script_bootstrap.py）
_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.frontmatter import today_iso  # noqa: E402

STRUCTURE = [
    "rules",
    "methodology",
    "longterm",
    "libs",
    "experience",
    "projects",
    "retro",
    "blueprints",
    "archive",
    # trae 已于 2026-10-05 退役（用户裁定降为普通工作区）：不再预建 trae_draft
    ".sync/drafts/code_draft",
    ".sync/conflicts",
    ".sync/locks",
    ".sync/state",
    ".sync/pending",
]

GITIGNORE = """# Key 与同步器内部状态不提交
provider_keys.yaml
.sync/state/
.sync/locks/
"""

INDEX_TEMPLATE = """# 中枢索引（内容目录）

- rules/       权威规则（AutoCAD 命名、DLL 版本防锁、代码规范…）
- methodology/ 方法论（可复用步骤/流程/思考原则）
- longterm/    长期记忆（用户级稳定档案，跨项目）
- libs/        复用代码库 / 插件片段
- experience/  经验卡片（成功模式 / 踩坑 / 决策理由）
- projects/    各项目心智档案
- retro/       复盘 + 时间线（retro/log.md）
- archive/     过时内容归档

## 使用约定（各平台执行前必读）
1. 执行前先查 INDEX.md 与五类目录（rules / methodology / longterm / projects / experience），命中再执行。
2. 不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。
3. 查询好结果回写为经验卡片（查询产物回写）。

## 检索方式
- 确定性：直接读对应目录文件。
- 语义：`python hub-engine/engine.py retrieve --root <中枢> "<问题>"`

## 沉淀通道
- 各平台内容先写入 .sync/drafts/<platform>_draft/，经同步器校验后提升。
"""

CONFIG_TEMPLATE = """# 同步器配置：各平台路径、规则映射、Key 引用
version: 1
sync:
  single_writer: true
  draft_dir: .sync/drafts
  conflict_dir: .sync/conflicts
  lock_dir: .sync/locks
  pending_dir: .sync/pending
  log_file: retro/log.md
platforms:
  code:
    memory_dir: "{home}/.codex"
    target_file: "AGENTS.md"
  hermes:
    memory_dir: "{home}/AppData/Local/hermes/memories"
    target_file: "MEMORY.md"
    # 平台记忆文件的**体量闸** = 消费端自己的加载上限（hermes config.yaml 的 memory_char_limit）。
    # 不声明 ⇒ push 不设闸（可能把消费端灌爆，而 push 照样报「成功」）。
    # ⚠ 必须与**本机**消费端配置一致（下面这个值要按本机 config.yaml 改）；改一边要改另一边。
    memory_char_limit: 16000
  workbuddy:
    memory_dir: "{home}/.workbuddy"
    target_file: "MEMORY.md"
  # ⚠ 平台级**告警预算**（只报不拦）—— 字段语义示例（**默认注释掉**；阈值由维护者按实测决定，
  #    中枢不擅自给任何平台填数字）：
  #   memory_char_warn_limit: <正整数，单位=字符>
  #
  #   与上面 memory_char_limit 的**语义差别**（务必分清，填错字段 = 闸/探针错位）：
  #     - memory_char_limit     = **消费端自己的加载上限** ⇒ 超限 ⇒ **拒绝写入**（阻断）。
  #                              只有能**核验消费端上限**的平台才能声明（如 hermes）；
  #                              消费端上限未核验的平台**不得**声明它。
  #     - memory_char_warn_limit = **hub 侧自设预算**（告警线）⇒ 超限 ⇒ **照常写入**，
  #                              但 push() 返回的 stat 里出结构化告警（stat["warnings"]），
  #                              且中枢日志 retro/log.md 留一行 ⇒ 「提前知道在长胖」的探针，
  #                              **不是**消费端限制。
  #     适用于消费端上限无法核验的平台（mavis / code / workbuddy / deepseek / pi）。
engine:
  provider_keys: provider_keys.yaml
"""

# 模板里的 {home} 在写盘时替换为当前机器的家目录（换机重跑 bootstrap 即正确）
_HOME_POSIX = Path.home().as_posix()

DEFAULT_LOG = "# 时间线\n\n"


def bootstrap(root: str | Path) -> Path:
    """创建中枢骨架；已存在则跳过（幂等）。返回中枢根。"""
    root = Path(root).expanduser().resolve()
    for sub in STRUCTURE:
        (root / sub).mkdir(parents=True, exist_ok=True)
    if not (root / ".gitignore").exists():
        (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    if not (root / "INDEX.md").exists():
        (root / "INDEX.md").write_text(INDEX_TEMPLATE, encoding="utf-8")
    if not (root / "retro" / "log.md").exists():
        (root / "retro" / "log.md").write_text(
            DEFAULT_LOG + f"## [{today_iso()}] init | 中枢初始化\n", encoding="utf-8"
        )
    if not (root / "hub.config.yaml").exists():
        (root / "hub.config.yaml").write_text(CONFIG_TEMPLATE.replace("{home}", _HOME_POSIX), encoding="utf-8")
    if not (root / "provider_keys.yaml").exists():
        (root / "provider_keys.yaml").write_text(
            "# 各免费模型 Key（独立文件，勿提交 Git）\ndefault: sk-REPLACE_WITH_YOUR_KEY\n",
            encoding="utf-8",
        )
    _git_init(root)
    return root


def _run_git(cmd: list[str]) -> None:
    """运行 git 子命令；失败时透传真实 stderr，避免裸 traceback"""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"git 命令失败: {' '.join(cmd)}\n{stderr or e}") from e


def _git_init(root: Path) -> None:
    """确保中枢是 Git 仓库（审计/回滚用）"""
    if (root / ".git").exists():
        return
    _run_git(["git", "-C", str(root), "init"])
    _run_git(["git", "-C", str(root), "add", "-A"])
    # 注入本地身份，保证未配置全局 user.name/user.email 也能完成首次提交（不污染全局配置）
    _run_git(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=AgentMemoryHub",
            "-c",
            "user.email=hub@local",
            "commit",
            "-m",
            "chore: 中枢初始化",
        ]
    )


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "AgentMemoryHub"
    print(f"中枢已就绪: {bootstrap(target)}")
