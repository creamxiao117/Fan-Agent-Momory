"""幂等创建 AgentMemoryHub 中枢骨架（Obsidian 根 / 唯一事实源）"""

import subprocess
import sys
from pathlib import Path

from common.frontmatter import today_iso

STRUCTURE = [
    "rules",
    "libs",
    "experience",
    "projects",
    "retro",
    "archive",
    ".sync/drafts/trae_draft",
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
- libs/        复用代码库 / 插件片段
- experience/  经验卡片（成功模式 / 踩坑 / 决策理由）
- projects/    各项目心智档案
- retro/       复盘 + 时间线（retro/log.md）
- archive/     过时内容归档

## 使用约定（各平台执行前必读）
1. 执行前先查 INDEX.md 与 rules / experience，命中再执行。
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
  trae:
    memory_dir: "C:/Users/Fan-SJSS/.trae-cn/memory"
    target_file: "user_profile.md"
  code:
    memory_dir: "D:/AIwork/code-memory"
    target_file: "CLAUDE.md"
engine:
  provider_keys: provider_keys.yaml
"""

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
        (root / "hub.config.yaml").write_text(CONFIG_TEMPLATE, encoding="utf-8")
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
        subprocess.run(
            cmd, check=True, capture_output=True, text=True, encoding="utf-8"
        )
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
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\AIwork\AgentMemoryHub"
    print(f"中枢已就绪: {bootstrap(target)}")
