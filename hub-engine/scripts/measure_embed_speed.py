# @version V1.0 / 2026-09-14 / Hermes / 测量各 embedding 模型实际响应时间（bge-small-zh / bge-m3 / nomic）
import json
import time

import requests

models = [
    "text-embedding-bge-small-zh-v1.5",
    "text-embedding-bge-m3",
    "text-embedding-nomic-embed-text-v1.5",
]

results = []
for m in models:
    try:
        start = time.time()
        resp = requests.post(
            "http://localhost:1234/v1/embeddings",
            json={"model": m, "input": "测试文本结构工程"},
            timeout=60,  # bge-m3 实测首次调用约 30s，15s 会误判失败
        )
        elapsed_ms = (time.time() - start) * 1000
        usage = resp.json().get("usage", {})
        results.append(
            {
                "model": m,
                "ms": round(elapsed_ms, 1),
                "status": resp.status_code,
                "usage": usage,
                "ok": True,
            }
        )
    except Exception as e:
        results.append({"model": m, "ms": 0, "ok": False, "error": str(e)})

for r in results:
    print(json.dumps(r, ensure_ascii=False))
