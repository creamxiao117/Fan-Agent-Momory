# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-23（启动链与规则门禁分层瘦身 · 分支 `optimize/slim-rules-gates` · **T14/T15/T16 已完成，待用户验收**）

## 当前状态快照

- 启动链曾 136K → **现测 23,326/30,000 PASS**（`cd hub-engine && python -m scripts.startup_budget` 退出码 0）。
- 方案：`docs/compose/specs/2026-09-23-slim-rules-gates-design.md`（S1–S5）；计划：`docs/compose/plans/2026-09-23-slim-rules-gates.md`。
- 分层：L0（AGENTS/CHARTER/WORK 当前态/根 INDEX 目录版）→ L1 四型（`hub-engine/tools/task_tier.py`）→ L2 检索。
- 安全底座常驻：单写者+§4 守护+ledger；query-first+交回用户+回写。
- 历史：`docs/superpowers/retro/work-history.md`；experience 索引：`AgentMemoryHub/INDEX-experience.md`（L2）。
- 实测分项：AGENTS 1416 / CHARTER 784 / WORK 本文件 / INDEX 18048。
  - 分项帽已于 2026-09-23 重配平为 AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000
    （和 29,000 ≤ 总帽 30,000，保持「分项帽之和 ≤ 总帽」不变量）。
- INDEX 描述已由「机械截断 10 字」改为**卡自身摘要**（边界断句 ≤40 字）；audit 由 27 项问题转为 ✅ 健康。

## 每日巡检状态（cron，独立于本迭代）

- 2026-09-23：**已修复，exit 0（全绿，健康度 92）**。原 13 处 Lint（invalid 12 + schema_drift 1）
  与弃用机制同一根因：卡首行 `<!-- DEPRECATED -->` 使 frontmatter 解析失败 ⇒ 被计入 invalid。
  改为显式 `status: deprecated` 后：invalid 8→0、schema_drift 1→0、lint 退出码 2→0。
- 编码门禁：FAIL 2→0（两份「以乱码为主题」的卡属误报，已加豁免）；BOM WARN 19→0。

## 活跃待办（本迭代）

| # | 任务 | 状态 |
| -- | --- | --- |
| A1 | startup_budget 门禁+单测 | 完成（1b709a0） |
| A2 | AGENTS 路由+CHARTER 压缩 | 完成（d3b8b3e+ca31e31） |
| A3 | WORK 当前态+历史归档 | 完成（db3d52e+33659c1） |
| A4 | INDEX 目录化+experience 拆分 | 完成（外层 da9f3c0 / 中枢 8556c53）；根 INDEX≤14K |
| A5 | rules tier+长卡拆分+inject 瘦身 | **完成**（外层 6884b9b / 中枢 f5eca53）；T14 双审已完成并修复所发现的缺陷 |
| B1 | backup+方法论合并+经验去重 | **完成**（T15）；合并早已完成且内容完整性已逐张验证；experience 220 张仅 1 组真重复已作废 |
| 收口 | 预算 PASS + 全量 pytest + ruff + 挂巡检 | **完成**（T16）：预算 23,326/30,000 PASS；pytest 393 通过/0 失败；ruff 绿；巡检已挂 `startup_budget` 步 |

## 已完成提交索引（外层 `optimize/slim-rules-gates`）

- 计划/spec：d3d633e, bc620e2, 40874f0, e7c05c6, 1315f55, 23e3b60
- T1–T6：1b709a0, ac132cc, fcfcffe, d3b8b3e, ca31e31, db3d52e, 33659c1, da9f3c0, 6884b9b
- T14–T16（本轮）：cb5a982（弃用显式化+L1 路由+弃用语义测试）、42be706（INDEX 卡摘要+边界断句+BOM 容错+帽配平）、3088b90（strip_bom+乱码豁免）、1797373（破坏性脚本护栏）
- 中枢仓 AgentMemoryHub：8556c53（INDEX 拆分）、f5eca53（rules tier+拆卡）、e462e5b+d4076d5（弃用显式化 2 笔）、68088fa（INDEX 卡摘要+补登记）、217acde（巡检产物）、e39127b（剥离 19 个 BOM）、c56d7db（作废 ingest-probe-a）

## 遗留待办（不阻塞收口）

- **19 个 .md 曾带 BOM 已剥离**；`extract_summary` 已改 `utf-8-sig` 容错，不会再产生空摘要。
- English 长标题类蓝图卡的 INDEX 摘要仍会硬切（11 条，无中文可断点）——可接受。
- `slim_index.py` 未接入任何流水线（仅手工工具），已改为边界断句防再次切出半截词。

