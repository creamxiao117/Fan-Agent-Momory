# SkillHub 登记收尾（2026-10-05）—— 取代 batch1 分类清单

> 取代 `2026-10-05-skillhub-registration-batch1.md`（那版数字已过期：当时 62/22，含已修的两类假阳性）。
> 数据源：`capability_reconcile`（已修假阳性）+ 7 个技能根实测扫描。规则：用户裁定「默认登记，仅排除 `HERMES_*` 与自称独享」。

## 一、机制修复（本轮，均已实证）

| 修复 | 效果 |
|---|---|
| `registry_coverage.impl` 判据 → `skill.yaml` ∪ `SKILL.md` | 依据 schema「记录逐一对应 skills/<name>/skill.yaml」 |
| `capability_scan.list_skills` 不再把**分类目录**当技能 | measured_installed 83 → 71；unregistered 62 → 51 |
| 本轮再删 5 条真死记录 | router records → 125 |
| 判定修正 | `code-rule` 曾被关键词**误排除**——用户明确要求共享，已改回待登记 |

## 二、仍待登记（共享）48 条

1. Fan-Control-PC
2. Fan-inspiration
3. agent-platform-onboarding
4. autocad-com-automation-test
5. baidu-drive
6. bailian-cli
7. bailian-docs-llm-wiki
8. bailian-finetune
9. bailian-gen
10. bailian-managed-agent
11. bailian-model-recommend
12. bailian-protocol
13. bailian-train-deploy
14. bailian-web-search
15. browser-automation-toolbox
16. build-new-task
17. cad-screenshot-pixel-forensics
18. computer-interface-controller
19. context-driven-development
20. darwin-skill
21. desktop-preview-reveal
22. doc-text-extract
23. github-trending-cn
24. hatch-pet
25. ima-skills
26. impeccable
27. janee
28. kdocs
29. local-proxy-timeout-diagnosis
30. markitdown-skill
31. mcp-server-setup
32. minimax-xlsx
33. neodata-financial-search
34. notebooklm-studio
35. npm-cli-relocate-custom-prefix
36. oracle
37. pdfkit-py
38. skillhub-integration
39. tencentcloud-ocr
40. web-board-browser-regression
41. westockdata
42. windows-file-access-denied-forensics
43. windows-safe-file-cleanup
44. workbuddy-custom-model-tuning
45. workbuddy-host-env-shim-isolation
46. wsl2-ops-on-windows
47. xiaoshi-quant-expert
48. 腾讯文档

## 三、排除 3 条

| 名称 | 理由 |
|---|---|
| HERMES_RULES_ROUTING | HERMES_* Hermes 自有（用户裁定不共享） |
| code-rule | SKILL.md 自称独享 |
| note-taking | 客户端目录未定位到 SKILL.md（疑目录名≠技能名） |

> `HERMES_RULES_ROUTING` = Hermes 自有（不共享）；`code-rule` 的排除是**误判已撤销**（见下）；`note-taking` 需先定位实现。

## 四、两个需要你知道的单点

1. **`pdf-reader`**：记录保留。其实现只存在于 `~/.trae-cn/skills/pdf-reader`，而 **trae 已退役** ⇒ 该来源已不在 hub.config.yaml 的 `skills_dir` 里。
   故它现在既不算「实测已装」也不算「有实现」——这不是 bug，是 trae 退役的连带效果。要保留就需把它迁到在役平台的技能目录。
2. **`notebooklm-studio`**：**是真技能不是分类目录**（`~/.workbuddy/skills/notebooklm-studio/SKILL.md` 存在）⇒ 归入 48 条待登记，不是假阳性。

## 五、下一步（批次 2 的正确形态）

对这 48 条走「三件套」：`skills/<name>/SKILL.md`（迁移或新建）+ `skill.yaml` + router 记录，
trigger 用短 token、`deploy_scope` 显式给值（默认 `task`）。**注意**：
`blueprint`/`exp` 类中枢卡**不登记为技能**已实测结案（+132 蓝图 ⇒ 7 条路由金标准失败）。
