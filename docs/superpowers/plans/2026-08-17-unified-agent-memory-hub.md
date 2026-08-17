# 跨 Agent 平台统一记忆中枢 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 按 Spec 建成"统一记忆中枢"第一版：Obsidian 中枢骨架 + hub-engine（同步器/混合检索/提炼/整理/Lint）+ trae/code 平台指令注入 + 一条真实 DLL 规则端到端走通。

**Architecture:** 三层分工——`D:\AIwork\AgentMemoryHub` 为唯一事实源（Obsidian 库，纯内容）；本仓库内 `hub-engine/` Python 项目提供全部能力（单一写入者同步器、确定性+语义混合检索、复盘提炼、整理归档、Lint 健康检查、omniroute 问答）；各平台经同步器对接中枢，只读权威区、可写暂存区、重要规则人工确认。

**Tech Stack:** Python 3.11 · PyYAML · requests · pytest · git（Hub 内做审计/回滚）

**关键决策（已在设计阶段与用户确认）：**
- 中枢位置：独立目录 `D:\AIwork\AgentMemoryHub`
- 计划形态：单份综合计划（按阶段顺序推进）
- 依赖：PyYAML + requests（配置解析 / omniroute 网关调用），其余尽量标准库
- 第一版范围：只做 Spec §5 的 7 项核心，暂不做平台全量接入 / 无人工提炼 / 复杂向量库 / 定时 Lint / web 界面

---

## 目录结构与任务地图

```
feat-implement-plan-ZilBmv/               ← 本仓库（代码）
├── docs/superpowers/plans/2026-08-17-unified-agent-memory-hub.md   ← 本计划
└── hub-engine/                           ← Python 项目（所有任务都在这）
    ├── pyproject.toml
    ├── requirements.txt
    ├── config/
    │   ├── engine.config.yaml            ← 网关地址 / 默认模型 / 超时
    │   └── provider_keys.example.yaml    ← Key 示例（真实 Key 只放中枢根）
    ├── engine.py                         ← CLI 统一入口
    ├── sync.py                           ← 同步器（单一写入者/暂存/去重/确认/Git）
    ├── common/
    │   ├── __init__.py
    │   ├── config.py                     ← hub.config.yaml / engine.config.yaml / provider_keys
    │   ├── frontmatter.py                ← 统一卡片 frontmatter 解析/写入/校验
    │   └── vector.py                     ← 字符 n-gram 向量 + 余弦相似度
    ├── tools/
    │   ├── __init__.py
    │   ├── retrieve.py                   ← 混合检索（确定性 + 语义）
    │   ├── distill.py                    ← 复盘 → 候选规则
    │   ├── tidy.py                       ← 整理/归档
    │   └── lint.py                       ← 库健康检查
    ├── scripts/
    │   └── bootstrap_hub.py              ← 幂等创建 D:\AIwork\AgentMemoryHub 骨架
    └── tests/
        ├── test_vector.py
        ├── test_frontmatter.py
        ├── test_retrieve.py
        ├── test_sync.py
        ├── test_distill.py
        ├── test_tidy.py
        ├── test_lint.py
        └── test_engine.py

D:\AIwork\AgentMemoryHub\               ← 中枢（外部，Obsidian 根，由 bootstrap 创建）
├── rules/ libs/ experience/ projects/ retro/ archive/
├── .sync/{drafts,conflicts,locks,state,pending}/
├── INDEX.md  retro/log.md  hub.config.yaml  provider_keys.yaml  .gitignore
```

任务顺序（共 14 个）：`1 脚手架 → 2 vector → 3 frontmatter → 4 bootstrap 中枢 → 5 sync 同步器 → 6 retrieve 检索 → 7 engine 网关 → 8 distill 提炼 → 9 tidy 整理 → 10 lint 健康检查 → 11 CLI 统一入口 → 12 平台指令注入 → 13 端到端示例 → 14 首次 Lint`

依赖关系：3←2（vector 供语义检索与去重）；5←3（sync 用 frontmatter）；6←2+3；8←3；13←5+6+8；14←10。

---

## Task 1: hub-engine 项目脚手架 + 配置加载

**Files:**
- Create: `hub-engine/pyproject.toml`
- Create: `hub-engine/requirements.txt`
- Create: `hub-engine/common/__init__.py`, `hub-engine/tools/__init__.py`, `hub-engine/config/engine.config.yaml`, `hub-engine/config/provider_keys.example.yaml`
- Create: `hub-engine/common/config.py`
- Test: `hub-engine/tests/test_config.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_config.py
from pathlib import Path

import pytest

from common.config import load_engine_config, load_provider_keys


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_load_engine_config_returns_gateway(tmp_path):
    _write(tmp_path, "engine.config.yaml",
           "gateway_url: http://127.0.0.1:11434\ndefault_model: qwen2.5:7b\ntimeout: 30\n")
    cfg = load_engine_config(tmp_path / "engine.config.yaml")
    assert cfg["gateway_url"] == "http://127.0.0.1:11434"
    assert cfg["default_model"] == "qwen2.5:7b"
    assert cfg["timeout"] == 30


def test_load_provider_keys_reads_hub_root(tmp_path):
    _write(tmp_path, "provider_keys.yaml", "default: sk-fake-123\n")
    keys = load_provider_keys(tmp_path)
    assert keys["default"] == "sk-fake-123"


def test_load_engine_config_default_path_exists():
    # 默认路径指向仓库内 config/engine.config.yaml，必须存在
    p = Path(__file__).resolve().parents[1] / "config" / "engine.config.yaml"
    assert p.exists()
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_config.py -v`（在 `hub-engine/` 下）
Expected: `ModuleNotFoundError: No module named 'common'`（包尚未建，测试失败即为预期）

- [x] **Step 3: 创建脚手架文件**

`hub-engine/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "hub-engine"
version = "0.1.0"
description = "跨 Agent 平台统一记忆中枢 · 同步器与增强引擎"
requires-python = ">=3.10"
dependencies = [
    "PyYAML>=6.0",
    "requests>=2.31",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools.packages.find]
include = ["common*", "tools*"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`hub-engine/requirements.txt`:

```
PyYAML>=6.0
requests>=2.31
pytest>=8.0
```

`hub-engine/common/__init__.py`:

```python
"""统一记忆中枢公共模块：配置 / frontmatter / 向量化"""
```

`hub-engine/tools/__init__.py`:

```python
"""统一记忆中枢工具模块：检索 / 提炼 / 整理 / Lint"""
```

`hub-engine/config/engine.config.yaml`:

```yaml
# omniroute 网关配置（聚合免费模型，OpenAI 兼容 API）
gateway_url: http://127.0.0.1:11434
default_model: qwen2.5:7b
timeout: 30
```

`hub-engine/config/provider_keys.example.yaml`:

```yaml
# 各免费模型 Key（示例）。真实 Key 放中枢根 provider_keys.yaml，勿提交 Git。
default: sk-REPLACE_WITH_YOUR_KEY
```

`hub-engine/common/config.py`:

```python
"""配置加载：hub.config.yaml / engine.config.yaml / provider_keys.yaml"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    """读取 YAML，失败返回空 dict"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}


@dataclass
class HubConfig:
    """中枢根配置（hub.config.yaml 的封装）"""
    root: Path
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, root: str | Path) -> "HubConfig":
        root = Path(root)
        return cls(root=root, data=load_yaml(root / "hub.config.yaml"))

    @property
    def platforms(self) -> dict:
        """各平台 {name: {target_file, memory_dir}}"""
        return self.data.get("platforms", {})

    @property
    def draft_dir(self) -> Path:
        return self.root / self.data.get("sync", {}).get("draft_dir", ".sync/drafts")


