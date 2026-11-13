# 中枢任务包（交 Hermes 统一处理 · 2026-11-13）

> **分工**：中枢仓（AgentMemoryHub）的维护者是 **Hermes**（ingest / build-vectors / sync / 推中枢仓）。
> 本轮我把中枢仓的**推送权**交回 Hermes ⇒ 中枢侧改动一律由 Hermes 统一执行。
> 引擎侧（hub-engine）已在外层仓落地并推送，**不需要 Hermes 动手**。
> **本包性质**：可执行任务清单（做什么 / 为什么 / 值多少 / 做完怎么验收），不是建议稿。

## 0. 一句话状态

| 面 | 状态 |
| --- | --- |
| 引擎侧 hub-engine | ✅ 已落地并推送：`ec78c36`（提交自洽·根治 l0 死锁）· `a7a9b54`（体量告警预算）· `6c5e09e`（post_ingest_hook 同源治本） |
| 中枢侧 AgentMemoryHub | ⏳ **本地领先 origin/master 56 个提交，未推**（含维护者自己的 40+ 提交）⇒ §1.1 |
| 平台体量告警 | 🟡 机制就绪、**只差一个数** ⇒ §1.2 |
| hermes 动态约束 | 🔴 **hermes 仓里目前不存在**（只读调查逐项确认）⇒ §3 给出落刀位置 |

## 1. 请 Hermes 立即执行（按序）

### 1.1 推中枢仓（56 个本地提交）

```powershell
git -C AgentMemoryHub push origin master
```

- `origin` = `git@github.com:creamxiao117/AgentMemoryHub.git`，`master` 当前 **ahead 56**（origin/master 停在 `fbcbf5f`）。
- 这 56 个提交里包含维护者自己近几天的产物（星链/晨报/能力账本/平台回写留痕）⇒ **不是我单方面的改动**，推之前请自行过一眼 `git log origin/master..HEAD`。
- 本轮我加的 4 个：`e2fbef5`（卡：平台记忆必须先查消费端）· `fd9cc93`（hub.config.yaml 字段语义注释）· `f3787ae`（卡：提交自洽纪律）· `a709f26`（mavis 平台 push 留痕）。
- 推前自检（当前实测已 PASS，可直接推）：
  `python -m scripts.render_index --root AgentMemoryHub --check` ⇒ PASS
  `python engine.py audit --root AgentMemoryHub` ⇒ **700/700 ✅**

### 1.2 `hub.config.yaml`：给 mavis 加告警线（值已算好，直接用）

> ✅ **2026-11-13 14:1x 实测：hermes 已在执行本节** —— `hub.config.yaml` 的 mavis 段已写入同值 `memory_char_warn_limit: 58000`（含同样的取值理由注释）⇒ **本节只需确认，不必重复改**。

在 `platforms.mavis` 段加一行：

```yaml
  mavis:
    ...
    # ⚑ 平台级**告警预算**（只报不拦）：超限照常写入 + stat["warnings"] + retro/log.md 留痕
    memory_char_warn_limit: 58000
```

**取值理由**（实测 2026-11-13 14:03，整文件字符数口径）：

| 候选 | 值 | 评价 |
| --- | --- | --- |
| 当前体量 | 52,440 | 立即误报 ⇒ 不可用 |
| 理论下限 | 52,441 | **每次 push 都报** ⇒ 噪音 ⇒ 探针被无视（比没有探针更坏）⇒ 不取 |
| **本次取值** | **58,000** | = 当前 + 5,560（**+10.6% 增长预算**）：一轮批量入库不报，越过即报警 |

- 单位 = **字符**，与 `memory_char_limit` 同口径（hub 侧按 `len(text)` 计）。
- **只先开 mavis 一个平台**（其余 4 个无消费端上限的平台暂不开）：一次布 5 条静态探针 = 5 处噪音源 + 5 个将来都要棘轮上调的数；先用这一条线校准「触发体验 + 棘轮策略」，再按 §2.1 的基线表逐个推广。
- 语义**不变**：超限只报不拦（照常写入）；**声明了但非法 ⇒ fail-closed 拒绝写入**（用户已裁定按此执行）。

### 1.3 改完 `hub.config.yaml` 必须跑 `capability_scan --write`

（WORK.md 既有规矩：否则巡检 reconcile 步报「账本与实测态不一致」。）

### 1.4 台账重渲（当前中枢门禁**唯一**红项）

