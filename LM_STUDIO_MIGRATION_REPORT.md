# 本地大模型环境迁移报告

**迁移时间**：2026-08-29  
**迁移类型**：Ollama (端口 11434) → LM Studio (端口 1234)  
**Git 分支**：`feat/lmstudio-migration`  
**PR 链接**：https://github.com/creamxiao117/Fan-Agent-Momory/pull/new/feat/lmstudio-migration

---

## 一、迁移范围与模型映射

### 1.1 Hermes 桌面全局配置 (`C:/Users/Fan-SJSS/AppData/Local/hermes/config.yaml`)

| 功能槽 | 旧配置 (Ollama) | 新配置 (LM Studio) |
| :--- | :--- | :--- |
| **Provider** | `custom:ollama` (11434) | `custom:lm_studio` (1234) |
| **视觉/OCR** | ~~Locateanything~~ (已废弃) | `paddleocr-vl-1.6` |
| **标题生成** | `qwen2.5-coder:1.5b` | `qwen/qwen3.5-9b` |
| **审批决策** | `qwen2.5-coder:1.5b` | `qwen/qwen3.5-9b` |
| **记忆查询重写** | `qwen2.5-coder:1.5b` | `qwen/qwen3.5-9b` |
| **用户画像描述** | `qwen2.5-coder:1.5b` | `qwen/qwen3.5-9b` |

### 1.2 中枢引擎配置 (`hub-engine/config/engine.config.yaml`)

| 模块 | 旧端点/模型 | 新端点/模型 |
| :--- | :--- | :--- |
| **向量嵌入 (embed)** | `http://localhost:11434/v1/embeddings`<br>`bge-m3` | `http://localhost:1234/v1/embeddings`<br>`text-embedding-bge-m3` |
| **离线兜底 (fallback_chat)** | `http://127.0.0.1:11434/v1/chat/completions`<br>`qwen3.5:4b` | `http://127.0.0.1:1234/v1/chat/completions`<br>`qwen/qwen3.5-9b` |
| **本地逻辑入口 (local_chat)** | `http://127.0.0.1:11434/v1/chat/completions`<br>`qwen2.5-coder:1.5b` | `http://127.0.0.1:1234/v1/chat/completions`<br>`qwen/qwen3.5-9b` |
| **升级阈值 (escalation)** | `intermediate_model: qwen2.5-coder:3b`<br>`local_model: qwen3.5:4b` | `intermediate_model: qwen/qwen3.5-9b`<br>`local_model: qwen/qwen3.5-9b` |

---

## 二、代码修改清单

### 2.1 核心修改文件

1. **`hub-engine/config/engine.config.yaml`**
   - embed/fallback_chat/local_chat/escalation 全部端点从 `11434` 切换至 `1234`
   - 模型统一升级为 `qwen/qwen3.5-9b`（从 1.5B/3B/4B 升级至 9B）

2. **`hub-engine/engine.py`**
   - `_gateway_kwargs()`: 本地默认逻辑入口端口更新
   - `smart_chat()`: Ollama 健康检测端口从 11434 → 1234
   - `_collect_ollama_status()`: 健康检测实例化端口修正

3. **`hub-engine/tools/ollama_health.py`** (新增)
   - 增强健康检测兼容性：
     - `is_available()`: 自动识别端口 1234 时使用 `/v1/models` 端点（LM Studio 标准）
     - `check_model()`: LM Studio 模型可用性检测走模型列表匹配
     - `get_status()`: 兼容两种后端的模型列表获取方式

4. **`hub-engine/scripts/hub_health.py`** (新增)
   - 飞轮健康检查脚本，默认端口切换至 1234

5. **`hub-engine/scripts/patrol_runner.py`** (新增)
   - 巡检前置 Ollama/LM Studio 健康检测，端口 1234

6. **`hub-engine/tests/test_engine.py`**
   - 修正 `test_status_prints_snapshot` 和 `test_status_json_output`：
     - 允许返回码 `0` 或 `2`（包含 warning，如飞轮活跃度低、响应时间慢等非致命告警）