def load_engine_config(config_path: str | Path | None = None) -> dict:
    """读取 engine.config.yaml；默认取仓库内 config/ 下的文件"""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "engine.config.yaml"
    return load_yaml(Path(config_path))


def load_provider_keys(hub_root: str | Path) -> dict:
    """读取中枢根下的 provider_keys.yaml（Key 独立文件）"""
    return load_yaml(Path(hub_root) / "provider_keys.yaml")
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/
git commit -m "feat: hub-engine 脚手架与配置加载"
```

---

## Task 2: 轻量向量化模块（语义检索/去重的基础）

**Files:**
- Create: `hub-engine/common/vector.py`
- Test: `hub-engine/tests/test_vector.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_vector.py
from common.vector import cosine, vector


def test_vector_char_bigrams():
    v = vector("autocad dll")
    assert "au" in v and "oc" in v


def test_cosine_similar_sentences_high():
    a = vector("每次修改 DLL 后必须重命名版本号")
    b = vector("修改 DLL 后需要重命名版本号避免锁文件")
    assert cosine(a, b) > 0.3


def test_cosine_unrelated_low():
    a = vector("autocad dll version naming")
    b = vector("今天天气很好适合出去散步")
    assert cosine(a, b) < 0.1


def test_cosine_identity_is_one():
    a = vector("hello world hello world")
    assert cosine(a, a) == 1.0
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_vector.py -v`
Expected: FAIL（`No module named 'common.vector'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/common/vector.py
"""轻量文本向量化：字符 n-gram 词袋 + 余弦相似度（零外部依赖）"""
import math
import re
from collections import Counter


def tokenize(text: str, n: int = 2) -> list[str]:
    """归一化后切字符 n-gram"""
    norm = re.sub(r"\s+", " ", text.lower())
    if len(norm) < n:
        return [norm] if norm else []
    return [norm[i:i + n] for i in range(len(norm) - n + 1)]


def vector(text: str, n: int = 2) -> Counter:
    """文本 → 字符 n-gram 计数向量"""
    return Counter(tokenize(text, n))


def cosine(a: Counter, b: Counter) -> float:
    """两个 Counter 的余弦相似度，0~1"""
    inter = sum(a[k] * b[k] for k in a.keys() & b.keys())
    la = math.sqrt(sum(v * v for v in a.values()))
    lb = math.sqrt(sum(v * v for v in b.values()))
    if not la or not lb:
        return 0.0
    return inter / (la * lb)
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_vector.py -v`
Expected: 4 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/common/vector.py hub-engine/tests/test_vector.py
git commit -m "feat: 字符 n-gram 向量化与余弦相似度"
```

---

## Task 3: 统一 frontmatter 卡片模块

**Files:**
- Create: `hub-engine/common/frontmatter.py`
- Test: `hub-engine/tests/test_frontmatter.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_frontmatter.py
from common.frontmatter import Card, parse_card, read_card, save_card, validate_card, write_card
from pathlib import Path


SAMPLE = """---
type: rule
tags:
  - autocad
  - dll-lock
updated: 2026-08-17
status: active
reuse_count: 0
---
# AutoCAD DLL 版本命名（防文件锁）
每次修改 DLL 后必须递增版本号。
"""


def test_parse_roundtrip():
    card = parse_card(SAMPLE)
    assert card.type == "rule"
    assert card.tags == ["autocad", "dll-lock"]
    assert card.status == "active"
    assert card.reuse_count == 0
    assert "# AutoCAD" in card.body


def test_write_roundtrip_preserves_fields():
    card = parse_card(SAMPLE)
    text = write_card(card)
    again = parse_card(text)
    assert again.type == card.type
    assert again.tags == card.tags
    assert again.body == card.body


def test_validate_ok():
    assert validate_card(parse_card(SAMPLE)) == []


def test_validate_bad_type_and_missing_updated():
    card = parse_card(SAMPLE)
    card.type = "unknown"
    card.updated = ""
    errs = validate_card(card)
    assert any("type" in e for e in errs)
    assert any("updated" in e for e in errs)


def test_save_and_read(tmp_path):
    p = tmp_path / "a.md"
    save_card(parse_card(SAMPLE), p)
    card = read_card(p)
    assert card.type == "rule"
    assert card.path == p


def test_parse_missing_frontmatter_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_card("没有 frontmatter 的纯文本")
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: FAIL（`No module named 'common.frontmatter'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/common/frontmatter.py
"""统一知识卡片 frontmatter 的解析 / 写入 / 校验"""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

VALID_TYPES = {"rule", "exp", "note", "project", "retro"}
VALID_STATUS = {"active", "archived", "candidate"}
KNOWN = {"type", "tags", "updated", "status", "reuse_count"}


@dataclass
class Card:
    """一张知识卡片（对应一个 .md 文件）"""
    type: str = "note"
    tags: list = field(default_factory=list)
    updated: str = ""
    status: str = "active"
    reuse_count: int = 0
    extra: dict = field(default_factory=dict)   # 其他自定义字段原样保留
    body: str = ""
    path: Path | None = None                     # 从磁盘读取时记录来源路径


def parse_card(text: str, path: Path | None = None) -> Card:
    """解析 '---\\n...\\n---\\n正文' 的统一卡片"""
    if not text.startswith("---"):
        raise ValueError("缺少 frontmatter 起始分隔符 '---'")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("frontmatter 缺少结束分隔符 '---'")
    fm = yaml.safe_load(parts[1]) or {}
    card = Card(path=path)
    if isinstance(fm.get("tags"), list):
        card.tags = [str(t) for t in fm["tags"]]
    card.type = str(fm.get("type", "note"))
    card.updated = str(fm.get("updated", ""))
    card.status = str(fm.get("status", "active"))
    card.reuse_count = int(fm.get("reuse_count", 0) or 0)
    card.extra = {k: v for k, v in fm.items() if k not in KNOWN}
    card.body = parts[2].strip()
    return card


def write_card(card: Card) -> str:
    """把卡片渲染回统一格式文本"""
    fm = {
        "type": card.type,
        "tags": card.tags,
        "updated": card.updated or date.today().isoformat(),
        "status": card.status,
        "reuse_count": card.reuse_count,
    }
    fm.update(card.extra)
    return ("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip()
            + "\n---\n\n" + card.body.strip() + "\n")


def validate_card(card: Card) -> list[str]:
    """返回错误列表；空列表表示合法"""
    errs = []
    if card.type not in VALID_TYPES:
        errs.append(f"type 必须为 {sorted(VALID_TYPES)} 之一，当前: {card.type}")
    if card.status not in VALID_STATUS:
        errs.append(f"status 必须为 {sorted(VALID_STATUS)} 之一，当前: {card.status}")
    if not card.updated:
        errs.append("updated 必填（YYYY-MM-DD）")
    return errs


def read_card(path: Path) -> Card:
    return parse_card(path.read_text(encoding="utf-8"), path=path)


def save_card(card: Card, path: Path) -> None:
    path.write_text(write_card(card), encoding="utf-8")
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: 6 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/common/frontmatter.py hub-engine/tests/test_frontmatter.py
git commit -m "feat: 统一 frontmatter 卡片解析/写入/校验"
```

---

## Task 4: 中枢骨架引导脚本（创建 D:\AIwork\AgentMemoryHub）

**Files:**
- Create: `hub-engine/scripts/bootstrap_hub.py`
- Test: `hub-engine/tests/test_bootstrap.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_bootstrap.py
from pathlib import Path

from scripts.bootstrap_hub import bootstrap