> ✅ **2026-11-13 14:1x 实测：hermes 已在执行本节** —— `scripts/INVENTORY.json` 已被重渲（工作树已变更）⇒ **只需确认并提交**。

```powershell
python -m scripts.inventory --write
```

- 起因：`scripts/capability_reconcile.py`（维护者**未提交**的改动）新增了 `capability_events.jsonl` 字面量
  ⇒ 产物台账与磁盘不一致 ⇒ `tests/test_inventory.py::test_real_ledger_is_current` 失败
  ⇒ `engine.py gate` 恒红（exit 11；pytest 940 passed / 1 failed）。
- 逐行取证：台账差异**只有一行**（`scripts/capability_reconcile` 的 artifacts 字段），其余模块 added/removed 均为空。
- ⚠ 该文件仍在被修改中 ⇒ **重渲要放在改动完成之后**，否则又会漂移。

## 2. 给 Hermes 动态约束的体量基线（同口径，可直接取用）

### 2.1 各平台当前体量（2026-11-13 14:03 实测）

| 平台 | 记忆文件 | 字符数 | 字节数 | 消费端加载上限 | 消费端已核验？ |
| --- | --- | --- | --- | --- | --- |
| hermes | `%LOCALAPPDATA%\hermes\memories\MEMORY.md` | 14,287 | 24,706 B | 16,000 | ✅ 已核验一致 |
| mavis | `~/.mavis/memories/MEMORY.md` | 52,440 | 94,498 B | — | ❌ **无消费端**（中枢镜像） |
| code | `~/.codex/AGENTS.md` | 52,064 | 82,542 B | — | ❌ 未核验 ⇒ 不得声明 |
| workbuddy | `~/.workbuddy/MEMORY.md` | 40,300 | 64,342 B | — | ❌ 未核验 ⇒ 不得声明 |
| deepseek | `~/.dsh/memories/MEMORY.md` | 17,609 | 28,929 B | — | ❌ 未核验 ⇒ 不得声明 |
| pi | `PiAgent\agent\AGENTS.md` | 16,699 | 27,101 B | — | ❌ 未核验 ⇒ 不得声明 |

- **mavis 无消费端是实测结论**：`app.asar`（371,919,371 B）字节级扫描 `.mavis/memories` 与 `memories/MEMORY` 均 count 0；
  MiniMax Code 真实记忆路径是 `{{DATA_DIR}}/memory/user.md` 与 `{{DATA_DIR}}/agents/<name>/memory/MEMORY.md` ⇒ 该文件本质是**中枢镜像**。
- 其余 4 个平台**尚未逐一取证**（与 mavis 同款理由，但没扫）⇒ 一律**不得**声明 `memory_char_limit`。

### 2.2 口径（**必须**对齐，否则两边各算各的）

- **中枢闸现在算的是「整文件长度」**（hub 侧 `len(text)`）；
- **hermes 消费端算的是「条目拼接长度」**：`len("\n§\n".join([e.strip() for e in raw.split("\n§\n") if e.strip()]))`
  （= `tools/memory_tool_store.py:309 _char_count`；磁盘是 CRLF，Python 侧 `read_text(encoding="utf-8-sig")` 会归一 ⇒ **磁盘文件长度 ≠ hermes 计数**）。
- 当前实测差 ≈ **355 字符**（MEMORY.md 整文件 14,643 vs hermes 口径 14,288）。
- ⇒ **中枢喂给 hermes 的基线值必须用 hermes 口径**（否则 hermes 拿到的基线偏大 355，动态判定整体偏松）。
- 中枢闸用整文件长度 ⇒ 偏**紧**（更早触发）⇒ 方向安全，但两边口径要在文档里写明，别互相引用对方的数。

### 2.3 现状告急（两处，写在这里免得漏）

| 项 | 实测 | 占用 | 余量 |
| --- | --- | --- | --- |
| hermes `MEMORY.md` | 14,287 字符（hermes 口径）/ 上限 16,000 | **89.3%** | 1,712 字符 |
| hermes `USER.md` | 1,469 字符（14 条目）/ 上限 1,500 | **97.9%** | **仅 31 字符** |

