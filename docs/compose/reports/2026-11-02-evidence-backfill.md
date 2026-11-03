# 存量 evidence 回填裁定表（2026-11-02）

> 判据：**v5**（`docs/compose/reports/2026-11-02-evidence-axis.md` 记录了 v1→v5 的迭代与每版被打回的原因）。
> 抽样人工核验：18/18 成立；已知边界见文末。
> 本次回填 **149 张**（t1=92 · measured=57）；其余卡**不写**（缺失即 none，避免无意义改写）。

| 卡 | grade | evidence | 依据（节 → 命中行） |
| -- | -- | -- | -- |
| `rules/chinese-text-encoding-discipline-appendix` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-09-20（本卡自带 4 条 | | 结论 | ✅ **PASS**（5/5 核心判据，且**红的原因已核**）| |
| `rules/chinese-text-encoding-discipline` | iron | **t1** | T1 小节自证：## T1 验证（2026-09-29，沙盒 chinese-t | - 结果：**✅ 4/4 PASS**（`t1_demo.py` 逐条验证卡内判别式与环节1 规则）。 |
| `rules/rules-routing-table` | proven | **t1** | T1 小节自证：## T1 验证（2026-10-10，F:\AgentMemo | **结果：⚠️ 部分（11 项断言 10 绿 1 红）** —— 纯只读断言脚本 `t1_routing_table.p |
| `methodology/2026-09-10-refactor-judgment-fanout-not-loc` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-10-08（ | | 结论 | ✅ 通过（判据可脚本化 + 有区分度） | |
| `methodology/2026-09-26-gate-fix-prove-red-then-green` | proven | **t1** | T1 小节自证：## T1 迭代验证（2026-09-27）✅ | ② **绿**（good.md 合规）→ exit 0（仅 tags 空软告警不阻断——错误/告警分层符合设计）。 |
| `methodology/acceptance-net-self-audit-criteria-redlines` | pitfall | **t1** | T1 小节自证：## T1 验证（2026-10-06，沙盒 `F:\Agent | - 结果：**✅ 8/8 PASS**（`selftest.py`，零安装、纯标准库）。 |
| `methodology/autocad-dotnet-plugin-skeleton-methodology` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-10-17（沙盒编译 + 红 | | T1-1 net48+x64 骨架 `dotnet build -p:AcadVersion=2020` | ✅ 0 |
| `methodology/autocad-plugin-testing` | proven | **measured** | 验证小节自证：### 阶段 3：引擎验证（Layer 2/3） | 12. 若 COM 死锁 → 跳回阶段 1/2 结果 |
| `methodology/benchmarkdotnet-performance-benchmarking-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-10-13，cron star-di | **结果：✅ 通过** ⇒ `status: reference → active`，`reuse_count` +1。 |
| `methodology/checker-must-be-provably-red` | pitfall | **measured** | 验证小节自证：## 一句话结论 | 打印 PASS 的检查器如果不曾被证明能 FAIL，它提供的是假信心 —— 比没有检查器更糟。 |
| `methodology/gh-star-repo-filter-rule` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-10-04（cron 无人值 | | F1 文件数 ≤ 8k | **GitHub trees API `git/trees/HEAD?recursive |
| `methodology/llm-dedup-gateway-degrade-fix` | proven | **t1** | T1 小节自证：## T1 迭代验证（复验）— 2026-09-15 | **对照探针（同机同刻）**：`engine._local_chat(prompt, hub)` 与 `engine.s |
| `methodology/mcp-hub-mount-guaranteed-retrieval` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-28 | | `list_tools` 返回 7 个 `hub_` 工具 | `tools=7, hub_ tools=7`：an |
| `methodology/pandoc-document-conversion-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-10-17（沙盒 zip 免 | | T1-1 版本 | ✅ pandoc 3.12.1，Features: `+server +lua` | |
| `methodology/pytest-python-test-framework-methodology` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-02 | | 结论 | ✅ 通过 | |
| `methodology/skillhub-tool-to-skill-registration-workflow` | proven | **t1** | T1 小节自证：## T1 沙盒验证 — 2026-10-31（✅ 通过 · 5 | 验证脚本 `verify_registration.py`（自写）**30/30 通过，exit 0**。 |
| `methodology/t1-iterative-verification-methodology` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-01 | | 结论 | ✅ 通过 | |
| `experience/2026-09-10-k2-horizon-7b-consumer-gpu-deploy` | task | **measured** | 验证小节自证：## 质量实测（5 题） | Simon Willison 鹈鹕骑车基础/加强版（加强版 26 根辐条+喉囊+羽毛全中）、水杯倒水（30 个 SMIL |
| `experience/2026-09-11-patch-input-truncation-silent-corruption` | task | **measured** | 验证小节自证：## 一句话结论 | （如 `$("#kpis")` 变成 `$("kpis")`）。**静态检查（ruff / 行数）全过，只有真跑才炸。* |
| `experience/2026-09-15-cad-label-assoc-lateral-gate` | task | **measured** | 验证小节自证：## 验证 | - 本项目：text2 实测坐标 → 期望 500/几何，旧逻辑 450，修复后 82/82 单测通过。 |
| `experience/activedirs-five-type-discipline` | task | **measured** | 验证小节自证：## 教训（2026-09-02 实测） | - 后果：真实中枢回归（`vector_bench --real`）融合命中率从 **100% 跌至 67%**（4/6 |
| `experience/autocad-cad-plugin-testing-skill-decoupled-architecture` | task | **measured** | 验证小节自证：## 验证数据 | | 成功率 | 100% (3/3) | 不稳定 | - | |
| `experience/autocad-nested-block-layer-inheritance-reverse-containers` | task | **measured** | 验证小节自证：## 验证 | text2.dwg depth=2 梁图层 0LYJY-02-主梁虚线（4650 实体）：修复前 depth=1，修复后 |
| `experience/autocad-pick-auto-click-getbestpickpoint-preposition` | task | **measured** | 验证小节自证：## 验证 | v51 无头 SJ3TESTPICK + 实机 SJ3SET：梁图层 0LYJY-02-主梁虚线命中 3/3 PASS。 |
| `experience/card-move-requires-rebuild-vectors` | pitfall | **measured** | 验证小节自证：## 现象（2026-11-02 实测，rules/ 瘦身 A2 | **没有任何报错**：巡检 exit 0、lint 0、INDEX 一致 —— 只有 `recall_regressio |
| `experience/cross-project-drift-is-semantic-coverage-not-thresholds` | task | **measured** | 验证小节自证：## 场景（2026-11-02 实测，4 个**不同项目**的 | 「谁是主梁」靠启发式（编号 → 收口 → 贯通）。跨项目实测发现主/次比例漂移极大（134/143、292/42、85/ |
| `experience/deepseek-peak-offpeak-scheduler` | task | **measured** | 验证小节自证：## 验证结果（已跑通） | - 幂等：当前空闲态跑脚本 → 静默 exit 0、config 不动 |
| `experience/det-overhit-shortcircuit-fallback` | task | **measured** | 验证小节自证：## 问题现象（真实验证） | 融合命中率从之前的 83% **跌破至 67%（4/6）**，门禁失败（退出码 3）。 |
| `experience/display-topology-switch-looks-like-scaling-change` | task | **measured** | 验证小节自证：## 取证结论：**缩放没被改**，但**显示拓扑**被切了 | | 注册表 `PerMonitorSettings\*\DpiValue` | 两屏 = **0** | 档位索引 ** |
| `experience/dual-engine-single-vector-db-meta-contract` | task | **t1** | T1 小节自证：## T1 验证 — 2026-10-14（⚠️ 部分 5/8  | | T1-1 现状 `would_rebuild=False` | ✅ active=`http:text-embedd |
| `experience/embedding-model-chinese-retrieval-bench-bge-m3-vs-nomic` | task | **measured** | 验证小节自证：## 结论 | | `text-embedding-nomic-embed-text-v1.5` | 768 | **1/10 = 10 |
| `experience/fanhub-10-round-code-review-journey` | task | **measured** | 验证小节自证：## 关键教训（适用所有 T1+ 任务） | 1. **每轮扩大审查面**：第 1 轮只看 db/frontend（漏 2/3 文件），第 3 轮扩到全栈（发现 8  |
| `experience/fanhub-bilibili-real-subtitle-api-without-yt-dlp` | task | **measured** | 验证小节自证：## 结论先行 | | **测试** | 15 个 pytest（13 函数 + 2 集成），全 PASSED | |
| `experience/fanhub-pipeline-batch-parallelization-partial-roi` | task | **measured** | 验证小节自证：## 结论先行 | | **测试** | 12/12 PASSED，含 4 边界 parametrize | |
| `experience/fanhub-pytest-suite-oneshot-scripts-migration` | task | **measured** | 验证小节自证：## 结论先行 | **结果**：38/38 PASSED ✅ |
| `experience/fanhub-sources-max-items-persistence` | task | **measured** | 验证小节自证：## 结论先行 | | **测试套件** | 50 → **55/55 PASSED** in 7.56s | |
| `experience/fanhub-youtube-backfill-single-video-path-success` | task | **measured** | 验证小节自证：## 结论先行 | | MKBHD | 3 | **3** | 0 | 249/342/349 | |
| `experience/gate-environmental-false-reds-guard-refusal-and-scope-delta` | task | **measured** | 验证小节自证：## 坑 1：环境前提变了、断言没跟上（实测两条红） | - 断言前**先探那个前提**（只读，不注入）⇒ 放行走原路径；拒绝则断言「**守卫说清了原因**」= **PASS** |
| `experience/gate-orchestrator-false-green-path-and-emptyrun` | pitfall | **measured** | 验证小节自证：## 二、三类根因（每类都可独立复现） | ⇒ 打印 `0%` 但 **exit 0**。**"零命中"必须是错误，不能是结论**。 |
| `experience/hermes-env-only-proxy-vs-clash-fakeip` | task | **measured** | 验证小节自证：## 判据链（本机实测，2026-09-17） | | httpx `trust_env=True` | HTTP 401 / 0.13s | 只差 key → **连接本 |
| `experience/inconclusive-must-flow-through-orchestration-layers` | task | **measured** | 验证小节自证：## 结论（可复用） | - 批次层：**单列** `inconclusive[]` + `counts{inconclusive}`，且 **a |
| `experience/ingest-l1-lint-gate` | task | **measured** | 验证小节自证：## 关键踩坑（实测） | 3. **lint 跨多文件要严格测**：本地 lint 输出 "X 不合规" ≠ pytest 测不出回归——pyte |
| `experience/l2-audit-regex-ruff-debug` | task | **measured** | 验证小节自证：## 关键问题（实测） | | 不识别嵌套 `|- ` 列表项 | INDEX 行 215/164/170 等嵌套行被忽略 | 加 NESTED_E |
| `experience/mavis-5th-platform-onboarding-pitfalls` | task | **measured** | 验证小节自证：## 验证证据 | [PASS] 平台元数据: platforms.yaml 已注册 |
| `experience/omniroute-auto-combo-offline-compression` | task | **measured** | 验证小节自证：## Auto-Combo 池调整实测（blockedProvi | - 副作用：池缩到只剩 felo 后，紧接 429/400/上下文 limit 报错，可用性反而更差。 |
| `experience/patrol-6day-red-three-defects-and-false-green-score` | pitfall | **measured** | 验证小节自证：### 缺陷 2｜时敏测试（time-bomb test） | 模拟 0/30/180/365/800 天后重跑，确认不再失效。 |
| `experience/pi-cli-injection-gbk-mojibake-utf8-contract` | task | **measured** | 验证小节自证：## 验证口径（复刻 pi 的 spawn 环境：显式清掉 `P | | `engine.py tier-bootstrap --json` | FFFD=27/70 字符，含 U+0636 |
| `experience/pluginhub-date-range-picker-v1.2` | task | **measured** | 验证小节自证：### 验证 | 2. **完整测试套件**:`pytest -q` → 295/295 pass |
| `experience/pluginhub-exhaustive-code-review-v15-findings` | pitfall | **measured** | 验证小节自证：## 测试 | - `pytest tests/test_ask_llm.py` — 26/26 通过 ✅ |
| `experience/pnpm-blocked-build-script-bypass` | task | **measured** | 验证小节自证：## 实测（2026-09-07） | 4. ✅ `pnpm run test:unit` → vitest 全绿（45/45） |
| `experience/ps51-python-stdout-codepage-contract` | task | **measured** | 验证小节自证：## 真根因（字节级证据） | - ⇒ **两边代码页不一致** ⇒ 「默认」两个字被按 GBK 解成 **3 个乱码字符**（实测码位 27035/2 |
| `experience/pyside6-qapplication-wrong-module-dead-import` | task | **measured** | 验证小节自证：## 验证 | - pytest 全套 295/295 pass（修复前 8 failed / 287 passed）。 |
| `experience/pytest-qt-offscreen-no-real-windows` | task | **measured** | 验证小节自证：## 验证 | PluginHub：offscreen 下 298/298 pass + ruff 全绿 + pre-commit 门禁 |
| `experience/python-default-arg-eval-pitfall-and-conftest-isolation` | task | **measured** | 验证小节自证：## 结论先行 | **测试**：64/64 PASSED in 7.60s（之前 1 failed → 0 failed）。 |
| `experience/repo-health-check-doc-layer-is-the-most-stale-layer` | task | **measured** | 验证小节自证：## 触发场景（2026-10-28 实测，CAD 插件 cad | | 门禁 | L0/L1/L2 全绿（编译 0 错误、单测 187/187、无头 33 断言、真实 CAD 3 图） | |
| `experience/ruff-rule-set-drift-lock-select-precommit-gate` | task | **measured** | 验证小节自证：## 验证 | PluginHub：138 errors（锁定规则集后）→ 0 errors + 298/298 tests pass  |
| `experience/scheduler-invoked-script-two-false-greens` | pitfall | **measured** | 验证小节自证：## 结论先行 | **「单测全绿 ≠ 调度器能跑」**：单测里脚本是 **`import scripts.x` 的模块**（`sys.pa |
| `experience/speech-input-r7-pyinstaller-exe-package` | task | **measured** | 验证小节自证：## 顺手验证结论 | - **EXE 跑通完整链路**：锁焦点 → 录音 → 真 ASR → 写剪贴板 → exit 0 |
| `experience/sqlite-insert-or-ignore-requires-unique-constraint` | task | **t1** | T1 小节自证：## T1 迭代验证 — 2026-11-03（cron 无人值 | | 1 | 表上**无 UNIQUE** 时 `INSERT OR IGNORE` 写 3 条 → 行数仍为 3（完全无 |
| `experience/subprocess-stdout-encoding-ambient-env-leak` | task | **t1** | T1 小节自证：## T1 验证（2026-10-30 · 沙盒 F:\Agen | | 干净（unset PYTHONUTF8/PYTHONIOENCODING） | **gbk** | 正常中文 | ✅ |
| `experience/wait-timeout-control-rerun-before-tuning-and-busy-vs-hung` | task | **measured** | 验证小节自证：## 但对照复现直接推翻了它 | 同一台机、**干净 CAD** 上重跑同一条用例：**24/24 断言通过、用时 55 s** ⇒ ⇒ **180 s  |
| `experience/windows-empty-dacl-eperm-vs-file-lock` | task | **measured** | 验证小节自证：# 业务面验证（本例）： | & "<pi安装根>\pi.cmd" auth print-api-key --provider deepseek    |
| `experience/workbuddy-custom-model-fakeip-direct-timeout` | task | **measured** | 验证小节自证：## 证据链（2026-09-17 实测） | | DNS / 裸连 | `api.deepseek.com → 198.18.0.24`（fake-ip）；裸 TCP |
| `experience/workbuddy-model-list-static-deepseek-alias` | task | **measured** | 验证小节自证：## DeepSeek 侧实测（2026-09-16，官方 ap | | `deepseek-v4-pro` | 200 | `deepseek-v4-pro` | 仍回显 pro（官方公告 |
| `experience/write-lock-zombie-detection` | task | **measured** | 验证小节自证：## Phase 1 验证 | - pytest 296/297 pass（无新增回归） |
| `blueprints/agent-skills-spec-skill-creator-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-09-20（SKILL.md | | 结论 | ✅ **PASS**（reference → active）| |
| `blueprints/agentscope-multi-agent-framework-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-06 | | 结论 | ✅ 通过（静态验证） | |
| `blueprints/aider-repo-map-diff-coder-strategy-blueprint` | domain | **t1** | T1 小节自证：## T1 计划（待人工批准） | 沙盒内 `pip install aider-chat`，把模型指向本机 LM Studio（OpenAI 兼容端点）， |
| `blueprints/aps-automation-bundle-blueprint` | proven | **measured** | 验证小节自证：## T1 落地记录（2026-08-21，XrefTraver | **场景**：验证 XrefTraverser（.NET AutoCAD bundle）能否脱离 APS 云端、作为本地 |
| `blueprints/arduino-cli-dual-interface-contract-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证（2026-10-19，沙盒 arduino | - 结果：**⚠️ 部分通过**（CLI 侧通过，gRPC daemon 侧受阻）——保持 reference。 |
| `blueprints/bevy-ecs-data-driven-architecture-blueprint` | domain | **t1** | T1 小节自证：## T1 验证条目（2026-09-11） | | 结论 | ✅ 通过（编译+运行） | |
| `blueprints/biopython-computational-biology-toolkit-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-17（ | **通过：12 / 12** |
| `blueprints/chili3d-browser-cad-wasm-architecture-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-10，F:\AgentMemo | **结果：✅ 通过（核心断言证实，附 1 项新边界）** → `status: reference → active`， |
| `blueprints/closedxml-ooxml-codegen-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-09-20（写 xlsx → | | 结论 | ✅ **PASS**（reference → active）| |
| `blueprints/columnar-dataframe-engine-blueprint` | proven | **t1** | T1 小节自证：## T1 验证条目（2026-09-11） | - **结果**：✅ 通过 |
| `blueprints/continual-harness-refine-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-14，evidence-dri | - step_diagnose: 通过（query.log 存在且有查询记录） |
| `blueprints/craftinginterpreters-language-implementation-blueprint` | proven | **t1** | T1 小节自证：## T1 验证条目（2026-09-07） | **结果**：✅ 通过 |
| `blueprints/dagger-programmable-cicd-engine-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 第 2 次 — 2026-09-06 | | 结论 | ✅ 通过（静态验证） | |
| `blueprints/datafusion-layered-query-engine-blueprint` | proven | **t1** | T1 小节自证：## T1 验证 — 2026-09-30（cron 无人值守  | | SessionContext 编排 + CSV 数据源插件（`register_csv`） | ✅ | |
| `blueprints/duckdb-analytical-db-architecture-blueprint` | proven | **t1** | T1 小节自证：### T1 第 1 次（2026-09-02） | - 结论：✅ 通过 · 隔离 venv + `pip install duckdb`(1.5.5) |
| `blueprints/esphome-yaml-iot-firmware-blueprint` | proven | **t1** | T1 小节自证：## T1 真机验证（2026-09-18，沙盒 F:\Agen | - ✅ 平台 key：显式声明 `esp32: board=esp32dev` 后通过（印证历史踩坑「Platform  |
| `blueprints/ezdxf-local-dxf-batch-processing-blueprint` | proven | **t1** | T1 小节自证：## T1 复用记录 3（最小 demo 验证，2026-09- | - `ezdxf 1.4.4` ✅，`doc = ezdxf.new('R2010')`，`msp.add_circle |
| `blueprints/fastapi-type-driven-api-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-02（ | | 结论 | ✅ 通过 | |
| `blueprints/fastmcp-modular-mcp-server-framework-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-15 | | 装饰器注册工具 | ✅ | `@mcp.tool` 两个函数 → `client.list_tools()` = ` |
| `blueprints/gh-affaan-m-ecc-harness-install-matrix-and-prompt-defense-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-10-31（ | | 基线证据 | `python check_matrix.py` → `模块 4 / 组件 3 / 档位 2`、`PA |
| `blueprints/gh-agricidaniel-claude-seo-domain-skill-pack-decomposition-blueprint` | domain | **measured** | 验证小节自证：### 四、工程规范（顺带证据） | - 26/26 `SKILL.md` frontmatter 含 `name` + `description`（静态 T |
| `blueprints/gh-akkadotnet-akka-net-actor-architecture` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-23 · 沙盒真跑通过） | - **结果**：绿 6 / 红 0 → `T1-PASS` |
| `blueprints/gh-bherbruck-solidcraft-never-crash-layering-enforcer-blueprint` | domain | **measured** | 验证小节自证：## T0 静态验证（2026-10-16，只读） | - Cargo.toml 良构：21/21（root + 11 crates + 3 apps + xtask/vend |
| `blueprints/gh-cloudflare-security-audit-skill-coverage-ledger-audit-blueprint` | domain | **measured** | 验证小节自证：## 一、静态 T0 证据集 | | 三态判决齐备 | 读 schema | ✅ `confirmed` / `needs_validation` / ` |
| `blueprints/gh-cursor-plugins-spec-governance-and-reality-audit-blueprint` | domain | **t1** | T1 小节自证：## T1 验证 — 2026-10-14（✅ 通过 · 规范位 | | T1-1 `required == ['name']` | ✅ | |
| `blueprints/gh-danyuchn-asd-ste100-skill-verifiability-split-linter-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-19，沙盒 asd-ste10 | - 结果：**✅ 通过（6/6 断言）**，`ste-lint.py --selftest` 返 `selftest O |
| `blueprints/gh-dapperlib-dapper-micro-orm-explicit-sql-blueprint` | domain | **t1** | T1 小节自证：## T1 计划（待人工批准） | 沙盒 `F:\AgentMemoryT1\dapper-t1-2026-10-04\` 内 `dotnet new co |
| `blueprints/gh-dotnet-roslyn-compiler-platform-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 2026-10-18（.slnf 构建 | - 环境注记：NuGet restore 直连成功；demo 全程 <30s。结论：**✅ 通过**，status re |
| `blueprints/gh-e2niee-pandapower-network-to-matrix-pipeline-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-10-02 · ✅ 通过 7/7） | | T1-1 `runpp(algorithm='nr')` 收敛 | ✅ | |
| `blueprints/gh-earthtojake-text-to-cad-agent-skill-library-governance-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-05，F:\AgentMemo | 隔离沙盒 · venv（Py3.12）· `pip install -r skill/requirements.txt` |
| `blueprints/gh-grafana-k6-loadtest-as-code-threshold-pipeline-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-10，F:\AgentMemo | **结果：✅ 通过（正/负样本双向验证）** → `status: reference → active`，`reuse |
| `blueprints/gh-hugohe3-ppt-master-routed-native-pptx-skill-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-30 · 沙盒 F:\Agen | | 基线 | 原始包 | **exit 0**，无输出（静默通过） | |
| `blueprints/gh-kedro-org-kedro-data-pipeline-engineering-blueprint` | domain | **t1** | T1 小节自证：## T1 验证 — 2026-10-14（✅ 通过 8/8） | | T1-1 DAG 2 节点 + 拓扑序 | ✅ `['normalize','summarize']` | |
| `blueprints/gh-klayout-klayout-script-rule-dsl-layering-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-10-02 · ✅ 通过 5/5） | | T1-1 `klayout.db` 无 GUI 可用 | ✅ 0.30.12 | |
| `blueprints/gh-leonxlnx-taste-skill-design-taste-library-and-two-tier-detector-blueprint` | domain | **measured** | 验证小节自证：## 一、静态 T0 证据集 | | JSON 全量良构 | 递归 `json.load` 仓内全部 `*.json` | ✅ **13/13 解析通过， |
| `blueprints/gh-mhtsec-artex-human-in-loop-tool-gate-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-10-15（ | | 结论 | ✅ 通过（要点 1/3/4 全部证实，另有增强证据） | |
| `blueprints/gh-microsoft-markitdown-universal-converter-plugin-monorepo-blueprint` | domain | **measured** | 验证小节自证：## 判级结论 | **B+** —— 方法价值高（统一转换面 + 策略族 + 插件分包，与中枢 ocrmypdf/pandoc 类卡同构互 |
| `blueprints/gh-pbakaus-impeccable-design-vocabulary-platform-mirror-blueprint` | domain | **measured** | 验证小节自证：## 一、静态 T0 证据集 | | 命令 ↔ playbook 一致 | 逐键核 `reference/<key>.md` 存在性 | ✅ 24/24  |
| `blueprints/gh-pingdotgg-t3code-provider-capability-negotiation-blueprint` | domain | **t1** | T1 小节自证：## 六、T1 迭代验证（2026-10-31，沙盒 F:\Ag | 对能力契约 / 三层分包 / 注册表顺序语义逐条断言。**断言 36/36 全过**（`verify_contract. |
| `blueprints/gh-prefecthq-prefect-workflow-orchestration` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-23 · 沙盒真跑通过） | - **结果**：绿 12 / 红 0 → `T1-PASS` |
| `blueprints/gh-quantconnect-lean-pluggable-trading-engine-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 2026-10-11（cron · ✅ | | SLN **23 个 Project 条目** | `Project("{` 行 **23** · `.csproj |
| `blueprints/gh-sqlalchemy-core-orm-dual-layer-blueprint` | proven | **t1** | T1 小节自证：## T1 验证 — 2026-09-30（cron 无人值守  | | Core 层 表达式查询（Table + select + where） | ✅ `[('Fan', 34)]` | |
| `blueprints/gh-storytold-cadcraft-clean-room-autocad-mcp-kernel-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-13，cron star-di | **结果：⚠️ 部分通过** —— 卡的核心断言「分层是**可执行门禁**」成立，但「L5 以下禁依赖 egui/wgp |
| `blueprints/gh-sympy-sympy-symbolic-assumptions-printer-blueprint` | domain | **t1** | T1 小节自证：## 静态 T0 证据（2026-10-03） | - `pyproject.toml` TOML 良构（tomllib 解析通过）。 |
| `blueprints/gh-t-auto-dsh-ops-progressive-disclosure-bounded-ops-blueprint` | domain | **measured** | 验证小节自证：## T0 静态验证（2026-10-16，只读） | - JSON 良构：143/143 文件解析 0 失败。 |
| `blueprints/gh-thedotmack-claude-mem-multi-platform-session-memory-loop-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 2026-10-11（cron · ✅ | | `claude-mem` **v13.35.0**（根 deps=2） | **npm 注册表 `13.35.0`* |
| `blueprints/gh-yjs-yjs-shared-type-crdt-blueprint` | domain | **t1** | T1 小节自证：## T1 沙盒验证 — 2026-10-31（✅ 通过 · 核 | 验证脚本 `verify_crdt.mjs`（自写，零外部断言库），**12/12 通过，exit 0**。 |
| `blueprints/gitleaks-generated-config-secret-scan-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-05，F:\AgentMemo | gitleaks **8.30.1** 单二进制（release asset `gitleaks_8.30.1_wind |
| `blueprints/graphite-node-graph-three-tier-executor-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 2026-11-03（cron 无人值 | | 2 | 路径 B：三段执行器 crate | `node-graph/preprocessor`、`node-gra |
| `blueprints/grpc-dotnet-protobuf-rpc-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-01 | | 结论 | ✅ 通过 | |
| `blueprints/hyperformula-spreadsheet-engine-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-06，沙盒 `F:\Agent | - 结果：**✅ 7/7 PASS**（`npm i hyperformula` 4 包/10s → `node dem |
| `blueprints/hypothesis-property-based-testing-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-19 | | P1 完备性 | 选出配筋面积 ≥ 需求（**不得少配**）| ✅ PASS | |
| `blueprints/ifcopenshell-bim-ecosystem-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-17（ | **通过：13 / 13** |
| `blueprints/ilspy-dotnet-decompiler-pipeline-blueprint` | domain | **t1** | T1 小节自证：## T1 计划（待人工批准后执行） | 沙盒 `F:\AgentMemoryT1\ilspy-dotnet-decompiler-pipeline-2026-0 |
| `blueprints/jupyterlab-extension-monorepo-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证（2026-09-27）✅ | - 结论：**通过** → status reference→active，reuse_count 0→1。 |
| `blueprints/langgraph-checkpoint-durable-agent-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-26 · ✅ 通过 9/9） | - 写侧 6/6：首次 invoke → `CheckpointTuple` 落盘 → `channel_values` |
| `blueprints/litestar-asgi-api-framework-blueprint` | proven | **t1** | T1 小节自证：## T1 真机验证（2026-09-18，沙盒 F:\Agen | - ✅ Controller 路由：`GET /items/` → 200，返回 `[{'name': '锚栓', 'q |
| `blueprints/litestar-python-asgi-plugin-architecture-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-10-08（ | | 结论 | ✅ 通过（4/4 断言全过，ALL PASS） | |
| `blueprints/mcp-servers-reference-implementation-capability-slicing-blueprint` | domain | **measured** | 验证小节自证：### 路径 D：TS/Python 双栈并存，测试与容器样例自 | `__tests__/`）、Python 系（`fetch/git/time`：pyproject.toml）；**7/ |
| `blueprints/meilisearch-index-scheduler-search-engine-blueprint` | domain | **t1** | T1 小节自证：## T1 计划（待沙盒执行） | `F:\AgentMemoryT1\meilisearch-index-scheduler-search-engine- |
| `blueprints/netdxf-csharp-dxf-object-model-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-09-16（C# 读写往返  | | 结论 | ✅ 通过（reference → active） | |
| `blueprints/nuclei-yaml-security-scanner-blueprint` | proven | **t1** | T1 小节自证：## T1 验证记录（2026-09-05） | **结果**：✅ 通过，输出 `[test-http-get] [http] [info]` |
| `blueprints/onnxruntime-multi-backend-ml-inference-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-01） | **结论**: ✅ 通过（reference → active, reuse_count: 0 → 1） |
| `blueprints/or-tools-model-solver-backend-separation-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-10-15（ | | 结论 | ✅ 通过 | |
| `blueprints/polly-resilience-pipeline-blueprint` | domain | **t1** | T1 小节自证：## T1 验证（2026-10-30 · 沙盒 F:\Agen | **通过的两件事（一手实测）**： |
| `blueprints/pydantic-type-driven-validation-core-split-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 2026-10-18（六断言全过） | - ①Rust 内核实测：`pydantic_core._pydantic_core.__file__` = `_pyd |
| `blueprints/pynite-python-structural-fea-architecture-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-15 | | 简支梁均布荷载（一阶） | ✅ | 跨中挠度 FE 8.0357e-3 m = 5wL⁴/384EI 同值（误差 0 |
| `blueprints/ruff-five-stage-workspace-rule-family-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-10-08（ | | 结论 | ✅ 通过 | |
| `blueprints/scrapy-three-tier-middleware-settings-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-10-07，沙盒 scrapy-th | **Demo**：`demo_middleware.py`，**10/10 通过**。 |
| `blueprints/semgrep-rules-engine-blueprint` | domain | **t1** | T1 小节自证：## T1 验证条目（2026-09-07） | **结果**：✅ 通过 |
| `blueprints/skillopt-blueprint` | proven | **t1** | T1 小节自证：## T1 验证条目（2026-09-07） | **结果**：⚠️ 部分通过（包已安装，无 CLI 入口） |
| `blueprints/sqlglot-zero-dependency-sql-parser-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-26 · ✅ 通过 10/10 | | 中文列名/表名解析（hive 方言） | ✅ `结构编号 / 位移_mm / 楼层` 全部保留 | |
| `blueprints/textual-cross-runtime-tui-pilot-blueprint` | proven | **t1** | T1 小节自证：## 本卡状态与后续 | - 判级 **B+**（方法价值高且与中枢同构：无头测试与驱动抽象同构于本仓既有测试/驱动方法论；静态 T0 通过）→  |
| `blueprints/tile38-command-codegen-spatial-store-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-28 | **判定**：✅ 通过 → `status: reference → active`，`reuse_count: 0 → |
| `blueprints/tree-sitter-incremental-reparse-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-10-07，沙盒 tree-sitt | **Demo**：`demo_incremental.py`，**9/9 通过**，三主张全部坐实。 |
| `blueprints/trimesh-python-mesh-processing-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 2026-09-16（几何量 vs 闭 | | 结论 | ✅ 通过（reference → active） | |
| `blueprints/trufflehog-detector-plugin-registry-secret-scan-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-29，沙盒 truffleho | - 结果：**✅ 通过（检出 2 类真实样本）**，`trufflehog 3.97.9`（release `truff |
| `blueprints/turso-libsql-database-engine-blueprint` | proven | **t1** | T1 小节自证：## T1 验证记录（2026-09-05） | **结果**：✅ 通过，输出 `┌──────┬──────────────────┐ │ 1 │ 3.50.4 │` |
| `blueprints/typst-markup-typesetting-engine-blueprint` | proven | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-09-28 | | demo 覆盖 | `#set page/#set text` 中英混排（New Computer Modern + |
| `blueprints/uv-unified-python-toolchain-rust-workspace-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-29，沙盒 uv-unifie | - 结果：**✅ 通过（3/3 主张）**，`uv 0.12.20 (2274b80d6 2026-09-28 x86_ |
| `blueprints/vector-db-hnsw-indexing-blueprint` | domain | **t1** | T1 小节自证：## T1 迭代验证 — 第 1 次 — 2026-10-29（ | | 结论 | ✅ 通过（方法学层面）。召回/延迟权衡、单调性、持久化、加速比四项全过 | |
| `blueprints/wasmtime-wasm-runtime-multi-backend-blueprint` | proven | **t1** | T1 小节自证：## T1 验证（2026-09-01） | **结论**: ✅ 通过（reference → active, reuse_count: 0 → 1） |
| `projects/hermes-cron-jobs` | domain | **measured** | 验证小节自证：## T1/状态回写口径（2026-10-01 起：**改卡，不 | python -m scripts.set_index_meta --slug <slug> --note '｜stat |
| `projects/project-threeRowRein-baseline-v51-snapshot` | domain | **t1** | T1 小节自证：## T1 验证 — 2026-10-17（基线完整性审计 ·  | | T1-1 关键文件 4/4 | ✅ docs/USER_GUIDE.md · tools/regression_ch |

## 已知边界（诚实记录）

1. **不是逐张人工读过**：本轮用 v5 判据**批量裁定** + **18 张抽样人工核验（18/18 成立）**；
   v5 仍有理论上的假阳性（如「结论先行」节里引用他人结论），故判据要求**量化结果**（n/N、exit 0、全过…）。
2. **t1 与 measured 的边界**：`t1` = 有 T1 亲跑小节；`measured` = 有验证/实测小节 + 量化结果。
   同一张卡若两者都有，取 `t1`（证据更强）。
3. **不改 grade**：本回填只加 `evidence`（正交轴），`grade` 全部保持人工标注。
4. **正文零 diff**：只写 frontmatter 两个字段（`evidence` / `updated`）。