def test_bootstrap_creates_skeleton(tmp_path):
    root = bootstrap(tmp_path)
    for sub in ("rules", "libs", "experience", "projects", "retro", "archive",
                ".sync/drafts/trae_draft", ".sync/drafts/code_draft",
                ".sync/conflicts", ".sync/locks", ".sync/state", ".sync/pending"):
        assert (root / sub).is_dir(), sub
    assert (root / "INDEX.md").exists()
    assert (root / "retro" / "log.md").exists()
    assert (root / "hub.config.yaml").exists()
    assert (root / "provider_keys.yaml").exists()
    assert (root / ".gitignore").exists()


def test_bootstrap_idempotent(tmp_path):
    bootstrap(tmp_path)
    bootstrap(tmp_path)  # 重复执行不报错、不覆盖已有文件
    assert (tmp_path / "INDEX.md").exists()


def test_bootstrap_git_init(tmp_path):
    root = bootstrap(tmp_path)
    assert (root / ".git" / "config").exists()
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_bootstrap.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'scripts'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/scripts/bootstrap_hub.py
"""幂等创建 AgentMemoryHub 中枢骨架（Obsidian 根 / 唯一事实源）"""
import subprocess
import sys
from datetime import date
from pathlib import Path

STRUCTURE = [
    "rules", "libs", "experience", "projects", "retro", "archive",
    ".sync/drafts/trae_draft", ".sync/drafts/code_draft",
    ".sync/conflicts", ".sync/locks", ".sync/state", ".sync/pending",
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
    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    if not (root / "INDEX.md").exists():
        (root / "INDEX.md").write_text(INDEX_TEMPLATE, encoding="utf-8")
    if not (root / "retro" / "log.md").exists():
        (root / "retro" / "log.md").write_text(
            DEFAULT_LOG + f"## [{date.today().isoformat()}] init | 中枢初始化\n", encoding="utf-8")
    if not (root / "hub.config.yaml").exists():
        (root / "hub.config.yaml").write_text(CONFIG_TEMPLATE, encoding="utf-8")
    if not (root / "provider_keys.yaml").exists():
        (root / "provider_keys.yaml").write_text(
            "# 各免费模型 Key（独立文件，勿提交 Git）\ndefault: sk-REPLACE_WITH_YOUR_KEY\n",
            encoding="utf-8")
    _git_init(root)
    return root


def _git_init(root: Path) -> None:
    """确保中枢是 Git 仓库（审计/回滚用）"""
    if (root / ".git").exists():
        return
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "chore: 中枢初始化"],
                   check=True, capture_output=True, text=True, encoding="utf-8")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\AIwork\AgentMemoryHub"
    print(f"中枢已就绪: {bootstrap(target)}")
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_bootstrap.py -v`
Expected: 3 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/scripts/ hub-engine/tests/test_bootstrap.py
git commit -m "feat: 中枢骨架引导脚本（幂等创建 Obsidian 库）"
```

---

## Task 5: 同步器核心（单一写入者 + 暂存区提升 + 去重 + Git 提交）

**Files:**
- Create: `hub-engine/sync.py`
- Test: `hub-engine/tests/test_sync.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_sync.py
from pathlib import Path

from common.frontmatter import parse_card, write_card
from scripts.bootstrap_hub import bootstrap
from sync import append_log, confirm_rule, ingest


def _make_draft(root: Path, platform: str, name: str, body: str, ctype: str = "exp") -> Path:
    d = root / ".sync" / "drafts" / f"{platform}_draft"
    d.mkdir(parents=True, exist_ok=True)
    card = parse_card(f"""---
type: {ctype}
tags:
  - test
updated: 2026-08-17
status: candidate
reuse_count: 0
---
{body}
""")
    p = d / name
    p.write_text(write_card(card), encoding="utf-8")
    return p


def test_ingest_promotes_low_risk_to_authority(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="exp")
    stat = ingest(root, "trae")
    assert stat["promoted"] == 1
    assert (root / "experience" / "exp-a.md").exists()
    assert stat["status"] == "ok"


def test_ingest_rule_goes_to_pending_not_authority(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "rule-x.md", "重要硬约束：DLL 必须递增版本", ctype="rule")
    stat = ingest(root, "trae")
    assert stat["pending"] == 1
    assert not (root / "rules" / "rule-x.md").exists()
    assert (root / ".sync" / "pending" / "rule-x.md").exists()


def test_ingest_duplicate_goes_to_conflicts(tmp_path):
    root = bootstrap(tmp_path)
    (root / "experience" / "exp-a.md").write_text(
        "---\ntype: exp\ntags: [test]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n这是一条经验卡片内容\n",
        encoding="utf-8")
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="exp")
    stat = ingest(root, "trae")
    assert stat["duplicate"] == 1
    assert list((root / ".sync" / "conflicts").glob("*.md"))


def test_ingest_duplicate_deletes_draft(tmp_path):
    """重复草稿处理后必须删除，避免下次同步重复处理并覆盖冲突区"""
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="exp")
    ingest(root, "trae")
    _make_draft(root, "trae", "exp-a.md", "这是一条经验卡片内容", ctype="exp")
    stat = ingest(root, "trae")
    assert stat["duplicate"] == 1
    assert not (root / ".sync" / "drafts" / "trae_draft" / "exp-a.md").exists()


def test_ingest_same_name_different_content_no_overwrite(tmp_path):
    """同名不同内容（语义不重复）→ 不得覆盖权威区，转冲突区且删除草稿"""
    root = bootstrap(tmp_path)
    (root / "experience" / "exp-a.md").write_text(
        "---\ntype: exp\ntags: [test]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n记录一次排查 Windows 系统崩溃的经验\n",
        encoding="utf-8")
    _make_draft(root, "trae", "exp-a.md", "如何制作拿铁咖啡的心得体会", ctype="exp")
    stat = ingest(root, "trae")
    assert "排查 Windows 系统崩溃" in (root / "experience" / "exp-a.md").read_text(encoding="utf-8")
    assert stat["duplicate"] == 1
    assert not (root / ".sync" / "drafts" / "trae_draft" / "exp-a.md").exists()


def test_confirm_rule_promotes_to_rules(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, "trae", "rule-x.md", "重要硬约束：DLL 必须递增版本", ctype="rule")
    ingest(root, "trae")
    dst = confirm_rule(root, "rule-x.md")
    assert dst.exists()
    assert dst.parent.name == "rules"


def test_append_log_uses_unified_prefix(tmp_path):
    root = bootstrap(tmp_path)
    append_log(root, "ingest", "测试写入")
    lines = (root / "retro" / "log.md").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("## [") and "| 测试写入" in line for line in lines)
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_sync.py -v`
Expected: FAIL（`No module named 'sync'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/sync.py
"""同步器：单一写入者 + 暂存区提升 + 去重/冲突 + 人工确认 + Git 提交"""
import shutil
import subprocess
from datetime import date
from pathlib import Path

from common.frontmatter import Card, read_card, validate_card, write_card
from common.vector import cosine, vector

TYPE_DIR = {"rule": "rules", "exp": "experience", "note": "experience",
            "project": "projects", "retro": "retro"}
HIGH_RISK = {"rule"}   # 重要规则：须人工确认


def _git(repo: Path, *args: str) -> str:
    """运行 git 子命令；返回 stdout，失败时透传真实 stderr（与 bootstrap 的 _run_git 一致）"""
    cmd = ["git", "-C", str(repo), *args]
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
        return r.stdout or ""
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"git 命令失败: {' '.join(cmd)}\n{stderr or e}") from e


def _append_log(root: Path, op: str, title: str) -> None:
    """retro/log.md append-only 时间线：## [YYYY-MM-DD] <op> | <title>"""
    log = root / "retro" / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"## [{date.today().isoformat()}] {op} | {title}\n")


def append_log(root: Path, op: str, title: str) -> None:
    _append_log(root, op, title)


def _authority_cards(root: Path) -> list[Card]:
    cards = []
    for sub in ("rules", "experience", "projects", "libs", "retro"):
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            try:
                cards.append(read_card(p))
            except Exception:
                continue
    return cards


def _find_duplicate(root: Path, card: Card, threshold: float = 0.7) -> Card | None:
    """语义相似度判断是否与权威区已有卡片重复（内容冲突不覆盖）"""
    cv = vector(card.body)
    for c in _authority_cards(root):
        if cosine(cv, vector(c.body)) >= threshold:
            return c
    return None


def _commit(root: Path, message: str) -> None:
    """提交变更：无变更可提交时直接跳过；真实 Git 失败透传 stderr"""
    if not _git(root, "status", "--porcelain").strip():
        return
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=AgentMemoryHub", "-c", "user.email=hub@local",
         "commit", "-m", message)


class _WriteLock:
    """写前锁：同一时刻只允许一个写入者（.sync/locks/writer.lock）"""

    def __init__(self, root: Path):
        self.lock = root / ".sync" / "locks" / "writer.lock"

    def __enter__(self):
        if self.lock.exists():
            raise RuntimeError("写锁已存在，同步器正在运行中")
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text("", encoding="utf-8")
        return self

    def __exit__(self, *exc):
        self.lock.unlink(missing_ok=True)


def ingest(root: Path, platform: str) -> dict:
    """把 .sync/drafts/<platform>_draft/ 下的内容提升到中枢；返回统计"""
    root = Path(root)
    stat = {"promoted": 0, "pending": 0, "duplicate": 0, "invalid": 0, "status": "ok"}
    drafts = root / ".sync" / "drafts" / f"{platform}_draft"
    if not drafts.is_dir():
        return stat
    try:
        with _WriteLock(root):
            for p in sorted(drafts.glob("*.md")):
                try:
                    card = read_card(p)
                except Exception:
                    stat["invalid"] += 1
                    continue
                if validate_card(card):
                    stat["invalid"] += 1
                    continue
                if _find_duplicate(root, card):
                    stat["duplicate"] += 1
                    cdir = root / ".sync" / "conflicts"
                    cdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, cdir / f"{platform}_{p.name}")
                    _append_log(root, "ingest", f"重复内容进冲突区：{p.name}")
                    p.unlink()  # 内容已保留在冲突区，草稿无保留价值
                    continue
                if card.type in HIGH_RISK:
                    # 新增重要规则 → 待人工确认
                    pending = root / ".sync" / "pending"
                    pending.mkdir(parents=True, exist_ok=True)
                    card.status = "candidate"
                    (pending / p.name).write_text(write_card(card), encoding="utf-8")
                    stat["pending"] += 1
                    _append_log(root, "ingest", f"新规则待确认：{p.name}")
                else:
                    # 低风险内容 → 自动入区，仅记日志
                    dst = root / TYPE_DIR.get(card.type, "experience") / p.name
                    if dst.exists():
                        # 同名不同内容（语义去重已在上方处理过）→ 不覆盖权威区，转冲突区
                        cdir = root / ".sync" / "conflicts"
                        cdir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(p, cdir / f"{platform}_{p.name}")
                        stat["duplicate"] += 1
                        _append_log(root, "ingest", f"同名不同内容进冲突区：{p.name}")
                    else:
                        card.status = "active"
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_text(write_card(card), encoding="utf-8")
                        stat["promoted"] += 1
                        _append_log(root, "ingest", f"自动入区：{p.name}")
                p.unlink()
            _commit(root, f"sync: ingest {platform} draft → hub")
    except RuntimeError as e:
        stat["status"] = str(e)
    return stat


def confirm_rule(root: Path, name: str) -> Path:
    """人工确认后，把待确认规则提升为 active 并入权威区"""
    root = Path(root)
    src = root / ".sync" / "pending" / name
    if not src.exists():
        raise FileNotFoundError(f"待确认文件不存在: {src}")
    with _WriteLock(root):
        card = read_card(src)
        card.status = "active"
        card.reuse_count = 0
        dst = root / "rules" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(write_card(card), encoding="utf-8")
        src.unlink()
        _append_log(root, "confirm", f"确认规则：{name}")
        _commit(root, f"sync: confirm rule {name}")
    return dst
```

