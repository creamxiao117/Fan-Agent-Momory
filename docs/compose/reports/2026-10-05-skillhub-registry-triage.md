# SkillHub 登记缺口 · 待审表（2026-10-05）

> 数据源：`python -m scripts.capability_reconcile --root AgentMemoryHub`（机器可复算）。
> **本表只做分流与排序，不含结论**：每条都要人判「补 / 删 / 保留」，机器按名字编路由会误命中（项目既定结论）。

## 成本上下文（每会话常驻）

- 平台：hermes 1907 | code 1272 | workbuddy 3264 | deepseek 0 | mavis 21 | pi 200；软目标 **1500**，MCP server 上限 **5**（fleet 求和 6664，仅库存参考、不设帽）
- 登记：recorded **75** / implemented **47** / measured_installed **83**
- 缺口：**装了未登记 62** · **登记了查无实现 22**
- ⚠️ 数字较 13:05 那次（81 / 103）下降，是因为 **trae 退役**后其名下技能退出 measured 集合（同一工具同一口径，只是平台范围变了）——**不要当成数据错误**。

## A. 「装了却从未登记」62 个（已知成本降序，未测者置后）

| # | 技能 | 已知常驻成本 | 建议动作（待你判） |
|---|---|---|---|
| 1 | workbuddy-host-env-shim-isolation | 169 token | 优先审（成本已知且高） |
| 2 | minimax-xlsx | 158 token | 优先审（成本已知且高） |
| 3 | build-new-task | 135 token | 优先审（成本已知且高） |
| 4 | bailian-train-deploy | 122 token | 优先审（成本已知且高） |
| 5 | npm-cli-relocate-custom-prefix | 122 token | 优先审（成本已知且高） |
| 6 | darwin-skill | 121 token | 优先审（成本已知且高） |
| 7 | hatch-pet | 111 token | 优先审（成本已知且高） |
| 8 | computer-interface-controller | 21 token | 审 |
| 9 | Fan-Control-PC | 未测 | 先测成本再判 |
| 10 | Fan-inspiration | 未测 | 先测成本再判 |
| 11 | HERMES_RULES_ROUTING | 未测 | 先测成本再判 |
| 12 | agent-platform-onboarding | 未测 | 先测成本再判 |
| 13 | apple | 未测 | 先测成本再判 |
| 14 | autocad-com-automation-test | 未测 | 先测成本再判 |
| 15 | autonomous-ai-agents | 未测 | 先测成本再判 |
| 16 | baidu-drive | 未测 | 先测成本再判 |
| 17 | bailian-cli | 未测 | 先测成本再判 |
| 18 | bailian-docs-llm-wiki | 未测 | 先测成本再判 |
| 19 | bailian-finetune | 未测 | 先测成本再判 |
| 20 | bailian-gen | 未测 | 先测成本再判 |
| 21 | bailian-managed-agent | 未测 | 先测成本再判 |
| 22 | bailian-model-recommend | 未测 | 先测成本再判 |
| 23 | bailian-protocol | 未测 | 先测成本再判 |
| 24 | bailian-web-search | 未测 | 先测成本再判 |
| 25 | browser-automation-toolbox | 未测 | 先测成本再判 |
| 26 | cad-screenshot-pixel-forensics | 未测 | 先测成本再判 |
| 27 | code-rule | 未测 | 先测成本再判 |
| 28 | context-driven-development | 未测 | 先测成本再判 |
| 29 | creative | 未测 | 先测成本再判 |
| 30 | desktop-preview-reveal | 未测 | 先测成本再判 |
| 31 | doc-text-extract | 未测 | 先测成本再判 |
| 32 | email | 未测 | 先测成本再判 |
| 33 | github-trending-cn | 未测 | 先测成本再判 |
| 34 | ima-skills | 未测 | 先测成本再判 |
| 35 | impeccable | 未测 | 先测成本再判 |
| 36 | janee | 未测 | 先测成本再判 |
| 37 | kdocs | 未测 | 先测成本再判 |
| 38 | local-proxy-timeout-diagnosis | 未测 | 先测成本再判 |
| 39 | markitdown-skill | 未测 | 先测成本再判 |
| 40 | mcp-server-setup | 未测 | 先测成本再判 |
| 41 | media | 未测 | 先测成本再判 |
| 42 | mlops | 未测 | 先测成本再判 |
| 43 | neodata-financial-search | 未测 | 先测成本再判 |
| 44 | note-taking | 未测 | 先测成本再判 |
| 45 | notebooklm-studio | 未测 | 先测成本再判 |
| 46 | oracle | 未测 | 先测成本再判 |
| 47 | pdfkit-py | 未测 | 先测成本再判 |
| 48 | productivity | 未测 | 先测成本再判 |
| 49 | research | 未测 | 先测成本再判 |
| 50 | skillhub-integration | 未测 | 先测成本再判 |
| 51 | smart-home | 未测 | 先测成本再判 |
| 52 | social-media | 未测 | 先测成本再判 |
| 53 | tencentcloud-ocr | 未测 | 先测成本再判 |
| 54 | web | 未测 | 先测成本再判 |
| 55 | web-board-browser-regression | 未测 | 先测成本再判 |
| 56 | westockdata | 未测 | 先测成本再判 |
| 57 | windows-file-access-denied-forensics | 未测 | 先测成本再判 |
| 58 | windows-safe-file-cleanup | 未测 | 先测成本再判 |
| 59 | workbuddy-custom-model-tuning | 未测 | 先测成本再判 |
| 60 | wsl2-ops-on-windows | 未测 | 先测成本再判 |
| 61 | xiaoshi-quant-expert | 未测 | 先测成本再判 |
| 62 | 腾讯文档 | 未测 | 先测成本再判 |

## B. 「登记了却查无实现」22 个（二元：补实现 or 删记录）

| # | 记录名 | 建议核查 |
|---|---|---|
| 1 | 1password | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 2 | ascii-art | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 3 | chrome | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 4 | concept-diagrams | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 5 | duckduckgo-search | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 6 | dynamic-ui | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 7 | fastmcp | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 8 | here-now | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 9 | integrated_code_mode | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 10 | integrated_goal | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 11 | jupyter-notebook | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 12 | lark | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 13 | meme-generation | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 14 | obsidian | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 15 | one-three-one-rule | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 16 | pdf-monster | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 17 | pdf-reader | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 18 | qmd | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 19 | scrapling | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 20 | sherlock | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 21 | skill-creator | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |
| 22 | vercel-react-best-practices | ①上游是否改名/下架 ②是否本就该由 MCP 提供（reconcile 已排除 mcp ⇒ 非此因） |

## C. 按性价比的推进次序（建议）

1. **先审超软目标最多的平台**（workbuddy 超 1764、hermes 超 407）——降常驻成本收益最直接；
2. B 表（22 条）**先删明显失效登记**再谈补实现（删记录成本最低、且能让指标回归真实）；
3. A 表（62 条）先补 `trigger`/`forgot` 的**只限成本已知且 ≥100 token 的前 10 条**，其余按需；
4. 全程**不动 `per_session_target` 这个数字**（棘轮语义：超帽要降级能力，不是抬帽）。
