# 各平台「任务级能力装配」可行性调研（M3/Task 19 · 前置门）

- 日期：2026-10-02
- 性质：**前置门**（M3/Task 21 能不能做、做到哪一步，取决于本调研结论）
- 关联：`docs/compose/specs/2026-10-02-hub-capability-memory-architecture.md` §5.3、`hub-engine/tools/capability_router.py`

## 要回答的问题

用户诉求：**常用能力常驻装；不常用的/特定的，在任务建立初期按任务计划临时安装，任务结束卸载**
（也可任务中途发现缺口再补装）。这要求客户端支持「**任务级（或项目级）能力作用域**」——
即"这个能力只在本项目/本任务可见，不进入全局常驻"。

## 结论表（2026-10-02 实测/文档核查）

| 平台 | 任务级/项目级配置 | 证据 | 判定 |
|---|---|---|---|
| **pi** | ✅ **项目级 `.pi/`**：`settings.json`/`extensions/`/`skills/`/`prompts/`/`AGENTS.md`/`APPEND_SYSTEM.md`，且 MCP 可走项目 `.mcp.json` | pi 官方文档 `configuration.md`「Project `.pi` directory」表 + `mcp.json` 查找顺序（`.mcp.json` 为 project 配置） | **可做全环**（装→用→卸） |
| trae | ❓ 未发现任务级配置；`~/.trae-cn/mcp.json` 与 skills 目录均为**用户级** | `hub.config.yaml` 登记的路径皆是 HOME 级 | **不可做**，退化为 session 级提示 |
| workbuddy | ❓ 同上（`.workbuddy/mcp.json`、`.workbuddy/skills` 皆为用户级） | 同上 | **不可做** |
| mavis | ❓ 三层机制（hook + memory topic + workspace AGENTS.md）里只有 **workspace AGENTS.md** 是项目级 | `methodology/mavis-as-5th-platform.md` | **部分**（只能项目级注入指令，不能装卸能力） |
| deepseek (DSH) | ❓ 配置在 `cordis.patch.yml`（用户级） | `rules/dsh-patch-driven-plugin.md` | **不可做** |
| hermes | ❓ 配置在 `AppData/Local/hermes/config.yaml`（用户级） | `hub.config.yaml` | **不可做** |

## 因此 M3/Task 21 的实际范围

1. **pi 走全环**：项目级 `.pi/skills/`（+ 项目 `.mcp.json`）作为 task scope 落点；
   `install` → `verify` → 任务结束 `remove` → `verify`，每步都要**证据**。
2. **其他平台退化为两层**：
   - **建议层**（已可用，与平台无关）：`tier-bootstrap` 在任务开头返回
     `capabilities.{installed, suggested, missing}`，附 `why`（命中了哪些触发词）
   - **提示层**：状态栏/通知提醒"本任务建议装 X（当前未装）"，由人决定是否改客户端配置
   - **结算层**：无法自动卸载 ⇒ 改为**巡检残留检测**（`deploy_scope=task` 超期未结算 → warn）

## 未验证项（诚实标注，不要当成已确认）

- trae / workbuddy / mavis / dsh / hermes 是否**存在未公开的项目级配置**：未逐个体检客户端文档，
  仅从"本机配置路径都是用户级"这一事实推断。**若要推进，需逐平台查官方文档**。
- pi 的 `.mcp.json`（项目级）与 `<agent-dir>/mcp.json`（用户级 override）的**优先级与合并语义**
  未实测；M3/Task 21 先在**技能**维度做全环（技能是纯文件复制，语义简单、可 verify）。

## 预算联动（Task 18 的棘轮帽）

临时安装的能力 **`deploy_scope=task` 时不计入常驻成本帽**（它们不该每次会话都付），
但**必须有人结算**：任务结束未卸载 ⇒ 它们事实上变成了常驻 ⇒ 巡检需把它们计入并告警。
这条是"临时装→永久装"退化的唯一防线。
