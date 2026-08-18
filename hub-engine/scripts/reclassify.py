"""原子化重构（2026-08-18）：把归档的 26 张旧卡按五类判别树拆成原子卡并重建索引。

五类判别树：
1. 违反有代价 → 规则（rule）
2. 可复用步骤/流程/思考原则 → 方法论（methodology）
3. 绑定具体项目/平台/环境 → 项目记忆（project）
4. 跨项目稳定用户档案 → 长期记忆（longterm）
5. 兜底（踩坑/排障/实测结论） → 经验（exp）

用法：python hub-engine/scripts/reclassify.py
幂等：重复运行会覆盖同名原子卡并重建 INDEX.md。
原 26 卡已拆分为 55 张原子卡，旧卡未保留（原子化重构完成）。
"""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1])
)  # 使 scripts 内可 import common.*

from common.frontmatter import Card, today_iso, write_card

HUB = Path(__file__).resolve().parents[2] / "AgentMemoryHub"
CLS_DIR = {
    "rule": "rules",
    "methodology": "methodology",
    "longterm": "longterm",
    "project": "projects",
    "exp": "experience",
}
TODAY = today_iso()

# (cls, file, tags, source, desc, body) —— source 逗号分隔旧卡名，用于来源对照表
ATOMS = [
    # ============ rules/ 权威规则（命令式/约束式，违反有代价） ============
    (
        "rule",
        "dll-version-lock",
        ["autocad", "dll-lock"],
        "dll-version-lock, query-writeback, user-preferences",
        "DLL 修改后必须递增版本号，避免 AutoCAD 锁文件",
        r"""DLL 版本防锁规则（跨项目适用）：
- 修改 DLL 后必须递增版本号，绝不能原地覆盖同名文件，避免发布后被 AutoCAD 锁文件。
- 预防优于补救：开发期即采用递增版本命名（查询「DLL 被锁」命中规则后的确认结论）。""",
    ),
    (
        "rule",
        "markdown-revision-style",
        ["markdown", "edit", "convention"],
        "markdown-revision-style",
        ".md 修改用修订样式（~~旧~~ / **新**）便于查看改动",
        r"""Markdown 文件修改约定（2026-08-16）：修改 `.md` 文件时使用修订样式（`~~旧内容~~` / `**新内容**`），方便查看改动前后。""",
    ),
    (
        "rule",
        "context-budget-discipline",
        ["context", "budget", "workflow"],
        "context-budget-discipline, fan-节奏：上下文-6",
        "上下文预算纪律：45~65% 节流、>65% 红区暂停扩展读取",
        r"""上下文预算纪律（2026-07-31 用户明确要求，强制遵守）：按当前上下文占用率分档调整行为，适用于所有项目；`WORK.md` 缺失时应在项目根创建。
- **45%~65%**：进入节流模式——减少无关文档阅读、不重复解释已确认的结论、不回贴原始工具输出（只给提炼后的关键行/结论）。
- **>65%**（红区）：暂停一切扩展性读取（不再 grep/read 新文件、不再跑探索性命令）；先把当前状态写入项目的 `WORK.md`（唯一当前态来源），必要时利用一次性调度在平台开启新对话，从 `WORK.md` 获取任务信息，重启上下文后再继续。""",
    ),
    (
        "rule",
        "context-engineering-skeleton",
        ["context-engineering", "skeleton", "workflow"],
        "context-engineering-v1",
        "AI 协作骨架：单入口/单一状态源/单日志/小迭代/分层/轻量闸门/上下文预算",
        r"""context-engineering-v1 核心骨架规则（来源：`c:\Users\Fan-SJSS\.trae-cn\skills\context-engineering-v1\SKILL.md`，跨项目适用）：
1. 单一入口：只保留 `AGENTS.md` 作为必需启动入口。
2. 单一状态源：`WORK.md` 作为项目当前状态的唯一来源。
3. 单一过程日志：`RUNLOG.md` 为只追加的迭代日志，倒序（最新在前），不每轮新建笔记文件。
4. 小迭代：每轮通常只加一个主能力。
5. 方法论分层：跨项目规则与项目专属规则分离（shared vs project-specific）。
6. 轻量闸门：用 4 字段成本-收益闸门，不用重型评分体系。
7. 上下文预算：三档节流（详见 rules/context-budget-discipline.md）。""",
    ),
    (
        "rule",
        "context-engineering-avoid",
        ["context-engineering", "avoid"],
        "context-engineering-v1",
        "骨架避免项：多状态文件/每轮解释文档/重型评分/验证前扩张/中文文件名",
        r"""【避免】多个当前状态文件；每轮新建解释文档；重型评分框架；验证前扩张工作流；核心运行时文件用中文文件名。""",
    ),
    (
        "rule",
        "text-extraction-priority",
        ["text", "ocr", "extract", "download"],
        "text-extraction-priority",
        "文本获取优先级：能复制就复制、能下载就下载、最后才 OCR",
        r"""【文本获取优先级】用户明确指令：找到文本后，能复制文字就复制（DOM/clipboard/aria），能下载就下载（页面下载/导出），最后才采用 OCR。这是处理网页/PDF/截图内容时的标准操作顺序。""",
    ),
    (
        "rule",
        "memory-hub-query-first",
        ["memory-hub", "workflow"],
        "workflows, unified-memory-hub-workflow",
        "执行前先查统一记忆中枢，命中再执行；不确定交回用户",
        r"""【统一记忆中枢工作流规则】执行前先查统一记忆中枢：读取 INDEX.md 与 rules / methodology / longterm / projects / experience，命中再执行；不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。""",
    ),
    (
        "rule",
        "browser-automation-chrome-preference",
        ["browser", "chrome", "cdp", "automation"],
        "browser-automation-chrome",
        "浏览器自动化：默认驱动已登录真实 Chrome，勿开临时 profile 复制 cookie",
        r"""【浏览器自动化偏好】默认驱动用户已登录的真实 Chrome（CDP / --remote-debugging-port=9222），复用其登录态；不要轻易开临时 profile 复制 cookie（Chrome 新版本加密 cookie 不可迁移，得不偿失）。""",
    ),
    (
        "rule",
        "code-platform-conventions",
        ["code", "convention"],
        "开启计划模式；代码要求简",
        "code 平台约定：计划模式/代码简洁/提交前检查/冗余删除/子智能体默认模型",
        r"""code 平台约定（本 AGENTS.md 约束）：
- 开启计划模式；代码要求简洁高效；git commit and push github 时需要逻辑和代码检查。
- md 文档中冗余的中间过渡产物，确认后直接删除；错误的结论使用删除线标注，保留修改时间和理由。
- 子智能体的模型只能使用默认模型（严禁使用 gpt-5.6-sol）。
- 子代理（spawn_agent / 子智能体）必须沿用本 AGENTS.md 的所有约束。""",
    ),
    (
        "rule",
        "lint-runtime-data-exclude",
        ["markdownlint", "check-code", "agentmemoryhub", "config"],
        "lint-runtime-data-exclude",
        "运行态数据目录（AgentMemoryHub）不进 markdownlint 静态检查",
        r"""运行态数据目录（AgentMemoryHub）不进 markdownlint 静态检查——draft/conflicts/retro 日志/experience/rules 卡片均为引擎生成产物（带 frontmatter 无 H1、紧凑日志格式），硬套手写文档规则必然误报（MD041/MD022/MD032/MD034/MD024），其内容质量由引擎 tools/lint.py 负责。
复用约定：后续新增平台记忆沉淀/运行态产物统一放 AgentMemoryHub 并沿用该排除；根目录手写文档（AGENTS.md/docs/设计稿）仍受 markdownlint 严格检查。""",
    ),
    (
        "rule",
        "gateway-no-credential-rule",
        ["gateway", "config"],
        "gateway：weix",
        "缺凭证的平台须先 enabled=false 再启动",
        r"""【网关启动规则】缺凭证的平台须先 enabled=false 再启动。""",
    ),
    # ============ methodology/ 方法论（可复用步骤/流程/思考原则） ============
    (
        "methodology",
        "first-principles",
        ["context-engineering", "thinking"],
        "context-engineering-v1",
        "思考原则：第一性原理（目标/约束/证据/最小验证）",
        r"""【思考原则】第一性原理：先拆到真实目标、硬约束、当前证据、最小可验证下一步；不因惯性继承旧工作流/布局/假设。""",
    ),
    (
        "methodology",
        "occam-razor",
        ["context-engineering", "thinking"],
        "context-engineering-v1",
        "思考原则：奥卡姆剃刀（最少文件/字段/步骤/依赖）",
        r"""【思考原则】奥卡姆剃刀：用最少的文件/字段/步骤/依赖满足当前目标；仅在消除歧义、防严重错误、或必要验证时加复杂度。""",
    ),
    (
        "methodology",
        "old-project-minimal-migration",
        ["context-engineering", "migration", "skeleton"],
        "old-project-minimal-migration, context-engineering-v1",
        "旧项目最小迁移：保留旧结构只补协作层 + 事实来源映射 + 真实首轮迭代",
        r"""旧项目接入 context-engineering-v1 最小迁移方法论：
1. 不先整体重构；保留原目录与业务文件，只补最小协作层。
2. 先写「事实来源映射表」（旧资料各对应哪份文件），比迁移文件更有用；迁移前先在 AGENTS/WORK 写清旧资料的事实来源位置。
3. 只补 AGENTS/CHARTER/WORK/RUNLOG 四核心文件（已有内容优先复用而非重写），够了就停。
4. 先定义当前 MVP，完成 1 轮真实小迭代（给现有代码加可测试小能力）验证骨架闭环；迁移经验仅在真实使用后沉淀为方法论卡，无真实模式时不臆造结构。
5. status 一键快照类子命令是高 ROI 起步，跨会话 10 秒定位状态。
避坑：不造第二个当前状态文件；RUNLOG 只追加、最新在前；注入/写文件保持幂等。""",
    ),
    (
        "methodology",
        "iteration-gate",
        ["context-engineering", "gate", "workflow"],
        "context-engineering-v1, unified-memory-hub-workflow",
        "4 字段迭代闸门：收益/时间/Token/阻塞，三选一决策",
        r"""【迭代闸门】仅 4 字段：下轮预期收益 / 时间成本 / Token 成本 / 当前阻塞严重度；每轮结束用其判断继续/收尾/需人工。
决策三选一：继续下轮 / 进入维护收尾 / 需人工判断；一句话解释不清则闸门过模糊。""",
    ),
    (
        "methodology",
        "phase-restart",
        ["context-engineering", "restart", "workflow"],
        "context-engineering-v1",
        "阶段重启时机与重启前更新 WORK/RUNLOG，按序启动",
        r"""【阶段重启】阶段完成、目标变更、对话过长混杂、结构可交接、或转交其他 agent 时压缩重启；非每个小任务都清上下文。
重启前更新 WORK.md（当前 MVP/已完成/下一有用补充/阻塞/验证方法）、RUNLOG.md 追加阶段记录；按 AGENTS→CHARTER→WORK→briefs→results 顺序启动，不以历史聊天为主源。""",
    ),
    (
        "methodology",
        "ideation-github-scan",
        ["context-engineering", "research"],
        "context-engineering-v1",
        "立项研究：轻量 GitHub 扫描产出「借鉴/避开」最小指引",
        r"""【立项研究】立项后首次详细规划前做 1 次轻量 GitHub 扫描（3-5 个相关仓库，高星优先再按契合度/时效/issue 质量过滤），只产出「借鉴什么/避开什么」的最小指引，方向不变不重跑。""",
    ),
    (
        "methodology",
        "project-visual-guide",
        ["context-engineering", "visualize"],
        "context-engineering-v1",
        "骨架稳定后补一页项目可视化（Mermaid/结构化 MD）",
        r"""【可视化】骨架稳定后补一页项目可视化（project-visual-guide.md，Mermaid/结构化 MD）；小任务可跳过。""",
    ),
    (
        "methodology",
        "next-roi-suggestion",
        ["context-engineering", "planning"],
        "context-engineering-v1",
        "每完成一个能力推荐 2-3 个高 ROI 方向，只挑 1 个",
        r"""【下一步推荐】每完成一个能力后推荐 2-3 个高 ROI 方向（收益/时间/Token/主要风险），只挑 1 个推荐。""",
    ),
    (
        "methodology",
        "feedback-loop",
        ["context-engineering", "skill", "feedback"],
        "context-engineering-v1",
        "经验回流：候选回流 skill，防重错/可复用才晋升本体",
        r"""【经验回流】项目经验以候选形式回流 skill（feedback-candidates），不自动规则化；仅当可复用、防重错、或简化流程时才晋升 skill 本体。""",
    ),
    (
        "methodology",
        "env-injection-yaml",
        ["hermes", "mcp", "yaml", "env"],
        "on-this-wind",
        "可靠注入 env 配置：Python + yaml.dump 直接编辑 YAML",
        r"""【可靠注入 env 配置】用 Python + yaml.dump 直接编辑 YAML 以确保 `env:` 块正确（`hermes mcp add --env` 有时把 key 放进 args 而非 env:，不可靠）。""",
    ),
    (
        "methodology",
        "github-skill-update-flow",
        ["github", "skill", "workflow"],
        "github-repos-and-skills, 技能-fan-inspiration-的-git",
        "技能更新流程：改本地 → 同步镜像 → git add/commit/push",
        r"""【技能更新流程】改完本地技能目录后同步到镜像工作副本，再 git add -A && git commit && git push：
- context-engineering-v1：克隆上游 → 覆盖 `~/.workbuddy/skills/context-engineering-v1/`
- Fan-inspiration：改完 `~/.workbuddy/skills/Fan-inspiration/` → 同步到 `D:/AIwork/20260811-Fan-LingGan/Fan-inspiration/` → push""",
    ),
    # ============ longterm/ 长期记忆（用户级稳定档案，跨项目） ============
    (
        "longterm",
        "communication-language",
        ["user", "preference"],
        "user-preferences",
        "沟通语言：中文",
        r"""Communication language: Chinese（中文沟通）。""",
    ),
    (
        "longterm",
        "ai-model-stack",
        ["user", "tech-stack"],
        "tech-stack",
        "技术栈：熟悉 GPT/Claude/Grok/MiniMax/DeepSeek v4-flash",
        r"""Familiar with AI models (GPT, Claude, Grok, MiniMax, DeepSeek v4-flash)（技术栈）。""",
    ),
    (
        "longterm",
        "github-account",
        ["user", "github", "account"],
        "github-repos-and-skills",
        "GitHub 账号 creamxiao117，MCP github 已配 gh CLI token",
        r"""用户 GitHub 账号 creamxiao117；MCP github 已配 gh CLI token（keyring 托管，scopes: repo/workflow/gist）。""",
    ),
    (
        "longterm",
        "github-repos",
        ["user", "github", "repos"],
        "github-repos-and-skills",
        "主要私有/公开 repo 清单",
        r"""主要私有 repo：AlBrook-sysv2、PKPM-Agent、md-GuanLi、codex-approval-guard；公开：FAN-context-engineering、Check-Code-v1、Code-rule、Fan-ComputerUse。""",
    ),
    (
        "longterm",
        "skill-context-engineering-repo",
        ["user", "skill", "repo"],
        "github-repos-and-skills",
        "context-engineering-v1 上游仓库与技能包位置",
        r"""用户级技能 context-engineering-v1 上游仓库：`git@github.com:creamxiao117/FAN-context-engineering.git`，技能包在 `outputs/context-engineering-v1-skill/`；BeeAgent 仓库不含此技能。""",
    ),
    (
        "longterm",
        "skill-fan-inspiration-repo",
        ["user", "skill", "repo"],
        "技能-fan-inspiration-的-git",
        "Fan-inspiration 仓库与本地镜像工作副本",
        r"""技能 Fan-inspiration 仓库：`git@github.com:creamxiao117/Fan-inspiration.git`（SSH）；内容：灵感碎片→Obsidian 知识库流水线技能（`SKILL.md` + `scripts/{import_new,gen_synthesis,refine_pending}.py` + README）。
本地镜像工作副本：`D:/AIwork/20260811-Fan-LingGan/Fan-inspiration/`（已 `git push -u origin main`）。""",
    ),
    (
        "longterm",
        "onedrive-account",
        ["user", "onedrive", "account"],
        "fan-节奏：上下文-6",
        "OneDrive 个人账号与 UserFolder",
        r"""OneDrive 个人账 creamxiaonan@outlook.com，UserFolder=C:\Users\Fan-SJSS\OneDrive。""",
    ),
    (
        "longterm",
        "memory-hub-location",
        ["memory-hub", "constraints"],
        "constraints",
        "统一记忆中枢位置（约束）",
        r"""统一记忆中枢位置：C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub。""",
    ),
    # ============ projects/ 项目记忆（绑定具体项目/平台/环境的事实） ============
    (
        "project",
        "omniroute-gateway",
        ["omniroute", "llm", "gateway", "docker"],
        "omniroute-gateway",
        "OmniRoute 本机容器（diegosouzapw/omniroute，绑 127.0.0.1:20128）",
        r"""OmniRoute 本机 docker 容器（diegosouzapw/omniroute，绑 127.0.0.1:20128，本地无鉴权），Hermes 经它路由 LLM（providers.omniroute.api_key 18 字符）。""",
    ),
    (
        "project",
        "omniroute-container-networking",
        ["omniroute", "docker", "networking"],
        "omniroute-gateway",
        "容器内访问须用容器名 http://omniroute:20128/v1",
        r"""容器内访问 OmniRoute 须用容器名 http://omniroute:20128/v1（127.0.0.1 在容器内不通宿主机）。""",
    ),
    (
        "project",
        "omniroute-local-config",
        ["omniroute", "config", "llm"],
        "omniroute-gateway",
        "engine.config.yaml：gateway 11434 / qwen2.5:7b / 超时 30s（workbuddy 合并）",
        r"""本机配置 engine.config.yaml 记录 gateway_url http://127.0.0.1:11434、默认模型 qwen2.5:7b、超时 30s；与 20128 端口存在出入，使用时以实际生效配置为准（来源 workbuddy 平台记忆合并）。""",
    ),
    (
        "project",
        "cad2020-tachart",
        ["cad2020", "tachart", "config"],
        "cad2020拆图：候选",
        "拆图候选 V20260813_08；非标=E设计UDM；PMP 须 UI",
        r"""CAD2020 拆图候选 V20260813_08；非标=E设计UDM（A1+0.5=1272×603），PMP 须 UI 非「无」。""",
    ),
    (
        "project",
        "cad2020-kplot",
        ["cad2020", "kplot", "config"],
        "cad2020拆图：候选",
        "E设计 KPlot：关配套 DWG → KPrintSet 取消 Dwg 拆分",
        r"""E设计 KPlot：关配套 DWG → KPrintSet 取消 Dwg 拆分设置。""",
    ),
    (
        "project",
        "cad2020-pdf-merge",
        ["cad2020", "pdf", "troubleshooting"],
        "cad2020拆图：候选",
        "查看全部失败先查 {batch}.pdf 是否 15B 空壳（合并失败）；总图 A/B 区分",
        r"""查看全部失败先查 PDF 总图 {batch}.pdf 是否 ~15B 空壳（合并失败）；总图 A=批次合并 PDF，总图 B=业务 Model（建筑），勿混。""",
    ),
    (
        "project",
        "cad2020-upload",
        ["cad2020", "upload", "workflow"],
        "cad2020拆图：候选",
        "拆图/上传分离，不自动上传",
        r"""拆图/上传分离，不自动上传。""",
    ),
    (
        "project",
        "hermes-context-usage",
        ["hermes", "desktop", "context"],
        "hermes-桌面「上下",
        "Hermes 桌面上下文用量右键勾选；localStorage 压过代码默认",
        r"""Hermes 桌面「上下文用量」可右键勾选；localStorage 会压过代码默认，仅改 statusbar-prefs 可能仍需勾一次。""",
    ),
    (
        "project",
        "hermes-fan-debug-v1",
        ["hermes", "skill", "debug"],
        "hermes-桌面「上下",
        "fan-debug-v1 技能：运行时/默认值/cwd 分层调试",
        r"""技能 fan-debug-v1：运行时/默认值/cwd 分层调试，与 hermes-customization 双向关联。""",
    ),
    (
        "project",
        "hermes-default-project-dir",
        ["hermes", "project-dir"],
        "桌面默认项目目录=f-h",
        r"桌面默认项目目录 F:\Hermes；侧边栏显示 main",
        r"""桌面默认项目目录=F:\Hermes（%APPDATA%\Hermes\project-dir.json）→ 无显式路径的新建会话落 F:\Hermes，侧边栏按 cwd 分组、该组显示为 git 分支名「main」（2026-08-11 实测确认，不是「Hermes」）。""",
    ),
    (
        "project",
        "clash-verge-config",
        ["clash", "proxy", "config"],
        "fan-节奏：上下文-6",
        "Clash Verge 路径/端口/secret 配置",
        r"""Clash Verge=%AppData%\cashrev，mixed 7897，API 127.0.0.1:9097，secret=运行时 caserg.yaml（常 set-your-secret）。""",
    ),
    (
        "project",
        "memory-hub-facts",
        ["memory-hub", "architecture"],
        "unified-memory-hub-workflow",
        "中枢事实：唯一事实源/单写者锁/CLI 子命令",
        r"""统一记忆中枢事实：唯一事实源 AgentMemoryHub/，单写者锁 .sync/locks/writer.lock；CLI 入口 hub-engine/engine.py，子命令 retrieve/ingest/confirm/distill/tidy/lint/chat/status。""",
    ),
    (
        "project",
        "memory-hub-inject-targets",
        ["memory-hub", "inject", "platform"],
        "unified-memory-hub-workflow",
        "中枢注入目标：trae→user_profile.md；code→CLAUDE.md",
        r"""中枢注入目标（幂等）：trae → user_profile.md；code → D:/AIwork/code-memory/CLAUDE.md。""",
    ),
    (
        "project",
        "gateway-weixin",
        ["gateway", "weixin", "bot"],
        "gateway：weix",
        "Weixin iLink 已通（account 1c9c99bd5050@im.bot）",
        r"""Gateway：Weixin iLink 已通（account 1c9c99bd5050@im.bot，DM 白名单=扫码用户）。""",
    ),
    (
        "project",
        "gateway-yuanbao",
        ["gateway", "yuanbao", "bot"],
        "gateway：weix",
        "Yuanbao 网关已通（bot_d95f860d…）",
        r"""Gateway：Yuanbao 已通（bot_d95f860d…）。""",
    ),
    # ============ experience/ 经验（踩坑/排障/实测结论） ============
    (
        "exp",
        "browser-chrome-single-instance",
        ["browser", "chrome", "troubleshooting"],
        "browser-automation-chrome",
        "驱动失败常因端口被残留调试实例占用；保持单实例并清理",
        r"""浏览器驱动失败常因端口被残留调试实例占用——保持单实例调试 Chrome，结束后清干净。""",
    ),
    (
        "exp",
        "hermes-preview-not-chrome",
        ["hermes", "browser", "troubleshooting"],
        "hermes-previ, browser-automation-chrome",
        "Hermes preview 可能≠真实 Chrome，驱动前核对窗口句柄",
        r"""Hermes preview 可能≠真实 Chrome；驱动前核对窗口句柄/标题。""",
    ),
    (
        "exp",
        "msys-pathconv",
        ["hermes", "msys", "mcp", "troubleshooting"],
        "on-this-wind",
        "MSYS 路径转换破坏 MCP 子进程：MSYS_NO_PATHCONV 修复",
        r"""On this Windows host, MSYS automatically converts `/c/Users/...` paths to `F:\c\Users\...`, breaking MCP server subprocesses. Fix: set `MSYS_NO_PATHCONV=1` before `hermes mcp add` and use native Windows paths (`C:/Users/Fan-SJSS/...`).""",
    ),
    (
        "exp",
        "hermes-mcp-env-yaml",
        ["hermes", "mcp", "yaml", "troubleshooting"],
        "on-this-wind",
        "hermes mcp add --env 把 key 放 args 而非 env: 的坑",
        r"""hermes mcp add --env 有时把 key 放进 args 而非 env: 字段；可靠注入方法见 methodology/env-injection-yaml。""",
    ),
    (
        "exp",
        "lint-ignores-not-work",
        ["markdownlint", "check-code", "troubleshooting"],
        "lint-runtime-data-exclude",
        "markdownlint ignores 键对显式文件列表不生效，用 .check-code.toml exclude",
        r"""markdownlint-cli 0.49.1 的 config `ignores` 键对显式传入的文件列表不生效，勿依赖；落地排除用 .check-code.toml `[check-code] exclude = ["AgentMemoryHub"]`（按路径段匹配整目录）。""",
    ),
    (
        "exp",
        "query-writeback-dll",
        ["autocad", "dll-lock", "writeback"],
        "query-writeback",
        "查询回写实例：DLL 被锁查询确认「预防优于补救」",
        r"""查询产物回写实例：查询「DLL 被锁」命中规则后回写确认结论——预防优于补救，开发期即采用递增版本命名，避免发布后被 AutoCAD 锁文件。""",
    ),
    (
        "exp",
        "wechat-qr-scan-png",
        ["weixin", "qrcode", "troubleshooting"],
        "gateway：weix",
        "微信扫码须导出 PNG 用图片查看器打开（桌面用户看不见终端 ASCII）",
        r"""微信扫码须导出 PNG 并主窗口/图片查看器打开（桌面用户看不见终端 ASCII）。""",
    ),
    (
        "exp",
        "duoyuanx-balance-gate",
        ["duoyuanx", "billing", "troubleshooting"],
        "gateway：weix",
        "duoyuanx 余额<$0.01 会 403（有余额仍可能被拒）",
        r"""duoyuanx 预扣门槛：余额<$0.01 会 403（有余额仍可能被拒）。""",
    ),
    (
        "exp",
        "proxy-guard-ie-override",
        ["proxy", "clash", "troubleshooting"],
        "fan-节奏：上下文-6",
        "proxy_guard 会冲掉 IE ProxyOverride",
        r"""proxy_guard 会冲掉 IE ProxyOverride。""",
    ),
    (
        "exp",
        "ms-login-skill-pointer",
        ["microsoft", "login", "skill"],
        "fan-节奏：上下文-6",
        "微软登录排障见技能 windows-proxy-ms-login",
        r"""微软登录排障见技能 windows-proxy-ms-login。""",
    ),
]

