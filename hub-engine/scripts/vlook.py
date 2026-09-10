# @version V1.0 / 2026-09-10 / Hermes / 看板截图视觉检查工具（本地 VL 模型驱动）
"""vlook.py - 用本机视觉模型"看"截图，输出结构化描述.

为什么需要它:
  当前 chat 模型（deepseek-flash）非多模态，vision_analyze 不可用。
  但本机 LM Studio(1234) 有 paddleocr-vl-1.6，OmniRoute(20128) 有 auto/vision。
  本工具把截图喂给本地 VL 模型，得到真实的"看到什么"描述。

用法:
  python vlook.py <图片路径> [--prompt "自定义问题"] [--backend lmstudio|omniroute]
"""

import argparse
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.request

BACKENDS = {
    "lmstudio": ("http://127.0.0.1:1234/v1/chat/completions", "paddleocr-vl-1.6"),
    "omniroute": ("http://127.0.0.1:20128/v1/chat/completions", "auto/vision"),
}

DEFAULT_PROMPT = (
    "这是一个深色主题的 Web 看板截图。请用中文客观描述你看到的内容：\n"
    "1) 整体布局（侧边栏/主区/卡片网格）\n"
    "2) 所有可见的标题与关键数字（逐条列出）\n"
    "3) 中文是否正常显示、有无乱码/方块/缺字\n"
    "4) 视觉问题（卡片大小失衡、留白过多、文字过小、对齐错位、颜色矛盾）\n"
    "只描述你真实看到的，不要推测。"
)


def encode_image(path: pathlib.Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def ask(image_path: pathlib.Path, prompt: str, backend: str, timeout: int = 180) -> str:
    url, model = BACKENDS[backend]
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + encode_image(image_path)
                        },
                    },
                ],
            }
        ],
        "max_tokens": 1600,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--backend", default="lmstudio", choices=list(BACKENDS))
    a = ap.parse_args()

    p = pathlib.Path(a.image)
    if not p.exists():
        print(f"[ERR] 图片不存在: {p}")
        return 2

    print(
        f"[vlook] {p.name} ({p.stat().st_size // 1024}KB) -> {a.backend}/{BACKENDS[a.backend][1]}"
    )
    print("=" * 70)
    try:
        print(ask(p, a.prompt, a.backend))
    except urllib.error.URLError as e:
        print(f"[ERR] 后端不可达: {e}")
        return 1
    except Exception as e:
        print(f"[ERR] {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
