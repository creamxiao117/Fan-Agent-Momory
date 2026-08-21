"""向量预过滤 + LLM 去重决策（OpenViking 路径 B 落地）。

对齐 OpenViking 记忆提取「消息→向量预过滤找相似→LLM去重决策→写入」：
- `candidates`：向量预过滤，返回语义相似候选（按 cosine 降序），替代纯向量硬阈值单判。
- `decide`：LLM 对「新卡 vs 候选」做去重决策，产出
  {action, target, reason, confidence}。action ∈
  skip(重复，丢弃草稿) / create(新建，与候选不同) / merge(并入指定旧卡) /
  delete(删冲突旧卡) / review(降级，交人工)。

保守边界（对齐蓝图卡「不可接受误删」伕）：本模块**只产出建议**，decide 返回
review = 降级。任何 merge/delete 的最终执行由调用方（sync.ingest）控制，
LLM 不可用时自动退为 review，绝不自动删改权威区。与 read 侧 query.log /
write 侧 memory_diff 组合可审。
"""

import json
import re
from pathlib import Path

# 决策动作白名单（其余一律视作非法 → 降级 review）
ACTIONS = {"skip", "create", "merge", "delete"}
VALID = ACTIONS | {"review"}

# 向量预过滤阈值：低于此分不视为候选（与 OpenViking "预过滤找相似" 对齐）
DEFAULT_MIN_SIM = 0.55


def candidates(
    root: Path, card, min_sim: float = DEFAULT_MIN_SIM, top_k: int = 5
) -> list[tuple]:
    """向量预过滤：返回与 card 语义相似（cosine>=min_sim）的权威区候选，按分降序。

    返回 (Card, score) 列表，至多 top_k 条。无命中返回空列表。
    """
    from common.vector import cosine, vector  # 延迟导入，避免冷启动加载
    from sync import _authority_cards  # 复用权威区卡片枚举（含单写者读路径）

    cv = vector(card.body)
    hits = []
    for c in _authority_cards(root):
        s = cosine(cv, vector(c.body))
        if s >= min_sim:
            hits.append((c, s))
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits[:top_k]


def _build_prompt(new_card, cands: list[tuple]) -> str:
    """构造去重决策提示词：给 LLM 新卡正文 + 候选卡正文，要求一律 JSON 输出"""
    lines = [
        "你是记忆库去重决策器。判断一张新记忆卡是否与下列候选卡重复。",
        "只输出一行 JSON（不要任何解释/包裹），格式：",
        '{"action":"skip|create|merge|delete","target":"<合并/删除的候选卡文件名,无则null>","reason":"<一句话理由>","confidence":0.0-1.0}',
        "",
        "定义：",
        "- skip：新卡与某候选语义重复，应丢弃新卡（target 填该候选文件名，或 null）；",
        "- create：新卡是全新内容，与候选均不重复（target=null）；",
        "- merge：新卡与候选高度同主题但互补，应并入候选（target 必填候选文件名）；",
        "- delete：候选已被新卡完全替代、无独立价值（target 必填候选文件名，**仅在确定性极高时**用）；",
        "不确定时优先 create/skip，绝不轻易 delete（误删代价高）。",
        "",
        "【新卡】",
        new_card.body.strip(),
        "",
    ]
    for i, (c, score) in enumerate(cands, 1):
        lines.append(f"【候选{i}】{c.path.name}（相似度 {score:.2f}）")
        lines.append(c.body.strip())
        lines.append("")
    return "\n".join(lines)


def parse_decision(text: str) -> dict:
    """从 LLM 输出中解析 JSON 决策；非法/非白名单动作一律降级 review。

    返回 dict：{action, target, reason, confidence, raw}。best-effort 不抛错。
    """
    out = {
        "action": "review",
        "target": None,
        "reason": "LLM 输出无法解析为合法决策",
        "confidence": 0.0,
        "raw": (text or "")[:200],
    }
    try:
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        if not m:
            return out
        obj = json.loads(m.group(0))
        action = str(obj.get("action", "")).strip().lower()
        if action not in VALID:
            out["reason"] = f"非法决策动作: {action!r}"
            return out
        out["action"] = action
        out["target"] = obj.get("target") or None
        out["reason"] = str(obj.get("reason", "")).strip() or "（无理由）"
        try:
            out["confidence"] = max(
                0.0, min(1.0, float(obj.get("confidence", 0.0)))
            )
        except (TypeError, ValueError):
            out["confidence"] = 0.0
        return out
    except Exception:  # noqa: BLE001 - 兜底：任何解析异常不阻塞 ingest
        return out


def decide(
    root: Path,
    new_card,
    cands: list[tuple],
    chat_fn=None,
) -> dict:
    """LLM 去重决策入口。返回 {action, target, reason, confidence}。

    - 无候选 → 直接 create（无相似物）。
    - chat_fn 缺省为 engine.chat（omniroute 网关）；请求失败/解析失败自动降级 review。
    - 永不抛错：任何异常回落到 review（交人工），不阻断同步主流程。
    """
    if not cands:
        return {
            "action": "create",
            "target": None,
            "reason": "向量预过滤无相似候选",
            "confidence": 1.0,
        }

    try:
        if chat_fn is None:
            from engine import chat  # 延迟导入，避免 scripts 冷启动

            chat_fn = chat
        text = chat_fn(_build_prompt(new_card, cands), root)
        return parse_decision(text)
    except Exception:  # noqa: BLE001 - 网关异常降级 review，绝不阻断同步
        return {
            "action": "review",
            "target": None,
            "reason": "LLM 网关不可用，降级交人工去重",
            "confidence": 0.0,
        }