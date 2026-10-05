# SkillHub 登记 · 批次 1 分类清单（2026-10-05）

> 数据源：`capability_reconcile.reconcile()` 的 `unregistered_installed` + 各平台 `skills_dir` 实测扫描。
> 规则（用户 2026-10-05 裁定）：**默认登记**；排除 `HERMES_*`（Hermes 自有不共享）与 skill 内**明示独享**者。
> 契约提醒：登记记录须**逐一对应** `skills/<name>/skill.yaml`（`router/schema.yaml` 顶层）⇒
> 本清单中 `migrate` 组必须**先迁实现**（SKILL.md + skill.yaml + router 三件套），**不得只往 router.yaml 加行**。

## 汇总

- **待迁移并登记**：48
- **排除：HERMES_* 自有**：1
- **排除：自称独享**：1
- **待定位实现**：12

## A. 待迁移并登记（48）

| # | 技能 | 线索 |
|---|---|---|
| 1 | Fan-Control-PC | workbuddy · 经由 computer-use-anywhere MCP server（cua-mcp）控制 Fan 的 Windows 桌面——截图、键鼠、激活窗口、浏览器 DOM 操作。这是经 |
| 2 | Fan-inspiration | workbuddy · 把 iPhone 语音转文字产生的灵感碎片（带错别字、重复多份），流水线式整理成可生长的 Obsidian 知识库（Zettelkasten 卡片盒）。触发：用户要把语音/速记灵感 |
| 3 | agent-platform-onboarding | hermes · Use to add a new Agent platform to AgentMemoryHub. |
| 4 | autocad-com-automation-test | workbuddy · 开发 AutoCAD .NET 插件（acmgd.dll / accoremgd.dll / acdbmgd.dll）时用 COM 自动化测试整套流程——含防卡死纪律、测试副本隔离 |
| 5 | baidu-drive | workbuddy · 百度网盘(Baidu Drive)文件管理 — 上传、下载、转存、分享、搜索、移动、复制、重命名、创建文件夹。TRIGGER: |
| 6 | bailian-cli | hermes · >- |
| 7 | bailian-docs-llm-wiki | hermes · >- |
| 8 | bailian-finetune | hermes · >- |
| 9 | bailian-gen | hermes · >- |
| 10 | bailian-managed-agent | hermes · >- |
| 11 | bailian-model-recommend | hermes · >- |
| 12 | bailian-protocol | hermes · >- |
| 13 | bailian-train-deploy | hermes · 用百炼 CLI (`bl`) 走完"数据→微调训练→导出→部署→调用"的完整闭环，或跳过训练直接部署基座模型。支持文本模型（SFT/DPO/CPT）、音频 TTS 模型（CosyV |
| 14 | bailian-web-search | hermes · >- |
| 15 | browser-automation-toolbox | workbuddy · 浏览器自动化兜底工具箱，专治难抓的网站。4 套爬虫方案自动降级（CloakBrowser / browser-act / Kimi WebBridge / Playwright）+ |
| 16 | build-new-task | hermes · Use this skill to open a brand-new task window and hand off the current (or a previous) ta |
| 17 | cad-screenshot-pixel-forensics | workbuddy · 无视觉模型或需要"可复现的数值证据"时，用纯像素分析从 CAD/工程截图里量出图元位置、间距、道数、长度、颜色（反推 AutoCAD ACI），用于取证、回归断言与"图↔代码"对照 |
| 18 | computer-interface-controller | mavis · 电脑界面自主操控技能。当用户要求操控电脑界面、自动化桌面操作、进行GUI自动化、点击按钮、输入文字、分析屏幕、填写表单、管理文件、控制浏览器时使用。支持本地和远程环境。 |
| 19 | context-driven-development | workbuddy · Use this skill when working with Conductor's context-driven |
| 20 | darwin-skill | workbuddy · Darwin Skill (达尔文.skill): autonomous skill optimizer inspired by Karpathy's autoresearch.  |
| 21 | desktop-preview-reveal | hermes · Open file:// URL in Hermes desktop preview pane. |
| 22 | doc-text-extract | workbuddy · 当 WorkBuddy 的 editor_sdk（tencent-local-office-edit）无法读取 .doc（Word 97-2003 二进制 OLE2）正文时，用 o |
| 23 | github-trending-cn | workbuddy · GitHub Trending Monitor. Fetch GitHub trending repos by |
| 24 | hatch-pet | code · Create, repair, validate, visually QA, and package Codex-compatible v2 animated pets from  |
| 25 | ima-skills | workbuddy ·  |
| 26 | impeccable | workbuddy · | |
| 27 | janee | code · > |
| 28 | kdocs | workbuddy · 操作金山文档（WPS 云文档 / Kdocs / 365.kdocs.cn / www.kdocs.cn）云文档的官方 Skill。核心能力覆盖云端新建、读取、编辑、搜索、分享、整 |
| 29 | local-proxy-timeout-diagnosis | workbuddy · 诊断「本机装了代理（Clash/Verge 等）导致某个应用调云端 API 超时，但浏览器/curl 却正常」这类问题——用连接阶段 vs 应用阶段、fake-ip 判定、注册表  |
| 30 | markitdown-skill | workbuddy · Convert documents to Markdown using Microsoft's MarkItDown CLI (`markitdown`). Supports PD |
| 31 | mcp-server-setup | hermes · Install or troubleshoot MCP servers in Hermes Agent. |
| 32 | minimax-xlsx | workbuddy · Open, create, read, analyze, edit, or validate Excel/spreadsheet files (.xlsx, .xlsm, .csv |
| 33 | neodata-financial-search | workbuddy · NeoData Financial Search — 自然语言通用金融数据搜索服务。用自然语言查询股票、基金、指数、板块、 |
| 34 | notebooklm-studio | workbuddy · Import sources (URLs, YouTube, files, text) into Google NotebookLM and generate artifacts: |
| 35 | npm-cli-relocate-custom-prefix | workbuddy · 把某个 npm 全局安装的 CLI/Agent（pi、codex、dsh 之类）从共享全局 prefix 迁到它自己的独立目录，并顺带钉住它的启动工作目录与配置/数据目录。含三个非 |
| 36 | oracle | workbuddy · Use the @steipete/oracle CLI to bundle a prompt plus the right files and get a second-mode |
| 37 | pdfkit-py | workbuddy · 仅用于对已存在的 .pdf 文件进行处理（读取/提取/编辑/合并/拆分/转换/水印/加密/OCR/表单/签名）。当且仅当用户输入或工作区中存在 .pdf 文件，且操作对象是该 PD |
| 38 | skillhub-integration | hermes · Use for SkillHub routing, mounting into Hermes, dedup calls. |
| 39 | tencentcloud-ocr | workbuddy · 腾讯云通用文字识别（高精度版）(GeneralAccurateOCR) 技能包。当用户发送/粘贴图片、提供图片URL、或要求识别图片中的文字时，应自动调用此技能。支持图像整体文字的 |
| 40 | web-board-browser-regression | workbuddy · 本地 Web 看板/应用的浏览器回归测试方法论（agent-browser 实操 + 三条硬纪律）。适用场景：网页看板回归、本地 Web 应用 UI 验证、自动化点击测试。勿用于： |
| 41 | westockdata | workbuddy · 金融市场结构化数据查询的权威入口。支持股票（A股/港股/美股）、ETF、指数、板块、期货、外汇、可转债的 K 线、技术指标、筹码、财报、研报、公告、风险事件、股东、分红、ETF 持 |
| 42 | windows-file-access-denied-forensics | workbuddy · Windows 上出现 EPERM / Errno 13 / "Access to the path is denied" 读写失败时的取证与修复流程——三步判据区分「句柄锁」「空 |
| 43 | windows-safe-file-cleanup | workbuddy · 在 Windows 上安全清理应用数据目录（如 F:\lmstudio-home、Electron/Ollama/LM Studio 的 home）的遗留安装包、过期运行时与过渡文 |
| 44 | workbuddy-custom-model-tuning | workbuddy · 在 WorkBuddy Desktop 上配置/排障自定义云端模型（~/.workbuddy/models.json）——读 app.asar 确认字段语义与消费路径、官方文档核对 |
| 45 | workbuddy-host-env-shim-isolation | workbuddy · 在 WorkBuddy 会话里构建/更新外部应用（Hermes、Electron 打包、npm/vite/uv 安装等）时，宿主注入的 shim 环境变量会拦截目录清理与文件删除， |
| 46 | wsl2-ops-on-windows | hermes · Use when installing or debugging WSL2 on Windows. |
| 47 | xiaoshi-quant-expert | workbuddy · Use Xiaoshi Big Data API for market and industry briefings, |
| 48 | 腾讯文档 | workbuddy · 腾讯文档（docs.qq.com）-在线云文档平台，是创建、编辑、管理文档的首选 skill。涉及"新建/创建/编辑/读取/查看/搜索文档"、"保存文件"、"云文档"、"腾讯文档" |

## B. 待定位实现（12）

| # | 技能 | 线索 |
|---|---|---|
| 1 | apple | 客户端目录未找到 SKILL.md（需先定位实现） |
| 2 | autonomous-ai-agents | 客户端目录未找到 SKILL.md（需先定位实现） |
| 3 | creative | 客户端目录未找到 SKILL.md（需先定位实现） |
| 4 | email | 客户端目录未找到 SKILL.md（需先定位实现） |
| 5 | media | 客户端目录未找到 SKILL.md（需先定位实现） |
| 6 | mlops | 客户端目录未找到 SKILL.md（需先定位实现） |
| 7 | note-taking | 客户端目录未找到 SKILL.md（需先定位实现） |
| 8 | productivity | 客户端目录未找到 SKILL.md（需先定位实现） |
| 9 | research | 客户端目录未找到 SKILL.md（需先定位实现） |
| 10 | smart-home | 客户端目录未找到 SKILL.md（需先定位实现） |
| 11 | social-media | 客户端目录未找到 SKILL.md（需先定位实现） |
| 12 | web | 客户端目录未找到 SKILL.md（需先定位实现） |

## C. 排除：自称独享（1）

| # | 技能 | 理由 |
|---|---|---|
| 1 | code-rule | SKILL.md 自称独享（workbuddy） |

## D. 排除：Hermes 自有（1）

| # | 技能 | 理由 |
|---|---|---|
| 1 | HERMES_RULES_ROUTING | HERMES_* 前缀：Hermes 自有，不共享（用户裁定） |
