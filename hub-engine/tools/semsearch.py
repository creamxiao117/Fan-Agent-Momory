"""向量语义检索层（方案 A：bge-small-zh + SQLite 二进制向量列）。

- 持久化：中枢根 `.sync/vector.db`，表 `docs`（path / mtime / size / title / tags / type / body / embedding）
- 向量编码：`embedding` 存 numpy float32 `.tobytes()` 二进制（读时 `.frombuffer`），
  替代旧 JSON 文本——免每次全表 json.loads 反序列化，显著降低检索耗时。
- 兼容：旧数据若为 JSON 文本（历史行）读侧自动识别回退解析，构建时统一落二进制。
- 增量：按 (mtime, size) 签名复用已有向量，仅新/变更卡重新 embedding
- 退化：embed 后端（transformers）不可用时返回 None，检索方回退词袋，不报错
- 可插拔：`AGENT_MD_EMBED_MODEL` 环境变量换模型（默认 BAAI/bge-small-zh-v1.5）

依赖标准库 sqlite3 + numpy；transformers/torch 为可选运行时（仅 embedding 需要）。
"""

import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

EMBED_MODEL = os.environ.get("AGENT_MD_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
_LOCK = threading.Lock()
_model = None
_tok = None

# 可注入的 embed 实现（测试用 monkeypatch 替换；生产为 _embed_text）
embed: Callable[[str], list[float] | None] = (
    None  # 类型标注，实际赋值见 set_embed_backend
)


# ---- HTTP embed 后端（OpenAI 兼容 /v1/embeddings，本机为 LM Studio + bge-m3）----
# 为什么需要：本机无任何解释器装齐 transformers+torch，本地模型后端实际跑不起来；
# 且库内现存 188 条向量为 bge-m3 的 1024 维，HTTP 端必须产出同维度模型，否则检索失效。
_HTTP_CFG: tuple[str, str, str, int] | None = None
_HTTP_PROBED = False


def _http_cfg() -> tuple[str, str, str, int] | None:
    """懒加载 engine.config.yaml 的 embed 段；无配置返回 None（只读一次）。"""
    global _HTTP_CFG, _HTTP_PROBED
    if _HTTP_PROBED:
        return _HTTP_CFG
    _HTTP_PROBED = True
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "engine.config.yaml"
    try:
        import yaml

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        emb = raw.get("embed") or {}
        if emb.get("url") and emb.get("model"):
            _HTTP_CFG = (
                emb["url"],
                emb["model"],
                emb.get("api_key") or "",
                int(emb.get("timeout", 30)),
            )
    except Exception:  # noqa: BLE001 - 配置缺失/损坏 → 交本地兜底
        _HTTP_CFG = None
    return _HTTP_CFG


def _embed_via_http(text: str) -> list[float] | None:
    """调 /v1/embeddings 取向量并 L2 归一化；失败返回 None（不抛错）。"""
    cfg = _http_cfg()
    if not cfg:
        return None
    url, model, api_key, timeout = cfg
    try:
        import json
        import urllib.request

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps({"model": model, "input": text}).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        import numpy as np

        v = np.asarray(payload["data"][0]["embedding"], dtype="float32")
        norm = float(np.linalg.norm(v))
        return (v / norm).tolist() if norm else None  # L2 → 点积=余弦
    except Exception:  # noqa: BLE001 - HTTP 后端不可用 → 交本地兜底
        return None


def _load_backend():
    """惰性加载模型（进程单例）；失败返回 None,None（不抛错,检索退化）"""
    global _model, _tok
    _LOCK.acquire()
    try:
        if _model is not None:
            return _model, _tok
        from transformers import AutoModel, AutoTokenizer

        _tok = AutoTokenizer.from_pretrained(EMBED_MODEL)
        _model = AutoModel.from_pretrained(EMBED_MODEL)
        return _model, _tok
    except Exception:  # noqa: BLE001 - 后端不可用则退化，绝不中断
        return None, None
    finally:
        _LOCK.release()


def _embed_text(text: str) -> list[float] | None:
    """文本 → L2 归一化向量；HTTP 后端优先，本地 transformers 兜底，均不可用返回 None。

    维度取决于后端：HTTP bge-m3=1024（与库内现存向量一致）/ 本地 bge-small-zh=512。
    """
    vec = _embed_via_http(text)
    if vec is not None:
        return vec
    model, tok = _load_backend()
    if model is None:
        return None
    try:
        import torch

        inp = tok(
            text, return_tensors="pt", padding=True, truncation=True, max_length=512
        )
        with torch.no_grad():
            out = model(**inp)
        v = out.last_hidden_state[:, 0].float()  # CLS
        v = torch.nn.functional.normalize(v, dim=-1)  # L2 归一化 → 点积=余弦
        return v[0].numpy().tolist()
    except Exception:  # noqa: BLE001 - 推理异常则退化，绝不中断
        return None


def set_embed_backend(fn: Callable[[str], list[float] | None] | None) -> None:
    """注入 embed 实现。fn=None 恢复默认（真实模型后端）。
    测试中用 monkeypatch 替换为本子（不依赖模型/网络）。"""
    global embed
    embed = fn if fn is not None else _embed_text


# 默认使用真实后端
set_embed_backend(_embed_text)

# ---- 查询侧 embedding LRU 缓存（建议 1：相似/模板查询免重复模型推理）----
# 仅缓存「查询」文本，不缓存 build 的批量卡片文本——避免全库卡片填满热点缓存。
# 退化态（embed 返回 None）不缓存，后端恢复后即自动命中，不残留脏结果。
_QUERY_CACHE_LIMIT = 128
_query_cache: dict[str, list[float]] = {}


def query_embedded(query: str) -> list[float] | None:
    """query → 向量，带 LRU 缓存（热点模板查询如 MCP hub_bootstrap 免重复推理）。

    命中/写入均在 _LOCK 保护下；LRU 超限淘汰最早插入项（dict 迭代序即插入序）。
    """
    if not query:
        return None
    with _LOCK:
        cached = _query_cache.pop(query, None)  # 命中即移除，随后重插以刷新「最近使用」
        if cached is not None:
            _query_cache[query] = cached  # 刷到队尾
            return cached
    vec = embed(query)  # type: ignore[misc]
    if vec is None:
        return None
    with _LOCK:
        _query_cache.pop(query, None)
        _query_cache[query] = vec
        if len(_query_cache) > _QUERY_CACHE_LIMIT:
            _query_cache.pop(next(iter(_query_cache)))  # 淘汰最老（队首）
    return vec


def clear_query_cache() -> None:
    """清空查询缓存（仅供测试/主动刷新热点）"""
    with _LOCK:
        _query_cache.clear()


def db_path(root: Path) -> Path:
    return Path(root) / ".sync" / "vector.db"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS docs(
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            mtime REAL,
            size INTEGER,
            title TEXT,
            tags TEXT,
            type TEXT,
            body TEXT,
            embedding BLOB,
            synced_at REAL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_path ON docs(path)")
    # 兼容旧库：无 synced_at 列时补齐（freshness 变更追踪用，OpenViking 路径 A）。
    cols = {r[1] for r in conn.execute("PRAGMA table_info(docs)").fetchall()}
    if "synced_at" not in cols:
        conn.execute("ALTER TABLE docs ADD COLUMN synced_at REAL")
    # 向量库元数据：记录模型名与向量维度，用于维度一致性门禁（借鉴
    # codebase-memory-mcp artifact 的 schema_version 门禁，防换模型后新旧向量维度混算）。
    conn.execute(
        """CREATE TABLE IF NOT EXISTS db_meta(
            key TEXT PRIMARY KEY,
            value TEXT
        )"""
    )


def _sig(full: Path) -> tuple[float, int] | None:
    try:
        st = full.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def _scan_cards(root: Path):
    """按 _ACTIVE_DIRS 遍历 active 卡（与 retrieve._index 同源目录）"""
    from tools.retrieve import _index  # 复用已缓存的进程内索引（含 mtime 失效）

    return _index(root).cards


_META_DIM = "embed_dim"
_META_MODEL = "embed_model"


def _stored_dim(conn: sqlite3.Connection) -> int | None:
    """从 db_meta 读已存向量维度；无 meta（含旧库无 db_meta 表）则从现有一行向量探测。"""
    try:
        row = conn.execute(
            "SELECT value FROM db_meta WHERE key=?", (_META_DIM,)
        ).fetchone()
    except sqlite3.OperationalError:
        row = None  # 旧库尚无 db_meta 表
    if row and row[0]:
        try:
            return int(row[0])
        except ValueError:
            return None
    hit = conn.execute(
        "SELECT embedding FROM docs WHERE embedding IS NOT NULL LIMIT 1"
    ).fetchone()
    if hit is None or hit[0] is None:
        return None
    import numpy as np

    try:
        return int(np.frombuffer(hit[0], dtype=np.float32).size)
    except Exception:  # noqa: BLE001
        return None


def _active_model_id() -> str:
    """实际生效的 embed 模型标识：HTTP 后端优先记 `http:<模型名>`，否则记本地模型名。

    为什么不能固定写 EMBED_MODEL：db_meta.embed_model 是维度门禁的判断依据，
    记错会让"换了后端但维度恰好相同"的情况漏判重建，导致不同模型向量混算。
    """
    cfg = _http_cfg()
    if cfg and _embed_via_http("model-id-probe") is not None:
        return f"http:{cfg[1]}"
    return EMBED_MODEL


def _probe_min_dim(conn: sqlite3.Connection) -> int | None:
    """返回库内现有非空向量的最小维度（跨行不一致时取最小以保守校验）。"""
    import numpy as np

    sizes = set()
    for (blob,) in conn.execute(
        "SELECT embedding FROM docs WHERE embedding IS NOT NULL"
    ).fetchall():
        try:
            sizes.add(int(np.frombuffer(blob, dtype=np.float32).size))
        except Exception:  # noqa: BLE001, S112 - 单行损坏则跳过该行，维度以其余行为准
            continue
    return min(sizes) if sizes else None


def _backend_ok() -> bool:
    """判断当前 embed 后端是否可用。

    区分注入 mock 与真实后端：测试经 set_embed_backend 注入回调时视为可能产向量，
    不属模型门禁管辖；生产（embed 是 _embed_text）则依次探测 HTTP 后端、本地模型。

    为什么 HTTP 也要实测一次：配置存在 ≠ 服务在跑（LM Studio 未启动时配置仍在），
    只判配置会让 build 在后端真挂时误判可用、落 NULL 污染库。
    """
    if embed is not _embed_text:
        return True
    if _http_cfg() and _embed_via_http("backend-probe") is not None:
        return True
    return _load_backend()[0] is not None


def build(root: Path) -> dict:
    """扫描卡片增量写入向量库；返回统计（reused/inserted/updated/removed/embedded）。

    维度门禁：记录 embed_dim/embed_model 到 db_meta；若本次 build 实得向量维度与库内
    已存维度不一致（换模型/维度变化），视为旧库失效，清空 docs 全量重建，避免新旧
    维度向量混算产生静默错误分（借鉴 codebase-memory-mcp artifact schema_version 门禁）。

    后端保护：embed 后端不可用且库内已有有效向量时，保留旧库（degraded），绝不落 NULL 污染。
    """
    db = db_path(root)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        _ensure_schema(conn)
        # ---- 后端保护：后端不可用且库内已有有效向量时，保留旧库，绝不落 NULL 污染 ----
        if not _backend_ok():
            n_valid = conn.execute(
                "SELECT COUNT(*) FROM docs WHERE embedding IS NOT NULL"
            ).fetchone()[0]
            if n_valid > 0:
                return {
                    "reused": 0, "inserted": 0, "updated": 0, "removed": 0,
                    "embedded": 0, "degraded": True,
                    "note": f"embed 后端不可用，保留 {n_valid} 条有效向量，未覆盖",
                }
        # 探测库内已存维度；若模型名变了且维度不同 → 全量重建
        stored_model = conn.execute(
            "SELECT value FROM db_meta WHERE key=?", (_META_MODEL,)
        ).fetchone()
        active_model = _active_model_id()  # 实际生效后端（HTTP 优先）：供比较与落库
        rebuild = False
        if stored_model and stored_model[0] != active_model:
            stored_dim = _stored_dim(conn)
            if stored_dim is not None and _probe_min_dim(conn) in (None, stored_dim):
                rebuild = True
        if rebuild:
            conn.execute("DELETE FROM docs")
        existing = {
            r[1]: (r[0], r[2], r[3], r[4])
            for r in conn.execute(
                "SELECT id, path, mtime, size, synced_at FROM docs"
            )
        }
        stats = {"reused": 0, "inserted": 0, "updated": 0, "removed": 0, "embedded": 0}
        current: set[str] = set()
        now = time.time()

        for card in _scan_cards(root):
            full = str(card.path)
            current.add(full)
            sig = _sig(card.path)
            old = existing.get(full)
            text = f"{card.body} {' '.join(card.tags)}"
            # 签名未变 → 复用已有行（含向量），仅刷新同步时间（freshness 变更追踪）
            if old is not None and sig is not None and (old[1], old[2]) == sig:
                conn.execute(
                    "UPDATE docs SET synced_at=? WHERE id=?", (now, old[0])
                )
                stats["reused"] += 1
                continue

            try:
                vec = embed(text)  # type: ignore[misc]
            except Exception:  # noqa: BLE001 - embed 后端异常则存空向量，不中断构建
                vec = None
            emb = _encode_vec(vec)  # 二进制 float32；None 表示无向量（退化）
            if emb:
                stats["embedded"] += 1

            if old is not None:
                conn.execute("DELETE FROM docs WHERE id=?", (old[0],))
                stats["updated"] += 1
            else:
                stats["inserted"] += 1

            conn.execute(
                """INSERT INTO docs(path, mtime, size, title, tags, type, body, embedding, synced_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    full,
                    sig[0] if sig else 0.0,
                    sig[1] if sig else 0,
                    card.path.name,
                    ",".join(card.tags),
                    card.type,
                    card.body,
                    emb,  # bytes(二进制) 或 None
                    now,
                ),
            )

        # 清理孤儿：源卡已删除
        for path_, (pid, _, _, _) in existing.items():
            if path_ not in current:
                conn.execute("DELETE FROM docs WHERE id=?", (pid,))
                stats["removed"] += 1

        # 写入向量库元数据（维度门禁）：记录本次实得维度 + 模型名
        min_dim = _probe_min_dim(conn)
        conn.execute(
            "INSERT OR REPLACE INTO db_meta(key, value) VALUES(?,?)",
            (_META_DIM, str(min_dim)),
        ) if min_dim is not None else None
        conn.execute(
            "INSERT OR REPLACE INTO db_meta(key, value) VALUES(?,?)",
            (_META_MODEL, active_model),
        )

        conn.commit()
        return stats
    finally:
        conn.close()


def scan_stale(root: Path) -> dict:
    """freshness 变更追踪：检出「内容已变但向量未同步」的待重建卡（OpenViking pending_child_changes）。

    判据：卡文件 mtime 新于向量库该行 synced_at → 说明卡片在最近一次 build-vectors 之后
    又改动过（或从未被向量化），检索仍会命中旧向量。按 type 目录聚合返回，纯只读软汇报，
    不提交、不改库、不算告警（嵌入向量通道退化时也如实暴露，供巡检提示补跑 build-vectors）。

    返回 {"stale_by_dir": {dir: count}, "total": n, "path_examples": [..]}。
    """
    db = db_path(root)
    stale_by_dir: dict[str, int] = {}
    examples: list[str] = []
    synced: dict[str, float] = {}
    have_db = db.exists()
    if have_db:
        conn = sqlite3.connect(db)
        try:
            _ensure_schema(conn)  # 旧库无 synced_at 列时幂等补齐（真机读侧安全）
            synced = {
                str(r[0]): r[1] or 0.0
                for r in conn.execute(
                    "SELECT path, synced_at FROM docs WHERE embedding IS NOT NULL"
                ).fetchall()
            }
        finally:
            conn.close()
    for card in _scan_cards(root):
        sig = _sig(card.path)
        if sig is None:
            continue
        mtime = sig[0]
        row = synced.get(str(card.path))
        if row is None or mtime > row:
            sub = getattr(card, "type", "unknown") or "unknown"
            stale_by_dir[sub] = stale_by_dir.get(sub, 0) + 1
            if len(examples) < 3:
                examples.append(str(card.path))
    total = sum(stale_by_dir.values())
    return {"stale_by_dir": stale_by_dir, "total": total, "path_examples": examples}


def vector_scores(
    root: Path, query_vec: list[float], top_k: int = 5
) -> list[tuple[str, float]]:
    """query 向量与库内每卡向量点积（余弦，均为 L2 归一化）→ [(path, score)] 降序。

    库不存在或空 → 返回 []。
    维度门禁：query 维度与库内向量维度不一致（换模型/旧库失效）→ 返回 []，
    由上游融合回退词袋，避免静默错分（借鉴 codebase-memory-mcp artifact schema_version 门禁）。
    """
    db = db_path(root)
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    try:
        stored_dim = _stored_dim(conn)
        if stored_dim is not None and len(query_vec) != stored_dim:
            return []
        rows = conn.execute(
            "SELECT path, embedding FROM docs WHERE embedding IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return []
    scored = []
    for path_, blob in rows:
        vec = _decode_vec(blob)
        if vec is None:
            continue
        scored.append((path_, _dot(query_vec, vec)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ---- 向量二进制编码：float32 .tobytes() 替代 JSON 文本，免每次全表反序列化 ----
def _encode_vec(vec: list[float] | None) -> bytes | None:
    """list[float] → float32 二进制 bytes；非向量返回 None。"""
    if not vec:
        return None
    import numpy as np

    try:
        return np.asarray(vec, dtype=np.float32).tobytes()
    except Exception:  # noqa: BLE001 - 编码异常视为退化，不强转 float32
        return None


def _decode_vec(blob: object) -> list[float] | None:
    """embedding 列 → list[float]。兼容旧 JSON 文本行与新二进制（float32）行。"""
    if blob is None:
        return None
    if isinstance(blob, bytes):
        import numpy as np

        try:
            arr = np.frombuffer(blob, dtype=np.float32)
            return arr.tolist()
        except Exception:  # noqa: BLE001 - 罕见损坏则忽略该行
            return None
    if isinstance(blob, str):  # 旧 JSON 文本行（历史数据）回退解析
        try:
            return json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            return None
    return None
