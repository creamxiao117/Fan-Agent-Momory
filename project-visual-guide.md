# 项目可视化指南 · 统一记忆中枢 v1

> 一页看懂：架构分层、内容流转、决策点与风险。供规划/交接/扩展方向对比用。

## 1. 系统架构与内容流转（流程图）

```mermaid
flowchart LR
    subgraph PLATFORM["接入层 · 各 Agent 平台"]
        T[trae] --> D1[写暂存区<br/>.sync/drafts]
        C[code<br/>(待接入)] --> D1
    end

    subgraph ENGINE["能力层 · hub-engine（本仓库）"]
        S[同步器 sync<br/>单写者锁 · 去重 · 确认] --> AUTH
        AUTH[权威区<br/>rules/libs/experience/projects]
        AUTH --> L[Lint 健康检查]
        AUTH --> R[混合检索 retrieve<br/>确定性 + 语义]
        AUTH --> TY[tidy 归档]
    end

    subgraph DATA["事实源层 · D:\\AIwork\\AgentMemoryHub"]
        D1 --> S
        PEND[.sync/pending<br/>待人工确认] --> CONFIRM{人工确认?}
        CONFIRM -- 是 --> AUTH
        CONFIRM -- 否/重复 --> REJ[丢弃/冲突]
        L --> REP[retro/lint-report]
        R --> Q[查询结果]
        Q --> WB[回写经验卡<br/>query-writeback]
        WB --> AUTH
    end

    R -- omniroute 问答 --> CHAT[chat]
```

## 2. 项目能力脑图（mindmap）

```mermaid
mindmap
  root((统一记忆中枢))
    数据层 D:\AIwork\AgentMemoryHub
      权威区 rules/libs/experience/projects/retro
      暂存区 .sync/drafts
      待确认 .sync/pending
      审计 Git 提交链
    能力层 hub-engine
      sync 同步器 单写者锁/去重/确认/Git
      distill 复盘→候选规则
      tidy 归档
      lint 健康检查 孤儿/陈旧/无效
      retrieve 混合检索 确定性+语义
      status 一键快照
      chat omniroute 问答 网关不可用回退本地
    平台层 trae(已注入)/code(待接入)
    协作骨架 context-engineering-v1
      AGENTS 启动入口
      WORK 状态唯一来源
      RUNLOG 迭代日志
      briefs 迭代简报
```

## 3. 核心决策点与风险

| 决策点/风险 | 处置 |
| --- | --- |
| 新规则提升 | 必须人工确认（ingest → pending → confirm） |
| 并发写入冲突 | 单写者锁 `.sync/locks/writer.lock` |
| 卡片失联 | Lint 孤儿/陈旧/无效 → 补 INDEX 引用或归档 |
| DLL 被 AutoCAD 锁 | 版本号必须递增（rules/dll-version-lock） |
| 网关不可用 | chat 回退本地文件检索，不中断 |
| 是否继续迭代 | 4 字段迭代门（收益/时间/Token/阻塞） |
