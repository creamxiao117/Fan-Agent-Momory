# 清理记录：`work/` 下的历史基准夹具（2026-09-24）

> 背景：全局审计发现 `work/` 占 **1,564 MB**，其中绝大部分是**过去一次性基准任务**留下的
> 第三方源码树副本（未跟踪、已 gitignore，但占用磁盘）。本记录留档删除范围与**版本指纹**，
> 以便将来需要复现时能对上上游版本。

## 删除范围（4 个目录 / 1,553.1 MB）

| 目录 | 体积 | 文件数 | 内容 | 版本指纹 |
|:--|--:|--:|:--|:--|
| `work/t1-wasmtime` | 1,488.8 MB | 2,317 | wasmtime（Rust，含 `target/` 构建产物） | **wasmtime 29.0.1**；`Cargo.lock` SHA256 前缀 `BF4C9ACD0109F8D2` |
| `work/t1-orleans` | 32.0 MB | 268 | Orleans 示例（.NET） | .NET **10.0**；Orleans **10.3.1**（`DemoInterfaces` 为 9.0.1） |
| `work/t0_test` | 25.9 MB | 173 | `aspire-t1-test` / `SunnyUIT1` / `ReactiveUIT1` | 过去 T1 UI 任务产物 |
| `work/t1-bhom` | 6.4 MB | 1,474 | `BHoM-src` + `BHoMDemo` | — |

**合计 1,553.1 MB / 4,232 文件。**

## 为何确认可删（取证）

1. **零外部引用**：全仓（含 docs / rules / methodology / experience / 脚本 / 定时任务）扫描
   `work/t1-*`、`work/t0_test`，**无任何引用**。
2. **与现役功能无关**：都是过去基准任务的第三方源码树，不参与中枢任何数据流或门禁。
3. **非版本控制内容**：未跟踪且已 gitignore ⇒ 删除不影响任何 git 历史。
4. 唯一提及在 `AgentMemoryHub/retro/log.md`（历史流水账），属**记载**而非依赖。

## 保留了什么（**修正了原计划**）

原计划"删 `t1-*`/`t0_test`/`bench_scale`（≈1.58 GB）"，取证后**发现 `bench_scale` 与
`bench_vectors` 是自生成夹具，不能按"惰性"处理**——但经确认它们**由脚本自行重建**，故也无需删：

| 目录 | 体积 | 为何保留 |
|:--|--:|:--|
| `work/bench_vectors` | 0.1 MB | **`vector_bench.py` 的夹具**（巡检活步骤 `vector_regression` 调用）。脚本内 `_ensure_hub()` 注明"幂等；已存在则跳过" ⇒ 自生成 |
| `work/bench_scale` | 10.1 MB | **`vector_scale_bench.py` 的夹具**，脚本自行"在隔离库中直接灌 N 条假向量" ⇒ 自生成 |
| `work/*.py`（顶层分析脚本） | ~250 KB | 本会话及历史分析脚本，仍需查阅 |

> ⚠️ **教训**：这两个目录被活代码引用，若按"体积大 + 看着像临时"就删，会破坏巡检的
> `vector_regression` 步骤——与 `patrol_runner_v3.py` 事件同一类错误。
> **判据必须是"有消费者吗"，不是"像不像临时文件"。**

## 如何恢复（如将来需复现）

- **wasmtime**：`git clone https://github.com/bytecodealliance/wasmtime`，检出 **29.0.1**
- **Orleans 示例**：dotnet 10 示例工程，Orleans 包版本见上表
- **BHoM**：上游 `BHoM` 仓库
- **t0_test / aspire-t1-test**：为项目自建产物，**已不可恢复**（无版本控制、无上游对应）；
  如遗留脚本仍需要，需重新创建

## 执行结果

见外层仓提交 `chore(cleanup): 移除 work/ 下历史基准夹具（1,553 MB）`。

---

# 清理记录：`.mimocode/node_modules`（2026-09-24）

## 是什么

项目内的 npm 依赖目录（`.mimocode/package.json` → `@mimo-ai/plugin@0.1.15`）。
**不是本项目代码**，不被任何仓内配置或定时任务引用。

## 删了什么 / 保留了什么

| 项 | 体积 | 处置 |
|:--|--:|:--|
| `.mimocode/node_modules/` | 48.75 MB / 3,449 文件 | **已删** |
| `.mimocode/package.json` + `package-lock.json` | 50 KB | **保留**（复原凭据） |
| `.mimocode/.cron-lock` | — | 保留（其记录的 PID 52084 **已不存在**，属残留锁） |

**为何只删 `node_modules` 而非整个 `.mimocode/`**：整目录仅多省 50 KB，却会失去
`npm install` 一句话复原的能力。**体积收益 99.9% 已到手，不取那 0.1% 的风险。**

## 取证（删前确认无活消费者）

1. **无进程引用**：枚举全部 `node.exe` 的命令行，`mimocode` 匹配 **0 个**
   （在跑的 node 进程是 MCP servers：github / filesystem / browser-use，及 pi 本体）
2. **无调度引用**：Windows 定时任务中无匹配；仓内无任何配置引用 `.mimocode`
3. **锁已失效**：`.cron-lock` 指向 PID 52084，该进程不存在（锁时间 2026-09-23 18:04）
4. **自管声明**：`.mimocode/.gitignore` 自身即把 `node_modules` / `package.json` /
   `package-lock.json` / `.cron-lock` 列为该工具自管项
5. **git 无关**：0 个被跟踪文件，`.gitignore:34` 已忽略 ⇒ 删除不动任何 git 历史

## 如何复原

```bash
cd .mimocode && npm install    # 依据 package-lock.json 还原 @mimo-ai/plugin 0.1.15
```

## 执行结果

实测释放 **54.49 MB**（含文件系统开销）；`.mimocode/` 由 48.8 MB 降至 **13.6 KB**。
未提交（该目录全部被 gitignore）。