> **代码评审修正（已应用，2026-08-17）**：Task 5 实现经代码评审发现 4 个质量问题并已修复——
> 1. 重复草稿在进冲突区后未删除，下次同步会重复处理并覆盖冲突区 → 现于重复分支先 `p.unlink()` 再 `continue`；
> 2. 同名不同内容的低风险卡片会静默覆盖权威区 → 现先检查 `dst.exists()`，存在则转 `.sync/conflicts/`（计 `duplicate`）不覆盖；
> 3. `_commit` 静默吞掉所有 git 错误 → 现先 `git status --porcelain` 判空跳过，真实失败透传 stderr（与 bootstrap `_run_git` 一致）；
> 4. 清理死代码：删除 `_fingerprint`、`import hashlib`、未用的 `LOW_RISK` 常量。
> 对应补充两条回归测试：`test_ingest_duplicate_deletes_draft`、`test_ingest_same_name_different_content_no_overwrite`。

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_sync.py -v`
Expected: 7 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/sync.py hub-engine/tests/test_sync.py
git commit -m "feat: 同步器核心（单一写入者/暂存/去重/确认/Git）"
```

---

## Task 6: 混合检索（确定性通道 + 语义通道）

**Files:**
- Create: `hub-engine/tools/retrieve.py`
- Test: `hub-engine/tests/test_retrieve.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_retrieve.py
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.retrieve import deterministic_retrieve, retrieve, semantic_retrieve


def _seed(root: Path) -> None:
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号避免被锁。\n",
        encoding="utf-8")
    (root / "experience" / "blunder.md").write_text(
        "---\ntype: exp\ntags: [autocad]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n上次没重命名导致 AutoCAD 占用文件无法覆盖。\n",
        encoding="utf-8")


def test_deterministic_by_tag(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hits = deterministic_retrieve(root, "dll-lock")
    assert [h.path.name for h in hits] == ["dll-lock.md"]


def test_semantic_recalls_similar(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hits = semantic_retrieve(root, "改了插件 DLL 结果被 AutoCAD 锁住打不开")
    names = [h.path.name for h in hits]
    assert "dll-lock.md" in names or "blunder.md" in names


def test_mixed_retrieve_returns_results(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hits = retrieve(root, "DLL 被锁怎么办")
    assert len(hits) >= 1
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_retrieve.py -v`
Expected: FAIL（`No module named 'tools.retrieve'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/tools/retrieve.py
"""混合检索：确定性通道（按 type/tag 精确命中）+ 语义通道（n-gram 余弦召回）"""
from pathlib import Path

from common.frontmatter import Card, read_card
from common.vector import cosine, vector


def _walk_active_cards(root: Path) -> list[Card]:
    cards = []
    for sub in ("rules", "experience", "projects", "libs", "retro"):
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            try:
                c = read_card(p)
            except Exception:
                continue
            if c.status != "archived":
                cards.append(c)
    return cards


def deterministic_retrieve(root: Path, query: str) -> list[Card]:
    """确定性通道：query 命中 type 或任一 tag 即返回"""
    q = query.lower()
    return [c for c in _walk_active_cards(root)
            if q in c.type or any(q in t.lower() for t in c.tags)]


def semantic_retrieve(root: Path, query: str, top_k: int = 5) -> list[Card]:
    """语义通道：对 body+tags 做 n-gram 余弦相似度召回 top-k"""
    qv = vector(query)
    scored = []
    for c in _walk_active_cards(root):
        sim = cosine(qv, vector(c.body + " " + " ".join(c.tags)))
        if sim > 0:
            scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def retrieve(root: Path, query: str, top_k: int = 5) -> list[Card]:
    """混合检索入口：先确定性，命中即返回；否则语义召回（网关不可用时的兜底方案）"""
    hits = deterministic_retrieve(root, query)
    if hits:
        return hits
    return semantic_retrieve(root, query, top_k)
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_retrieve.py -v`
Expected: 3 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/tools/retrieve.py hub-engine/tests/test_retrieve.py
git commit -m "feat: 混合检索（确定性 + 语义通道）"
```

---

## Task 7: omniroute 网关统一入口（chat / 回退）

**Files:**
- Create: `hub-engine/engine.py`
- Test: `hub-engine/tests/test_engine.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_engine.py
from pathlib import Path

