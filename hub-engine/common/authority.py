# @version V1.0 / 2026-10-05 / pi / 权威区目录的**唯一事实源**
"""权威区 / 非权威区 / 卡片目录 / 目录↔type 的**唯一字面量来源**（2026-10-05 立）。

## 为什么要有这个模块

此前 `authority_dirs` 有 **6 份副本、4 种内容**，而 `hub.config.yaml` 的那份
**没有任何消费方**（`common/config.py::HubConfig` 只暴露 `platforms` / `draft_dir`）
⇒ "声明的单一事实源"形同虚设。2026-10-05 体检实测到的漂移与其后果：

| 副本 | 当时内容 | 后果 |
|---|---|---|
| `tools/lint.py` | 5 权威区（**缺 experience**） | 236 张 experience 卡**不参与孤儿/陈旧判定**（潜在盲区） |
| `scripts/index_consistency.py` | 同上（缺 experience） | 注释自称"与 hub.config.yaml 对齐"，**实际不对齐** |
| `tools/mcp_policy.py` | 5 权威区 + **libs** + **retro** | slug 解析可落到 `retro/log.md` 等**非卡片文件**（越权面） |
| `scripts/metrics_daily.py` | + **libs** + **retro** | `_total_cards()` 把 libs/retro 的 md 计成卡片（指标虚高） |
| `scripts/secret_sentry.py` | 5 权威区 + experience + **notes** | `notes` 不被检索/注入，却按"高危区"扫描（误报） |

同时 `engine.py status` 的卡片分布与 `engine.py audit` 的"权威区文件数"都直接源自
`tools/lint.py::AUTHORITY_DIRS`，故上表第一行也让这两处**永久漏掉 experience**
（audit 打出「INDEX 条目 520 / 权威区文件 284」的自相矛盾）。

## 口径（不要各自再写一份）

- `AUTHORITY_DIRS`   —— 五权威区 + `experience`，与 `hub.config.yaml` 的 `authority_dirs` **逐项一致**
  （experience 于 2026-09-10 由 Fan 拍板升级进权威区）
- `NON_AUTHORITY_DIRS` —— `notes` / `retro`，不参与去重/向量/检索主流程，但**保留可检索/可登记**
  （见 `tools/lint.py` 的 `_NON_AUTH_INDEX_DIRS` 注释：指向它们的 INDEX 登记不是幽灵）
- `CARD_DIRS` —— 参与派生（INDEX 渲染、向量）的目录；与检索口径同源
- `DIR2TYPE` —— 目录 → 期望 `type`（目录为准，供 lint 的 type↔目录 维度）

`hub.config.yaml` 仍是**人读的口径文档**；它与本模块的一致性由
`tests/test_authority_single_source.py` 看守（改一处漏另一处即红）。
"""

from __future__ import annotations

# 五权威区 + experience（顺序与 hub.config.yaml 的 authority_dirs 声明顺序一致）
AUTHORITY_DIRS: tuple[str, ...] = (
    "rules",
    "blueprints",
    "methodology",
    "longterm",
    "projects",
    "experience",
)

# 非权威区：不参与孤儿/陈旧判定，但保留 INDEX 登记与检索白名单语义
NON_AUTHORITY_DIRS: tuple[str, ...] = ("notes", "retro")

# 参与派生的目录（INDEX 渲染 + 向量 + 检索）
# 顺序固定为检索口径（tools/retrieve.py::_ACTIVE_DIRS 的历史顺序），不要随手重排。
CARD_DIRS: tuple[str, ...] = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "blueprints",
    "experience",
)

# 目录 → 期望 type。依据见 tools/lint.py::find_type_dir_mismatch 的 docstring：
# type 只用于 sync/confirm 路由，目录才是检索分区，二者不一致会让卡被确认到错目录。
DIR2TYPE: dict[str, str] = {
    "rules": "rule",
    "blueprints": "blueprint",
    "methodology": "methodology",
    "longterm": "longterm",
    "projects": "project",
    "experience": "exp",
    "notes": "note",
    "retro": "retro",
}