- `USER.md` 只剩 31 字符 ⇒ **下一次写用户记忆几乎必然被拒**（`user_char_limit` 超限即拒绝写入）。
- `MEMORY.md` 在本会话上午→14:03 之间从 12,045 涨到 14,287（**+2,242 字符**）⇒ 按同速率约数小时触顶 ⇒ 动态约束不是锦上添花，是**已经逼近硬限**。
- ⚠ `USER.md` 由 hermes 自己写，**中枢闸管不到**（hub 只推 `MEMORY.md`）⇒ 属 hermes 侧处置范围。

## 3. hermes 动态约束：落刀位置与参数（只读调查结论）

### 3.1 现状：**不存在**

两个 checkout（主 `223de1625a3` / PR worktree `5aceb46210f`）+ 上游 `origin/main` 全部逐项排查：
工作树干净、无未跟踪文件、无相关 stash/分支/提交；关键词 `dynamic|growth|soft_limit|warn_limit|headroom|per_hour|max_entries|threshold|prune|trim` 全仓搜**无一处与记忆体量相关**。
hermes 侧现有的「软」机制都不是体量约束：加载期超限只告警不拦（`memory_tool_store.py:250`）、每轮合并失败封顶 3 次、后台记忆审查（`nudge_interval`）。

### 3.2 唯一落刀点：**`tools/memory_tool_store.py:312 _char_limit()`**

- 它是**唯一**的上限来源；4 个判定点（`:380` add / `:431` patch / `:482` replace / `:593` batch 终态）全部经它传下去
  ⇒ 把它从「固定 int」换成「动态上限计算」⇒ **所有写路径自动统一口径**，**不要新开一条旁路**。
- 两个构造点都要接，否则网关与 CLI 口径打架：`agent/agent_init.py:1336`、`tools/memory_tool.py:56`。

### 3.3 参数建议

| 参数名 | 语义 | 落点 |
| --- | --- | --- |
| `memory_char_baseline` | **中枢提供的当前体量参考值**（hermes 口径）⇒ 用来算增量，不是算上限 | 两个构造点从 `mem_config` 读；或从 `memories/.memory_baseline.json` 惰性读（中枢写，免重启） |
| `memory_growth_limit` | 一个窗口内允许的最大**增量**（字符）⇒ 总量不再有死上限，只卡「快速膨胀」 | 同上；判定收在 `_char_limit` 内 |
| `memory_growth_window_seconds` | 增量窗口长度 | 同上 |
| `memory_char_warn_limit` | 只报不拦的软预算（**与中枢同名字段** ⇒ 天然同口径） | hermes 侧命中时在写入结果里带告警而非拒绝 |

- 窗口增量需要落盘快照（中枢直写 MEMORY.md **绕过** memory 工具 ⇒ hermes 的内存计数看不到那次写入）
  ⇒ 做法：**每次写/加载时重算文件体量并落一份快照**。

### 3.4 可照搬的范式（中枢自己就有现成实现）

`hub-engine/scripts/capability_reconcile.py:891-1000`（月度体检）已经是「基线 + 膨胀检测 + 只降不升」的完整范式：
基线择优（同月「上次运行」快照 > 上月留痕）· `delta`/`delta_pct`/`bloat` 标记 · `suggested_target = min(base, cur)`（**只降不升**）· 状态文件 `capability_budget_review-last.json`。
对应方法论卡：`AgentMemoryHub/methodology/2026-11-13-soft-target-per-platform-monthly-review.md`。
⇒ 记忆体量的动态约束**照这个范式做**即可，不必另发明。

### 3.5 中枢侧的反向对应（**改完动态约束后要做**）

一旦 hermes 改成动态（无固定上限），中枢的 `platforms.hermes.memory_char_limit: 16000`（阻断式）就**失去语义依据**
（它代表「消费端加载上限」，而消费端不再有固定上限）⇒ hermes 平台应切到 `memory_char_warn_limit`（只报不拦），
**阻断责任移交消费端的动态约束**。注意：中枢推 hermes 平台记忆时，hub 侧算的是整文件长度，比消费端口径多 355 ⇒ 切 warn 后这一层差异不再是安全余量，需按 §2.2 重新对齐。

## 4. 语义边界（三个字段别混）

| 字段 | 语义 | 超限行为 | 谁能声明 |
| --- | --- | --- | --- |
| `memory_char_limit` | **消费端自己的加载上限** | **拒绝写入**（阻断） | 仅能**核验**消费端上限的平台（现只有 hermes） |
| `memory_char_warn_limit` | **hub 侧自设预算** | **照常写入 + 结构化告警 + retro/log.md 留痕** | 消费端上限无法核验者 |
| 声明了但非法 | 配置错误 | **fail-closed 拒绝写入** | —— |