## 下一 Agent 必做（本迭代已收口）

1. 读本文件 + spec + plan；确认分支 `optimize/slim-rules-gates`。
2. 本迭代 T14/T15/T16 已完成，等待用户验收；如需合并回 `master` 请先跑一次
   `cd hub-engine && python -m pytest`（基线已无失败）+ `python -m scripts.startup_budget`。
3. **勿执行 `scripts/merge-methodology.py` / `scripts/deduplicate-experience.py`**：
   两者已加拒绝护栏（实测会截断/误杀，详见脚本头部注释）。
4. 巡检脏文件（`RUNLOG.md` / `AgentMemoryHub/retro/snapshot-*.json`）单独分笔提交。
5. 勿提交 `nul`（已清除的幽灵条目）。

## T14 双审结论（已审）

- **规格审：通过**。tier iron 3 / task 29 / ref 3；三长卡核心 1303/1058/1140（均 ≤spec 的 1.5K）；
  inject 只注 L0 铁律+四型路由+检索一句（test_inject 6/6）；拆卡内容完整（附录含全部小节）。
- **质量审：发现 1 缺陷 + 2 隐患，均已修**：
  1. A5 加 `tier:` 时把 4 张作废卡的 DEPRECATED 注释下移 ⇒ 它们**复活进检索库**。
     根因是「注释在第几行」隐式决定可索引性 ⇒ 已重构为显式 `status: deprecated`。
  2. `test_inject` 一处断言测的是**从未存在过的字符串**（永远为真）⇒ 已换成真实片段+长度帽。
  3. 两引擎 status 口径不一（项目 `VALID_STATUS` 无 deprecated、只认 archived）⇒ 已统一。
- 备份：`AgentMemoryHub/.backup/20260923/manifest.txt`；内容完整性核对：`work/verify_merge_fidelity.py`

## 验收口径

- `python -m scripts.startup_budget` 退出码 0（**已满足**：L0 24,402/30,000）
- **L0 四文件字符**：AGENTS≤2500 CHARTER≤1500 WORK≤5000 INDEX≤20000，**且四者之和 ≤ 总帽 30,000**
  （已满足；不变量由 `tests/test_startup_budget.py` 看守）
- **L1 二任务型补读量 ≤15,000**（2026-09-23 新增门禁；spec S2 曾声明但无人看守）：
  实测 light 0 / code 8,663 / hub 8,814 / sync 6,874，均 OK；
  **L1 卡名解析不到文件也算违规**（路由悬空比超预算更危险）
- `cd hub-engine && .venv\Scripts\python.exe -m pytest`：**402 通过 / 4 跳过 / 0 失败**（基线 4 败已消失）
- ruff 绿
- L0 六条铁律（概念断言已加进 `tests/test_inject.py`）；INDEX 无 10 字半截词；改码型 L1 含编码核心卡名
- **门禁必须真的在跑**（不只是"代码里有"）：定时任务 `AgentHub-DailyPatrol` 每日 07:30
  跑 `scripts/run_patrol.cmd` → `patrol_runner`；已实测触发成功（LastTaskResult=0，
  日志内可见 `✅ startup_budget`）
- 弃用语义：`status: deprecated` 被两引擎一致排除（`tests/test_deprecation_semantics.py`）

## 上一轮遗留（须人工裁定，非本迭代引入）

见归档「待用户裁定」四修（vector_bench 夹具 / patrol fail-below / _norm_path CWD / RRF 保底）——本迭代不擅自改。

## 环境备忘

- **解释器：必须用 `.venv\Scripts\python.exe` 跑 pytest（重要，与旧备注相反）**。
  2026-09-23 实测：系统 python **缺 jieba**，会让 9 个检索/分词测试**静默跳过**——
  即「假绿」。对比：系统 python `393 passed / 13 skipped` vs `.venv` **`402 passed / 4 skipped`**；
  剩下的 4 个 skip 是 mcp 未装，与本议题无关。
  巡检启动器（`scripts/run_patrol.cmd`）已硬编码 `.venv`，并会在缺失时以 127 退出。
- LM Studio 1234 / embed 对齐 bge 配置以 `AgentMemoryHub/system/config.yaml` 为准（它是生效单源；
  `hub-engine/config/engine.config.yaml` 仅兜底，改它看不到效果）。
- `AgentMemoryHub` 为嵌套 git 且被外层 gitignore——中枢卡必须 `git -C AgentMemoryHub` 提交。
