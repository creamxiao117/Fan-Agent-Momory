# 第二层落地实现方案：bge-small-zh + SQLite 向量语义检索

> 状态：设计待审
> 日期：2026-08-18
> 背景：第一层已落地（`tools/retrieve.py` 进程内存语料索引：tag/type 倒排 + token counts 缓存 + 目录签名失效）。第二层引入**语义向量检索**，在现有词袋确定性/语义通道之外叠加稠密向量召回，解决同义词、长句、跨语言语义召回。方案 A = 复用 md-GuanLi 已验证的 **bge-small-zh + SQLite JSON 向量** 路线，**不引入 FAISS**，保持增量、可回退、不过度设计。

## 目标与边界

- 目标：让 `retrieve` 能按"自然语言描述"召回语义相关卡（同义词/意译/跨语言），弥补现有词袋通道的盲区。
- 非目标（本期不做）：
  - 不引入 FAISS/ChromaDB（卡片量上数千再评估）——保持单依赖 `sqlite3`（标准库）
  - 不动 MCP 工具 schema（`hub_search` 等签名不变）
  - 不改变现有确定性 + 词袋语义通道的行为（新增通道为**叠加**，非替换）

## 架构总览

```
                    检索 query
                        │
              ┌─────────▼──────────┐
              │   unified search    │   ← 保留现有接口 entry
              └─────────┬──────────┘
                        │ 三个通道打分 → 融合
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
    确定性通道       语义通道(词袋)     向量通道(新增 bge-small-zh)
   tag/type 倒排    jieba+IDF 余弦     CLS embedding + 余弦
        │               │                │
        └──────┬────────┘                │
               ▼                         ▼
        第一层 _CorpusIndex          SQLite docs.embedding
   （进程内索引，新增失效机制复用）   （持久化，增量复用）

                融合策略：向量通道作为「语义扩展召回」，与现有语义通道
                用 RRF（Reciprocal Rank Fusion）或加权和合并，取 top_k
```

## 数据存储：SQLite 向量库（复用 md-GuanLi 模式）

新表置于中枢根下 `.sync/vector.db`（运行态数据，**不进 git**，与 `.sync/state/` 同级）。

```sql
CREATE TABLE IF NOT EXISTS docs (
    id      INTEGER PRIMARY KEY,
    path    TEXT UNIQUE,            -- 卡文件绝对路径
    mtime   REAL,                   -- 卡 mtime（失效签名）
    size    INTEGER,
    title   TEXT,
    tags    TEXT,                   -- 逗号拼接
    type    TEXT,                   -- rule/exp/methodology/...
    body    TEXT,                   -- 卡正文（含 frontmatter 剥离）
    embedding TEXT,                 -- JSON 序列化 512 维向量
    updated TEXT                    -- 卡 frontmatter 的 updated（可选）
);
CREATE INDEX IF NOT EXISTS idx_docs_path ON docs(path);
```

### 增量失效签名（复用第一层思想）

- 扫描与 `_CorpusIndex` 同一组目录 + 同一 `(mtime_ns, size)` 签名。
- 签名未变的卡：**复用已有行与向量**，跳过 embedding（省钱关键，md-GuanLi 已验证）。
- 签名变化 / 新增：重新 compute embedding 并 upsert。
- 源文件删除：清理孤儿行。

## embedding 实现（bge-small-zh）

加载放**惰性** + **进程级单例**（与 `_CorpusIndex` 一致，MCP 常驻进程内复用一次加载）。

```python
# tools/semsearch.py（新增）
import json, sqlite3, threading
from pathlib import Path

EMBED_MODEL = "BAAI/bge-small-zh-v1.5"   # 可被 AGENT_MD_EMBED_MODEL 覆盖
_lock = threading.Lock()
_model = _tok = None

def _load():
    global _model, _tok
    if _model is not None:
        return _model, _tok
    from transformers import AutoTokenizer, AutoModel
    import torch
    _tok = AutoTokenizer.from_pretrained(EMBED_MODEL)
    _model = AutoModel.from_pretrained(EMBED_MODEL)
    return _model, _tok

def embed(text: str):
    """返回 512 维 L2 归一化向量(list[float])；后端不可用时返回 None（退化词袋）"""
    try:
        model, tok = _load()
    except Exception:
        return None
    import torch
    inp = tok(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    with torch.no_grad():
        out = model(**inp)
    v = out.last_hidden_state[:, 0].float()      # CLS
    v = torch.nn.functional.normalize(v, dim=-1) # L2 归一化
    return v[0].numpy().tolist()
```