- ⚑ **无消费端的平台不得声明 `memory_char_limit`**（声明未核验的上限 = 把猜测伪装成已核验）。
- 告警 ≠ 阻断：hub 侧只报；真要拦，必须落在**消费端**（hermes 动态约束）。

## 4.5 两个必须知道的耦合（2026-11-13 实测踩到）

1. **外层仓的 l0 门禁校验的是中枢「活体工作树」**：
   `gate_runner.py::gate_l0` 对 `repo=outer` 不物化 index，直接跑 `scripts.render_index --check`（默认根 = 中枢）
   ⇒ **中枢只要有在途卡改动（哪怕是维护者自己的暂存），外层仓任何触及 L0 面（`AGENTS.md`/`CHARTER.md`/`WORK.md`/…）的提交都会被挡**。
   ⇒ 中枢改完卡要 `render_index --write`（或等维护者自己跑），否则外层仓的提交会被 l0 拦住。
   （2026-11-13 实测：hermes 正在改 `rules/global-rules.md`（GR 标题中文化）⇒ 渲染产物陈旧 ⇒ 外层仓提交被挡 exit 3；重渲后即放行。）
2. **外层仓 `WORK.md` 有 5,000 字符分项帽**（`startup_budget`）⇒ 它已是「只装状态 + 待办指针」的文件：
   轮次细节归 `RUNLOG.md`、已完成项的判据明细归各自的 metrics/report 文档 ⇒ 往 WORK.md 加长内容前先压缩已达成项。
   （2026-11-13 实测：加 3 行即越帽（5,641 > 5,000）⇒ 压缩已达成项（A4/A5–A7/A8/T1 判据）后回到 4,942；顺带修掉两处**粘连的表格行**（A8 行与「### T1 判据」标题被粘在前一行）⇒ markdownlint MD055/MD058 少 1 处。）

## 5. 中枢侧其余待办（登记在册，不急）

1. **ingest 提交失败后卡滞留工作树** ⇒ 下一轮 protect 快照会保护它们 ⇒ 需人工收口（未修）。
2. **无闸暴露面**：mavis/code/workbuddy/deepseek/pi 各自 680–690 张卡待推，hermes 同卡集投影 **180 万字符**
   ⇒ 若全量推，无闸平台会被灌到百万字符量级。可选方案：中枢加「**只推指针**」模式（当前中枢无此能力）。
3. **告警线的棘轮语义**：静态告警线 ⇒ 体量涨到线上后恒告警 ⇒ 需要一个「按实测抬线」的棘轮规则（用户已知悉，尚未拍板）。
4. **平台体量基线漂移**：§2.1 的数会随每次 push 变 ⇒ 建议纳入巡检刷新（照 §3.4 的快照范式）。

## 6. 验收口径（Hermes 执行后应达到）

- [ ] `git -C AgentMemoryHub push origin master` 成功，`origin/master..HEAD` 为空。
- [ ] `platforms.mavis.memory_char_warn_limit: 58000` 已写入 `hub.config.yaml`，且 `capability_scan --write` 已跑。
- [ ] `python -m scripts.inventory --write` 已跑 ⇒ `tests/test_inventory.py::test_real_ledger_is_current` 绿。
- [ ] `python engine.py gate --root AgentMemoryHub` ⇒ **全绿（exit 0）**。
- [ ] `python engine.py audit --root AgentMemoryHub` ⇒ 700/700 ✅。
- [ ] 若已切 hermes 动态约束：hermes 侧 `_char_limit()` 不再是固定 int，且 §3.3 四个参数可配。

## 7. 附：引擎侧已闭合（供引用，不必重做）

| 提交 | 内容 |
| --- | --- |
| `ec78c36` | 提交自洽：临时索引精确提交 + 提交树渲染 INDEX + 暂存区自愈 ⇒ 根治 l0 门禁死锁（判据是**暂存态**） |
| `a7a9b54` | 平台体量告警预算 `memory_char_warn_limit`（只报不拦），非法值 fail-closed |
| `6c5e09e` | `post_ingest_hook` 改走 scoped 提交（同一根因的第二个入口） |

- 对应中枢卡：`2026-11-13-platform-memory-consumer-check-and-warn-budget`（消费端先查）· `2026-11-13-commit-self-consistency-scoped-commit`（提交自洽）。