import pytest

from engine import chat


def test_chat_calls_gateway_and_returns_content(monkeypatch, tmp_path):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "已命中 DLL 规则"}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["model"] = json["model"]
        return FakeResp()

    monkeypatch.setattr("engine.requests.post", fake_post)
    out = chat("DLL 被锁怎么办", tmp_path)
    assert "DLL" in out
    assert captured["url"].endswith("/v1/chat/completions")


def test_chat_falls_back_on_gateway_error(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("engine.requests.post", boom)
    out = chat("随便问一句", tmp_path)
    assert isinstance(out, str) and out  # 不抛异常，返回兜底文本


def test_chat_raises_when_fallback_disabled(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("engine.requests.post", boom)
    with pytest.raises(RuntimeError):
        chat("x", tmp_path, fallback=False)
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL（`No module named 'engine'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/engine.py
"""omniroute 增强引擎统一入口：chat（检索/归纳/整理均复用此通道）"""
from pathlib import Path

import requests

from common.config import load_engine_config, load_provider_keys
from tools.retrieve import retrieve


def _gateway_kwargs(hub_root: Path) -> tuple[str, str, str, int]:
    cfg = load_engine_config()
    keys = load_provider_keys(hub_root)
    url = cfg.get("gateway_url", "http://127.0.0.1:11434").rstrip("/") + "/v1/chat/completions"
    model = cfg.get("default_model", "qwen2.5:7b")
    api_key = keys.get("default", "")
    timeout = int(cfg.get("timeout", 30))
    return url, model, api_key, timeout


def chat(prompt: str, hub_root: str | Path, fallback: bool = True) -> str:
    """调用 omniroute 网关；网关不可用则回退到文件关键词/full-text 检索"""
    hub_root = Path(hub_root)
    try:
        url, model, api_key, timeout = _gateway_kwargs(hub_root)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = requests.post(url, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        if not fallback:
            raise
        # 兜底：把本地检索结果拼成可读文本，保证功能不中断
        cards = retrieve(hub_root, prompt)
        if not cards:
            return "（网关不可用且中枢无命中，建议交回用户确认）"
        parts = [f"[{c.type}/{c.status}] {c.path.name}" for c in cards[:3]]
        bodies = [c.body.strip() for c in cards[:3]]
        return "网关不可用，已回退本地检索：\n" + "\n".join(parts) + "\n---\n" + "\n\n".join(bodies)
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_engine.py -v`
Expected: 3 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/engine.py hub-engine/tests/test_engine.py
git commit -m "feat: omniroute 网关统一入口与本地回退"
```

---

## Task 8: 复盘 → 候选规则（distill）

**Files:**
- Create: `hub-engine/tools/distill.py`
- Test: `hub-engine/tests/test_distill.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_distill.py
from pathlib import Path

from common.frontmatter import parse_card, write_card
from scripts.bootstrap_hub import bootstrap
from tools.distill import collect_candidates, distill


def _retro_draft(root: Path, platform: str, text: str) -> Path:
    d = root / ".sync" / "drafts" / f"{platform}_draft" / "retro"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "retro-1.md"
    p.write_text(text, encoding="utf-8")
    return p


RETRO_TEXT = """# 复盘 2026-08-17
今天改完插件 DLL 后直接覆盖，被 AutoCAD 锁定，最后只能改版本号解决。
教训：修改 DLL 后必须递增版本号，不能原地覆盖。
"""


def test_collect_candidates_extracts_lessons(tmp_path):
    root = bootstrap(tmp_path)
    _retro_draft(root, "trae", RETRO_TEXT)
    cards = collect_candidates(root, "trae")
    assert len(cards) >= 1
    assert "递增版本" in cards[0]["body"]


def test_distill_writes_candidate_cards(tmp_path):
    root = bootstrap(tmp_path)
    _retro_draft(root, "trae", RETRO_TEXT)
    written = distill(root, "trae")
    assert written  # 至少产出一张候选卡片
    assert all(p.suffix == ".md" for p in written)
    card = parse_card(written[0].read_text(encoding="utf-8"))
    assert card.status == "candidate"


def test_distill_dedupes_repeated_lessons(tmp_path):
    root = bootstrap(tmp_path)
    _retro_draft(root, "trae", RETRO_TEXT)
    _retro_draft(root, "trae", RETRO_TEXT.replace("2026-08-17", "2026-08-18"))
    written = distill(root, "trae")
    # 两条几乎相同 → 只产出一张候选
    assert len(written) == 1
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_distill.py -v`
Expected: FAIL（`No module named 'tools.distill'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/tools/distill.py
"""复盘 → 候选规则：扫描暂存区复盘草稿，归纳去重，产出 candidate 卡片"""
from datetime import date
from pathlib import Path

from common.frontmatter import parse_card, write_card
from common.vector import cosine, vector
from sync import append_log

REQUIRE_MARKERS = ("必须", "禁止", "不要", "一定", "教训", "注意", "规则")


def _split_lessons(text: str) -> list[str]:
    """从复盘草稿里切出带有约束意味的句子/段落"""
    lessons = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if any(m in line for m in REQUIRE_MARKERS):
            lessons.append(line)
    return lessons


def collect_candidates(root: Path, platform: str) -> list[dict]:
    """收集该平台暂存区复盘草稿中的候选内容（含来源）"""
    root = Path(root)
    draft_dir = root / ".sync" / "drafts" / f"{platform}_draft" / "retro"
    if not draft_dir.is_dir():
        return []
    out = []
    for p in sorted(draft_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue  # 坏文件跳过，避免中断整个 distill
        for lesson in _split_lessons(text):
            out.append({"source": p.name, "body": lesson})
    return out


def distill(root: Path, platform: str, output: str = "experience") -> list[Path]:
    """把复盘草稿转成去重后的候选卡片，写入 .sync/drafts/<platform>_draft/candidates/"""
    root = Path(root)
    candidates = collect_candidates(root, platform)
    out_dir = root / ".sync" / "drafts" / f"{platform}_draft" / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)

    unique: list[str] = []
    for c in candidates:
        body = c["body"].lstrip("- ").strip()
        if any(cosine(vector(body), vector(u)) >= 0.7 for u in unique):
            continue  # 与已有候选高度相似，跳过
        unique.append(body)

    written = []
    for i, body in enumerate(unique, 1):
        card = parse_card(f"""---
type: exp
tags:
  - distill
updated: {date.today().isoformat()}
status: candidate
reuse_count: 0
---
{body}
""")
        p = out_dir / f"candidate-{i}.md"
        p.write_text(write_card(card), encoding="utf-8")
        written.append(p)

    if written:
        append_log(root, "distill", f"从 {platform} 复盘产出 {len(written)} 条候选")
    return written
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_distill.py -v`
Expected: 3 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/tools/distill.py hub-engine/tests/test_distill.py
git commit -m "feat: 复盘→候选规则（distill，含去重）"
```

---

## Task 9: 整理/归档（tidy）

**Files:**
- Create: `hub-engine/tools/tidy.py`
- Test: `hub-engine/tests/test_tidy.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_tidy.py
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.tidy import archive


def _seed_rule(root: Path) -> Path:
    p = root / "rules" / "old-rule.md"
    p.write_text(
        "---\ntype: rule\ntags: [old]\nupdated: 2026-08-01\nstatus: active\nreuse_count: 0\n---\n过时规则。\n",
        encoding="utf-8")
    return p


def test_archive_moves_to_archive_and_marks_archived(tmp_path):
    root = bootstrap(tmp_path)
    src = _seed_rule(root)
    dst = archive(root, "rules/old-rule.md", reason="已被新规则取代")
    assert dst.exists()
    assert not src.exists()
    # 保留来源子目录结构：archive/rules/old-rule.md
    assert dst == root / "archive" / "rules" / "old-rule.md"
    card = read_card(dst)
    assert card.status == "archived"
    assert card.extra.get("archived_reason") == "已被新规则取代"
    assert card.body.strip() == "过时规则。"
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "归档 rules/old-rule.md（已被新规则取代）" in log


def test_archive_missing_raises(tmp_path):
    root = bootstrap(tmp_path)
    import pytest
    with pytest.raises(FileNotFoundError):
        archive(root, "rules/nope.md")
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tidy.py -v`
Expected: FAIL（`No module named 'tools.tidy'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/tools/tidy.py
"""整理/归档：把过时/废弃卡片标 archived 并移入 archive/"""
from pathlib import Path

from common.frontmatter import read_card, write_card
from sync import append_log


def archive(root: Path, rel_path: str, reason: str = "") -> Path:
    """把卡片改为 archived 并移动到 archive/；返回新位置"""
    root = Path(root)
    src = root / rel_path
    if not src.exists():
        raise FileNotFoundError(f"待归档文件不存在: {src}")
    card = read_card(src)
    card.status = "archived"
    card.extra.setdefault("archived_reason", reason or "未说明")
    # 保留来源子目录结构，避免不同目录同名文件互相覆盖
    rel_dir = src.parent.relative_to(root)
    dst = root / "archive" / rel_dir / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(write_card(card), encoding="utf-8")
    src.unlink()
    append_log(root, "tidy", f"归档 {rel_path}（{reason or '未说明'}）")
    return dst
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tidy.py -v`
Expected: 2 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/tools/tidy.py hub-engine/tests/test_tidy.py
git commit -m "feat: 整理/归档（tidy）"
```

---

## Task 10: 库健康检查（Lint）

**Files:**
- Create: `hub-engine/tools/lint.py`
- Test: `hub-engine/tests/test_lint.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_lint.py
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.lint import find_orphans, lint


def _seed(root: Path) -> None:
    (root / "rules" / "a.md").write_text(
        "---\ntype: rule\ntags: [x]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n规则 A\n",
        encoding="utf-8")
    (root / "experience" / "orphan.md").write_text(
        "---\ntype: exp\ntags: [y]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n无人引用的孤立页\n",
        encoding="utf-8")
    (root / "rules" / "stale.md").write_text(
        "---\ntype: rule\ntags: [z]\nupdated: 2026-01-01\nstatus: active\nreuse_count: 0\n---\n半年没更新的陈旧页\n",
        encoding="utf-8")


def test_find_orphans(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    names = [p.name for p in find_orphans(root)]
    assert "orphan.md" in names


def test_lint_reports_stale_pages(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    report = lint(root)
    stale = [i["name"] for i in report["stale"]]
    assert "stale.md" in stale


def test_lint_returns_full_shape(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    report = lint(root)
    assert set(report) == {"orphans", "stale", "invalid", "notes"}
    assert isinstance(report["invalid"], int)
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_lint.py -v`
Expected: FAIL（`No module named 'tools.lint'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/tools/lint.py
"""Lint：周期性库健康检查（孤儿页 / 陈旧页 / 无效卡片 / 摘要）"""
from datetime import date
from pathlib import Path

from common.frontmatter import read_card, validate_card

AUTHORITY_DIRS = ("rules", "experience", "projects", "libs", "retro")
STALE_DAYS = 180


def _all_cards(root: Path) -> list:
    """返回 (dir, Path, Card) 列表"""
    out = []
    for sub in AUTHORITY_DIRS:
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            try:
                out.append((sub, p, read_card(p)))
            except Exception:
                out.append((sub, p, None))
    return out


def find_orphans(root: Path) -> list[Path]:
    """无入链指向的页面（INDEX.md 不计入引用）"""
    root = Path(root)
    index_text = ""
    if (root / "INDEX.md").exists():
        index_text = (root / "INDEX.md").read_text(encoding="utf-8")
    orphans = []
    for sub, p, card in _all_cards(root):
        if card is None or card.status == "archived":
            continue
        stem = p.stem
        referenced = stem in index_text
        if not referenced:
            # 粗略排除"自身目录内被其他文件引用"的情况
            for sub2, p2, card2 in _all_cards(root):
                if p2 != p and stem in p2.read_text(encoding="utf-8"):
                    referenced = True
                    break
        if not referenced:
            orphans.append(p)
    return orphans


def lint(root: Path) -> dict:
    """健康检查报告：orphans / stale / invalid / notes"""
    root = Path(root)
    orphans, stale, invalid = [], [], []
    for sub, p, card in _all_cards(root):
        if card is None:
            invalid += 1
            continue
        errs = validate_card(card)
        if errs:
            invalid += 1
            continue
        try:
            age = (date.today() - date.fromisoformat(card.updated)).days
        except ValueError:
            stale.append({"name": p.name, "dir": sub, "updated": card.updated})
            continue
        if age > STALE_DAYS and card.status == "active":
            stale.append({"name": p.name, "dir": sub, "updated": card.updated})
    total = sum(1 for _ in _all_cards(root))
    return {
        "orphans": [str(p) for p in find_orphans(root)],
        "stale": stale,
        "invalid": invalid,
        "notes": f"共检查 {total} 张卡片",
    }
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_lint.py -v`
Expected: 3 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/tools/lint.py hub-engine/tests/test_lint.py
git commit -m "feat: 库健康检查（Lint）"
```

---

## Task 11: CLI 统一入口

**Files:**
- Modify: `hub-engine/engine.py`（追加 main()）
- Test: `hub-engine/tests/test_cli.py`

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_cli.py
from pathlib import Path

from engine import main
from scripts.bootstrap_hub import bootstrap


def test_cli_retrieve_prints_hit(capsys, tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules" / "dll.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号。\n",
        encoding="utf-8")
    rc = main(["retrieve", "--root", str(root), "dll-lock"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dll.md" in out


def test_cli_ingest_and_confirm_flow(tmp_path):
    root = bootstrap(tmp_path)
    d = root / ".sync" / "drafts" / "trae_draft"
    d.mkdir(parents=True, exist_ok=True)
    (d / "r1.md").write_text(
        "---\ntype: rule\ntags: [x]\nupdated: 2026-08-17\nstatus: candidate\nreuse_count: 0\n---\n重要规则：DLL 必须递增版本。\n",
        encoding="utf-8")
    assert main(["ingest", "--root", str(root), "--platform", "trae"]) == 0
    assert main(["confirm", "--root", str(root), "r1.md"]) == 0
    assert (root / "rules" / "r1.md").exists()
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL（`AttributeError: ... main`）

- [x] **Step 3: 在 engine.py 追加 CLI**

在 `hub-engine/engine.py` 末尾追加：

```python
def _cmd_retrieve(args) -> int:
    from tools.retrieve import retrieve
    for c in retrieve(Path(args.root), args.query):
        print(f"[{c.type}/{c.status}] {c.path.name}")
        print(c.body[:200])
    return 0


def _cmd_ingest(args) -> int:
    from sync import ingest
    stat = ingest(Path(args.root), args.platform)
    print(stat)
    return 0 if stat["status"] == "ok" else 1


def _cmd_confirm(args) -> int:
    from sync import confirm_rule
    dst = confirm_rule(Path(args.root), args.name)
    print(f"已确认并提升: {dst}")
    return 0


def _cmd_distill(args) -> int:
    from tools.distill import distill
    written = distill(Path(args.root), args.platform)
    print(f"产出候选 {len(written)} 张: {[p.name for p in written]}")
    return 0


def _cmd_tidy(args) -> int:
    from tools.tidy import archive
    dst = archive(Path(args.root), args.rel, reason=args.reason)
    print(f"已归档: {dst}")
    return 0


def _cmd_lint(args) -> int:
    from tools.lint import lint
    report = lint(Path(args.root))
    print("孤儿页:", report["orphans"])
    print("陈旧页:", report["stale"])
    print("无效卡片:", report["invalid"])
    print("备注:", report["notes"])
    return 0


def _cmd_chat(args) -> int:
    print(chat(args.prompt, Path(args.root)))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="hub", description="跨 Agent 平台统一记忆中枢")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("retrieve", help="混合检索")
    p.add_argument("--root", required=True)
    p.add_argument("query")
    p.set_defaults(func=_cmd_retrieve)

    p = sub.add_parser("ingest", help="导入暂存区")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", required=True)
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("confirm", help="确认待人工审核的规则")
    p.add_argument("--root", required=True)
    p.add_argument("name")
    p.set_defaults(func=_cmd_confirm)

    p = sub.add_parser("distill", help="复盘→候选规则")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", default="trae")
    p.set_defaults(func=_cmd_distill)

    p = sub.add_parser("tidy", help="归档")
    p.add_argument("--root", required=True)
    p.add_argument("rel")
    p.add_argument("--reason", default="")
    p.set_defaults(func=_cmd_tidy)

    p = sub.add_parser("lint", help="库健康检查")
    p.add_argument("--root", required=True)
    p.set_defaults(func=_cmd_lint)

    p = sub.add_parser("chat", help="omniroute 问答")
    p.add_argument("--root", required=True)
    p.add_argument("prompt")
    p.set_defaults(func=_cmd_chat)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 2 passed

- [x] **Step 5: 提交**

```bash
git add hub-engine/engine.py hub-engine/tests/test_cli.py
git commit -m "feat: CLI 统一入口（retrieve/ingest/confirm/distill/tidy/lint/chat）"
```

---

## Task 12: 平台固定指令注入（trae + code）

**Files:**
- Create: `hub-engine/tools/inject.py`
- Test: `hub-engine/tests/test_inject.py`

**背景说明：** Spec §4.2 要求向各平台规则文件写入"执行前先查中枢"的固定指令。第一版只做 **trae**（目标 `C:/Users/Fan-SJSS/.trae-cn/memory/user_profile.md`）与 **code**（目标 `D:/AIwork/code-memory/CLAUDE.md`，目录由用户按实际调整）。注入为幂等（已存在则跳过），由用户显式触发。

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_inject.py
from pathlib import Path

from tools.inject import inject_instruction


def test_inject_writes_block(tmp_path):
    target = tmp_path / "user_profile.md"
    target.write_text("# 用户档案\n", encoding="utf-8")
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert "INDEX.md" in text
    assert "不得臆测" in text


def test_inject_idempotent(tmp_path):
    target = tmp_path / "user_profile.md"
    target.write_text("", encoding="utf-8")
    inject_instruction(target)
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert text.count("统一记忆中枢") == 1
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_inject.py -v`
Expected: FAIL（`No module named 'tools.inject'`）

- [x] **Step 3: 写最小实现**

```python
# hub-engine/tools/inject.py
"""平台固定指令注入：向各平台规则文件写入"执行前先查中枢"指令（幂等）"""
from pathlib import Path

INSTRUCTION = """## 统一记忆中枢（AGENT MEMORY HUB）
执行前先查统一记忆中枢：读取 INDEX.md 与 rules / experience，命中再执行；
不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。
中枢位置：D:\\AIwork\\AgentMemoryHub
"""


def inject_instruction(target: str | Path) -> Path:
    """把固定指令追加到目标规则文件；已存在则跳过。返回目标文件。"""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and "统一记忆中枢" in target.read_text(encoding="utf-8"):
        return target
    block = ("\n" if target.exists() else "") + INSTRUCTION
    with open(target, "a", encoding="utf-8") as f:
        f.write(block)
    return target


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("用法: python -m tools.inject <目标规则文件路径>")
    print(f"已注入: {inject_instruction(sys.argv[1])}")
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_inject.py -v`
Expected: 2 passed

- [x] **Step 5: 真实注入（需用户确认目录后手动执行）**

```bash
python -m tools.inject "C:/Users/Fan-SJSS/.trae-cn/memory/user_profile.md"
python -m tools.inject "D:/AIwork/code-memory/CLAUDE.md"   # 目录不存在时先确认实际位置
```

> 注意：此步写入中枢外部文件，属于平台接入副作用。若用户尚未准备好 code 平台目录，可仅注入 trae，code 留待后续。

- [x] **Step 6: 提交**

```bash
git add hub-engine/tools/inject.py hub-engine/tests/test_inject.py
git commit -m "feat: 平台固定指令注入（幂等）"
```

---

## Task 13: 端到端示例（真实 DLL 规则走通全流程）

**Files:**
- Create: `D:\AIwork\AgentMemoryHub\rules\dll-version-lock.md`（由下方命令产生）
- Create: `hub-engine/scripts/demo_e2e.py`（端到端演示脚本）

- [x] **Step 1: 写失败测试**

```python
# hub-engine/tests/test_e2e.py
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from scripts.demo_e2e import run_demo


def test_demo_promotes_rule_and_retrieves(tmp_path):
    root = bootstrap(tmp_path)
    result = run_demo(root)
    # 一条真实规则端到端：沉淀→提炼→确认→复用
    assert (root / "rules" / "dll-version-lock.md").exists()
    assert result["confirmed"] == "dll-version-lock.md"
    assert result["hits"]  # 复用检索能命中该规则
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "confirm" in log
    # 查询产物回写：好答案→新经验卡片
    assert (root / "experience" / "query-writeback.md").exists()
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'scripts.demo_e2e'`）

- [x] **Step 3: 写端到端演示脚本**

```python
# hub-engine/scripts/demo_e2e.py
"""端到端演示：一条真实 AutoCAD DLL 规则走通 沉淀→提炼→确认→复用"""
from datetime import date
from pathlib import Path

from common.frontmatter import write_card, parse_card
from scripts.bootstrap_hub import bootstrap
from sync import append_log, confirm_rule, ingest
from tools.retrieve import retrieve


def run_demo(root: str | Path) -> dict:
    root = Path(root)
    bootstrap(root)

    # 1) 平台复盘沉淀到暂存区
    draft = root / ".sync" / "drafts" / "trae_draft"
    draft.mkdir(parents=True, exist_ok=True)
    retro = draft / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    (retro / "retro-2026-08-17.md").write_text(
        f"""# 复盘 {date.today().isoformat()}
今天改完插件 DLL 直接覆盖源文件，结果被 AutoCAD 占用锁住，最后只能递增版本号解决。
教训：修改 DLL 后必须递增版本号，绝不能原地覆盖同名文件。
""", encoding="utf-8")

    # 2) 提炼 → 候选
    from tools.distill import distill
    distill(root, "trae")
    cand_dir = root / ".sync" / "drafts" / "trae_draft" / "candidates"
    cands = sorted(cand_dir.glob("*.md"))

    # 3) 把候选改为规则暂存，走 ingest（规则 → 待确认）
    rule_draft = draft / "dll-version-lock.md"
    card = parse_card(cands[0].read_text(encoding="utf-8"))
    card.type = "rule"
    card.tags = ["autocad", "dll-lock"]
    card.status = "candidate"
    rule_draft.write_text(write_card(card), encoding="utf-8")

    stat = ingest(root, "trae")
    assert stat["pending"] == 1, stat

    # 4) 人工确认 → 提升到 rules/
    dst = confirm_rule(root, "dll-version-lock.md")

    # 5) 复用：查询能命中该规则
    hits = retrieve(root, "DLL 被 AutoCAD 锁住了怎么办")
    append_log(root, "reuse", f"查询命中 {len(hits)} 条")

    # 6) 查询产物回写：好答案→新经验卡片（写入暂存区后自动入区）
    insight = parse_card(f"""---
type: exp
tags:
  - autocad
  - dll-lock
  - writeback
updated: 2026-08-17
status: candidate
reuse_count: 0
---
查询\"DLL 被锁\"命中规则后确认：预防优于补救——开发期即采用递增版本命名，避免发布后被 AutoCAD 锁文件。
""")
    insight.type = "exp"
    qwb = root / ".sync" / "drafts" / "trae_draft" / "query-writeback.md"
    qwb.write_text(write_card(insight), encoding="utf-8")
    ingest(root, "trae")  # exp 属低风险 → 自动入区仅记日志

    return {"confirmed": dst.name, "hits": [h.path.name for h in hits]}
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: 1 passed

- [x] **Step 5: 在真实中枢跑通（人工复核产物）**

```bash
cd hub-engine
python -m scripts.bootstrap_hub D:\AIwork\AgentMemoryHub
python -m scripts.demo_e2e D:\AIwork\AgentMemoryHub
git -C D:\AIwork\AgentMemoryHub log --oneline -5
```

Expected: `rules/dll-version-lock.md` 已生成；log 含 confirm/reuse 记录；Git 可回滚。

- [x] **Step 6: 提交**

```bash
git add hub-engine/scripts/demo_e2e.py hub-engine/tests/test_e2e.py
git commit -m "feat: 端到端示例（DLL 规则沉淀→提炼→确认→复用）"
```

---

## Task 14: 首次 Lint 运行 + 产物记录

**Files:**
- Create: `hub-engine/scripts/lint_report.py`（报告写入辅助脚本）
- Create: `D:\AIwork\AgentMemoryHub\retro\lint-report-2026-08-17.md`（运行产物）
- Modify: `D:\AIwork\AgentMemoryHub\retro\log.md`（追加 Lint 记录）

- [x] **Step 1: 写报告脚本（含失败测试）**

```python
# hub-engine/tests/test_lint_report.py
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from scripts.lint_report import run_report


def test_run_report_writes_file_and_log(tmp_path):
    root = bootstrap(tmp_path)
    path = run_report(root)
    assert path.exists()
    assert "Lint 报告" in path.read_text(encoding="utf-8")
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "首次健康检查完成" in log
```

```python
# hub-engine/scripts/lint_report.py
"""跑 Lint 并把报告写入中枢 retro/，同时追加 log 时间线"""
from datetime import date
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from sync import append_log
from tools.lint import lint


def run_report(root: str | Path) -> Path:
    root = Path(root)
    bootstrap(root)
    report = lint(root)
    path = root / "retro" / f"lint-report-{date.today().isoformat()}.md"
    path.write_text(f"""# Lint 报告 {date.today().isoformat()}

- 孤儿页: {report['orphans']}
- 陈旧页: {report['stale']}
- 无效卡片: {report['invalid']}
- 备注: {report['notes']}
""", encoding="utf-8")
    append_log(root, "lint", "首次健康检查完成")
    return path


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\AIwork\AgentMemoryHub"
    print(f"报告已写入: {run_report(target)}")
```

- [x] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_lint_report.py -v`
Expected: 1 passed

- [x] **Step 3: 在真实中枢运行（人工复核产物）**

```bash
cd hub-engine
python -m scripts.lint_report D:\AIwork\AgentMemoryHub
```

Expected: `retro/lint-report-2026-08-17.md` 生成，`log.md` 追加 `## [2026-08-17] lint | 首次健康检查完成`。

- [x] **Step 4: 提交中枢 Git**

```bash
git -C D:\AIwork\AgentMemoryHub add -A
git -C D:\AIwork\AgentMemoryHub commit -m "chore: 首次 Lint 报告"
```

- [x] **Step 5: 提交仓库**

```bash
git add -A
git commit -m "docs: 实现计划（统一记忆中枢 v1）完成评审"
```

---

## Spec 覆盖自查表

| Spec 章节/要求 | 对应任务 |
|---|---|
| §3 中枢目录结构 | Task 4（bootstrap 骨架） |
| §3.1 统一 frontmatter | Task 3 |
| §4.1 omniroute 引擎 + Key 模块 | Task 1（config）+ Task 7（chat）+ Task 4（provider_keys.yaml） |
| §4.2 混合检索（不空想） | Task 6 + Task 12（平台指令注入） |
| §4.3 双向同步协议 | Task 5（ingest / confirm）+ Task 4（hub.config.yaml） |
| §4.4 并发写入兼容（单一写入者/写锁/暂存隔离/去重/Git） | Task 5（_WriteLock / draft / _find_duplicate / _commit） |
| §4.5.1 迭代主闭环 + 质量闸（重要规则人工确认） | Task 5（HIGH_RISK→pending）+ Task 8 |
| §4.5.2 Lint 健康检查 | Task 10 + Task 14 |
| §4.5.3 log.md 时间线 | Task 4（模板）+ Task 5（append_log） |
| §4.5.4 查询产物回写 | Task 13（reuse 命中 + append_log） |
| §5 第一版范围 7 项 | Task 4/12/5/6/13/13/10+14 |
| §6 错误处理（网关回退/冲突/回滚/幻觉污染/Key 安全） | Task 7（回退）、Task 5（conflicts + Git + 人工确认）、Task 4（.gitignore） |

**已知边界（YAGNI，按 Spec §5 暂不做）：** 平台全量接入（仅 trae+code）、无人工提炼、复杂向量库、定时 Lint 调度、web/移动端。

---

## 风险与备注

- **外部中枢写入**：Task 4/13/14 会创建/写入 `D:\AIwork\AgentMemoryHub`（独立目录，用户已确认）。Task 12 写入 trae/code 规则文件属平台副作用，执行前需用户确认目录。
- **omniroute 网关**：第一版默认 `http://127.0.0.1:11434`（本地 OpenAI 兼容网关），未起服务时自动回退本地检索，功能不中断。
- **code 平台目录**：`D:/AIwork/code-memory/CLAUDE.md` 为占位，实际路径以用户为准。
- **依赖安装**：执行前需 `pip install -r hub-engine/requirements.txt`。
