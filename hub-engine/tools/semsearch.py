"""向量语义检索层（方案 A：bge-small-zh + SQLite JSON 向量）。

- 持久化：中枢根 `.sync/vector.db`，表 `docs`（path / mtime / size / title / tags / type / body / embedding）
- 增量：按 (mtime, size) 签名复用已有向量，仅新/变更卡重新 embedding
- 退化：embed 后端（transformers）不可用时返回 None，检索方回退词袋，不报错
- 可插拔：`AGENT_MD_EMBED_MODEL` 环境变量换模型（默认 BAAI/bge-small-zh-v1.5）

依赖标准库 sqlite3；transformers/torch 为可选运行时（仅 embedding 需要）。
"""

import json
import os
import sqlite3
import threading
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
    """文本 → 512 维 L2 归一化向量（CLS）；后端不可用返回 None（退化）"""
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
            embedding TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_path ON docs(path)")


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


def build(root: Path) -> dict:
    """扫描卡片增量写入向量库；返回统计（reused/inserted/updated/removed/embedded）。"""
    db = db_path(root)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        _ensure_schema(conn)
        existing = {
            r[1]: (r[0], r[2], r[3])
            for r in conn.execute("SELECT id, path, mtime, size FROM docs")
        }
        stats = {"reused": 0, "inserted": 0, "updated": 0, "removed": 0, "embedded": 0}
        current: set[str] = set()

        for card in _scan_cards(root):
            full = str(card.path)
            current.add(full)
            sig = _sig(card.path)
            old = existing.get(full)
            text = f"{card.body} {' '.join(card.tags)}"
            # 签名未变 → 复用已有行（含向量），跳过 embedding
            if old is not None and sig is not None and (old[1], old[2]) == sig:
                stats["reused"] += 1
                continue

            try:
                vec = embed(text)  # type: ignore[misc]
            except Exception:  # noqa: BLE001 - embed 后端异常则存空向量，不中断构建
                vec = None
            emb_str = json.dumps(vec, ensure_ascii=False) if vec else None
            if emb_str:
                stats["embedded"] += 1

            if old is not None:
                conn.execute("DELETE FROM docs WHERE id=?", (old[0],))
                stats["updated"] += 1
            else:
                stats["inserted"] += 1

            conn.execute(
                """INSERT INTO docs(path, mtime, size, title, tags, type, body, embedding)
                VALUES(?,?,?,?,?,?,?,?)""",
                (
                    full,
                    sig[0] if sig else 0.0,
                    sig[1] if sig else 0,
                    card.path.name,
                    ",".join(card.tags),
                    card.type,
                    card.body,
                    emb_str,
                ),
            )

        # 清理孤儿：源卡已删除
        for path_, (pid, _, _) in existing.items():
            if path_ not in current:
                conn.execute("DELETE FROM docs WHERE id=?", (pid,))
                stats["removed"] += 1

        conn.commit()
        return stats
    finally:
        conn.close()


def vector_scores(
    root: Path, query_vec: list[float], top_k: int = 5
) -> list[tuple[str, float]]:
    """query 向量与库内每卡向量点积（余弦，均为 L2 归一化）→ [(path, score)] 降序。

    库不存在或空 → 返回 []。
    """
    db = db_path(root)
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT path, embedding FROM docs WHERE embedding IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return []
    scored = []
    for path_, emb_str in rows:
        try:
            vec = json.loads(emb_str)
        except (json.JSONDecodeError, TypeError):
            continue
        scored.append((path_, _dot(query_vec, vec)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
