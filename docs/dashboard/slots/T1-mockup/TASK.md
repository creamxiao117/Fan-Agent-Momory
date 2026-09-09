# T1 任务: 中枢总控台静态 Mockup（修正版 V2）

## 你的角色
你是 M2.7 子 Agent，由 M3 主 Agent 派发。
任务：写中枢总控台 dashboard 的静态 mockup（HTML，1 个文件）。

## 关键路径修正
- popular-web-designs SKILL.md: `C:/Users/Fan-SJSS/AppData/Local/hermes/skills/creative/popular-web-designs/SKILL.md`
- **Linear 模板**（你要用的）: `C:/Users/Fan-SJSS/AppData/Local/hermes/skills/creative/popular-web-designs/templates/linear.md`
- TASK.md 自身: `C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/work/dashboard/slots/T1-mockup/TASK.md`（就是本文件）

## 设计意图（来自 M3 主 Agent 规划）
中枢总控台合并 3 个旧看板（flywheel-timeline.html / hub-health.html / memory-hub-flywheel-v2.html）。
新版 6 大区：
1. **总体健康** — 综合评分 + 5 平台状态汇总
2. **5 平台连接状态** — Hermes/trae/workbuddy/DSH/Mavis 各自状态
3. **飞轮运转** — 5 阶段活跃度（卡片摄取/向量构建/去重/归纳/纪律）
4. **知识缺口** — 24h miss rate
5. **待人工处理** — T19/T21 待办 + 规则卡 pending
6. **告警** — critical / error 实时显示

## 关键禁止
- ❌ **不要用 `find` 命令扫描全盘**（会卡死）
- ❌ **不要 `import` / `write_file` 大文件**（用 patch 工具小段改）
- ✅ **用 search_files（glob 模式）或 read_file（绝对路径）**读文件
- ✅ **最终 mockup.html 控制在 300-500 行**

## 完成步骤
1. `read_file` SKILL.md（看 Linear 风格说明）
2. `read_file` linear.md（看 Linear CSS/HTML 模板）
3. `read_file` 旧看板 `C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/flywheel-timeline.html`（理解现有 UI）
4. `write_file` mockup.html 到 T1-mockup 目录（用 popular-web-designs/linear 风格，6 大区布局）
5. `write_file` done.txt = "OK"
6. `write_file` result.txt 一句话总结

## 时间预算
- 读 3 个文件: 5s
- 思考设计: 10s
- 写 mockup.html: 15s
- 总计: **30s 内完成**

## 失败信号
如果 `read_file` SKILL.md 或 linear.md 返回 None → **立即写 done.txt=FAIL: SKILL.md 路径错** 然后退出。

完成直接报告，不要问问题。