INDEX_HEADER = """# 中枢索引（内容目录）

统一记忆中枢索引。知识原子按五类判别树归类：

- rules/        权威规则（命令式/约束式，违反有代价）
- methodology/  方法论（可复用步骤/流程/思考原则）
- longterm/     长期记忆（用户级稳定档案，跨项目）
- projects/     项目记忆（绑定具体项目/平台/环境的事实）
- experience/   经验（踩坑/排障/实测结论）
- libs/         复用代码库 / 插件片段
- retro/        复盘 + 时间线（retro/log.md）
- archive/      过时内容归档

## 使用约定（各平台执行前必读）
1. 执行前先查 INDEX.md 与五类目录（rules / methodology / longterm / projects / experience），命中再执行。
2. 不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。
3. 查询好结果回写为经验卡片（查询产物回写）。

## 检索方式
- 确定性：直接读对应目录文件。
- 语义：`python hub-engine/engine.py retrieve --root <中枢> "<问题>"`
"""

# 索引行：保持 ATOMS 定义顺序，按类分组
INDEX_GROUPS = [
    ("rule", "规则（rules/）"),
    ("methodology", "方法论（methodology/）"),
    ("longterm", "长期记忆（longterm/）"),
    ("project", "项目记忆（projects/）"),
    ("exp", "经验（experience/）"),
]

