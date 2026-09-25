# @version V1.0 / 2026-09-18 / Hermes / conflicts 区过期降级项 LLM 重判（本地链）
"""C 项：对 .sync/conflicts/ 中"09-15 修复前"产生的降级项（review/0.0 + 网关不可用）
用当前已修好的本地链（smart_chat → LM Studio 1234）重跑 LLM 判决。

- 只读 conflicts，不删除不搬移；判决结果写入 .sync/state/readjudicate-<date>.json
- 已有真判决（非 review/0.0）的组跳过
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
ROOT = _REPO / "AgentMemoryHub"
ENGINE = _REPO / "hub-engine"
sys.path.insert(0, str(ENGINE))

from common.frontmatter import read_card
from engine import smart_chat
from tools.dedup import candidates, decide

CONF = ROOT / ".sync" / "conflicts"
OUT = ROOT / ".sync" / "state" / "readjudicate-20260918.json"


def is_stale(dec: dict) -> bool:
    """09-15 修复前的降级形态：review + conf 0.0 + 网关兜底字样。"""
    return str(dec.get("action")) == "review" and float(dec.get("confidence") or 0.0) == 0.0


def main() -> None:
    rows, skipped = [], []
    for pj in sorted(CONF.glob("*.pred.json")):
        d = json.loads(pj.read_text(encoding="utf-8"))
        dec = d.get("decision") or {}
        name = pj.name[: -len(".pred.json")]
        if not is_stale(dec):
            skipped.append({"file": name, "action": dec.get("action"), "conf": dec.get("confidence")})
            continue
        md = CONF / f"{name}.md"
        if not md.exists():
            skipped.append({"file": name, "action": "缺 .md", "conf": None})
            continue
        card = read_card(md)
        cands = candidates(ROOT, card)
        t0 = time.time()
        new = decide(ROOT, card, cands, chat_fn=smart_chat)
        dt = round(time.time() - t0, 1)
        rows.append(
            {
                "file": name,
                "platform": d.get("platform"),
                "type": card.type,
                "cands": len(cands),
                "old": {"action": dec.get("action"), "conf": dec.get("confidence")},
                "new": new,
                "sec": dt,
            }
        )
        print(f"  {name[:52]:<54} {len(cands)}候选 → {new.get('action')}/{new.get('confidence')}  ({dt}s)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"rows": rows, "skipped": skipped}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n重判 {len(rows)} 组 / 跳过 {len(skipped)} 组 → {OUT}")


if __name__ == "__main__":
    main()