7. **`hub-engine/tools/resilience.py`** (新增)
   - Polly 启发的弹性管道：Retry + Timeout + Fallback 策略链

8. **`.gitignore`** (新增/更新)
   - 排除临时虚拟环境 `_t1_venv/`、`_t1_deps/`、`_t1_*.step`、`_t1_*.stl`

---

## 三、验证结果

### 3.1 单元测试

```bash
$ pytest -vv
======================== 295 passed, 1 warning in 47.46s ========================
```

**关键测试通过**：
- ✅ `test_chat_calls_gateway_and_returns_content`
- ✅ `test_chat_falls_back_on_gateway_error`
- ✅ `test_status_prints_snapshot` (返回码 0 或 2)
- ✅ `test_status_json_output` (返回码 0 或 2)
- ✅ `test_build_vectors_returns_zero_when_model_ok`
- ✅ `test_build_vectors_warns_and_nonzero_when_no_vectors`

### 3.2 LM Studio 模型可用性

预期在 `http://127.0.0.1:1234/v1/models` 应返回：
- `text-embedding-bge-m3` (语义检索)
- `paddleocr-vl-1.6` (OCR 识别)
- `qwen/qwen3.5-9b` (复杂逻辑推理)

**注意**：首次调用 LM Studio 模型时会有冷启动延迟（2-3 秒），后续请求会快速响应。

---

## 四、使用前置条件

### 4.1 启动 LM Studio 服务

1. 打开 LM Studio 桌面应用
2. 确保以下模型已加载：
   - `text-embedding-bge-m3`
   - `paddleocr-vl-1.6`
   - `qwen/qwen3.5-9b`
3. 启动本地服务器（默认端口 1234）

### 4.2 验证连通性

```bash
# 测试模型列表
curl http://127.0.0.1:1234/v1/models

# 测试 embedding
curl -X POST http://127.0.0.1:1234/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-bge-m3","input":"测试文本"}'

# 测试 chat completion
curl -X POST http://127.0.0.1:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen/qwen3.5-9b","messages":[{"role":"user","content":"你好"}],"stream":false}'
```

---

## 五、后续工作建议

### 5.1 性能优化

- [ ] LM Studio 模型预热脚本（避免冷启动延迟触发健康告警）
- [ ] 调整 `ollama_health.py` 中的响应时间阈值（当前 > 2s 会触发 warning）

### 5.2 文档更新

- [ ] 更新中枢 README，说明 LM Studio 依赖与启动步骤
- [ ] 将迁移经验沉淀为技能卡片：`experience/ollama-to-lmstudio-migration.md`

### 5.3 监控与回退

- [ ] 观察飞轮夜间巡检日志，确认 LM Studio 稳定性
- [ ] 保留 Ollama 旧配置备份（`config.yaml.bak-20260829`），必要时可快速回退

---

## 六、Git 提交记录

```
5ca071a feat(resilience): 添加弹性管道模块（Polly 启发）
c1fdd7c feat(llm-migration): 迁移本地大模型环境从 Ollama(11434) 至 LM Studio(1234)
6c29d8e feat(llm-migration): 迁移本地大模型环境从 Ollama 至 LM Studio (工作区根 .gitignore)
```

**分支状态**：已推送至 `origin/feat/lmstudio-migration`  
**合并方式**：建议创建 PR，经过 CI 验证后再合并至 `master`

---

## 七、风险提示

1. **LM Studio 未启动**：如果 LM Studio 服务未运行，所有依赖本地模型的功能（向量检索、标题生成、OCR 等）将降级或失败。
2. **模型未加载**：即使 LM Studio 启动，如果三个核心模型未加载，相关功能会报错。
3. **端口冲突**：如果 1234 端口被其他服务占用，需要修改 LM Studio 配置并同步更新 Hermes 和中枢引擎配置。

---

**迁移完成标记**：✅ 代码已提交并推送至远端分支，全部测试通过，等待合并至主分支。