要点：
- **CLS + L2 归一化** → 余弦 = 点积（md-GuanLi 同款，已验证）。
- **未安装 transformers/无 GPU 时优雅退化**：`embed()` 返回 None，检索回退现有词袋通道，不报错。
- **数据规模考虑**：bge-small-zh 24M，内存 ~90MB，MCP 常驻可接受；首启需联网下载权重一次（~90MB），之后离线。

## 检索融合（不破坏现有通道）

在 `tools/retrieve.py` 新增 `semantic_vector_retrieve(root, query, top_k)`：

```python
def semantic_vector_retrieve(root, query, top_k=5):
    """向量通道：embed(query)，与库内每卡向量点积(余弦)，返回 top_k 卡。"""
    qv = embed(query)
    if qv is None:
        return []           # 后端不可用 → 返回空，走融合兜底
    rows = _read_vector_rows(root)   # 从 .sync/vector.db 读 path+embedding
    cands = [(cosine(qv, vec), path) for path, vec in rows]
    cands.sort(reverse=True)
    return [path for _, path in cands[:top_k]]
```

在现有 `retrieve` / `_semantic_scored` 的融合点接入：

- **方式：RRF 融合**——给现有语义通道得分 + 向量通道得分各打 rank 分（`1/(k+rank)`），求和取 top_k。确定性通道保底（同现有一致性，触及即高优先级）。
- 兜底：向量通道返回空（后端缺失）→ 完全回退现有词袋行为，**无行为回归**。

```
final_score(card) = α·wordScore(card) + β·vecRankScore(card)   # 或 RRF
top_k = 排序后截断
```

## 现有代码改动点（最小侵入）

| 文件 | 改动 |
|---|---|
| `tools/semsearch.py`（新增） | embed 加载/计算 + SQLite 建表/upsert/读取 |
| `tools/retrieve.py` | ① 扫描回调补写向量库（`build` 时）；② 新增 `semantic_vector_retrieve`；③ `retrieve/_semantic_scored` 融合向量通道；④ 保留公开函数签名 |
| `tests/test_semsearch.py`（新增） | SQLite upsert/增量回用/孤儿清理/退化兜底单测（**mock embed，不依赖模型/网络**） |

## 关键取舍与决策点

1. **SQLite 全表余弦**（方案 A 短板）：当前 ~65 卡，毫秒级；上千卡后变慢。**本期接受**，上几千上万卡再切 FAISS（届时只需替换 `_read_vector_rows` 为 ANN 查询，接口不变）。
2. **规范输入**：embed 的文本 = `title + tags + body`（与词袋 `_card_text` 对齐），确保语义与现有通道可比。
3. **模型可插拔**：保留 `AGENT_MD_EMBED_MODEL` 环境变量（沿用 md-GuanLi 约定），未来可直接切 bge-m3 无需改代码。
4. **按需触发**：向量通道默认在 `retrieve` 词袋结果为空或分数阈值低时才触发（省算力）；或始终并行取 top-k 融合。倾向**默认并行融合**，后端未装则自动跳过。

## 落地步骤（TDD）

1. 新增 `tools/semsearch.py`：SQLite 建表 + upsert + 读取（纯标准库可测）。
2. 单测 `test_semsearch.py`：mock `embed`，验证增量复用 / 新增 / 孤儿 / 退化兜底。
3. `tools/retrieve.py` 接入：写入向量库 + `semantic_vector_retrieve` + 融合。
4. 单测：融合后 top_k 含语义扩大召回，且后端缺失时行为与现状一致。
5. 全量 pytest + ruff + lint 验证，无回归。
6. 真机验证：装 transformers，实跑中英文查询对比词袋/向量召回率差异，落经验卡。

## 验收标准

- [ ] `retrieve` 后端可用时，中英文同义词/意译查询能召回（现状词袋召回不到的）
- [ ] 后端未装时，检索行为与**现状完全一致**（0 回归）
- [ ] 卡片增删改后重扫，未变更卡**不重新 embedding**（增量生效）
- [ ] 全量 pytest 通过 + ruff/lint 全绿
- [ ] `.sync/vector.db` 不进 git（gitignore 已覆盖 `.sync/`）

---

**下一步**：确认本方案后按 TDD 从步骤 1 开始落地。若你认为上千卡即需 FAISS 或要走 bge-m3，先对齐再动工。