INDEX_TAIL = """## 沉淀通道
- 各平台内容先写入 .sync/drafts/<platform>_draft/，经同步器校验后提升。
"""


def generate_cards() -> list[Path]:
    """写出所有原子卡，返回生成的文件路径列表"""
    written = []
    for cls, file, tags, source, _desc, body in ATOMS:
        card = Card(
            type=cls,
            tags=tags,
            updated=TODAY,
            status="active",
            reuse_count=0,
            extra={"source": source},
            body=body,
        )
        path = HUB / CLS_DIR[cls] / f"{file}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(write_card(card), encoding="utf-8")
        written.append(path)
    return written


def build_index() -> None:
    """重建 INDEX.md：头部 + 五类索引 + 来源对照表"""
    lines = [INDEX_HEADER]
    for cls, title in INDEX_GROUPS:
        lines.append(f"## {title}")
        for c, file, _tags, _source, desc, _body in ATOMS:
            if c == cls:
                lines.append(f"- {file}    {desc}")
        lines.append("")
    # 来源对照表：旧卡 → 拆出的原子卡（按 source 聚合）
    src_map: dict[str, list[str]] = {}
    for _cls, file, _tags, source, _desc, _body in ATOMS:
        for s in (x.strip() for x in source.split(",") if x.strip()):
            src_map.setdefault(s, []).append(file)
    lines.append("## 来源对照（原 26 卡 → 原子卡）")
    lines.append("| 原卡片 | 拆分为 |")
    lines.append("| --- | --- |")
    for src in sorted(src_map):
        lines.append(f"| {src} | {', '.join(sorted(src_map[src]))} |")
    lines.append("")
    lines.append(INDEX_TAIL)
    (HUB / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    written = generate_cards()
    build_index()
    counts: dict[str, int] = {}
    for c, _f, _t, _s, _d, _b in ATOMS:
        counts[c] = counts.get(c, 0) + 1
    print(f"生成原子卡 {len(written)} 张：{dict(sorted(counts.items()))}")
    print(f"中枢：{HUB}")


if __name__ == "__main__":
    main()
