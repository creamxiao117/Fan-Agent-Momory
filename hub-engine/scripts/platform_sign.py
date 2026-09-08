# @version V1.0 / 2026-09-09 / Hermes / 平台身份签名工具
"""platform_sign.py - 平台身份签名/验证（任务 4 缺口 3 解决）.

V1.0 (2026-09-09): 解决双平台身份君子协定问题。
"""

import hashlib
import hmac
import os
import secrets
import sys
from pathlib import Path

DEFAULT_KEYS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "AgentMemoryHub" / "system" / "keys"
)


def get_or_create_key(platform: str, keys_dir: Path = DEFAULT_KEYS_DIR) -> bytes:
    """获取或创建平台签名 key。"""
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_path = keys_dir / f"{platform}.key"
    if key_path.exists():
        return key_path.read_bytes()
    key = secrets.token_bytes(32)
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, 0o600)
    except (OSError, AttributeError):
        pass
    return key


def sign(payload: bytes, key: bytes) -> str:
    """HMAC-SHA256 签名 payload，返回 hex。"""
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify(payload: bytes, signature: str, key: bytes) -> bool:
    return hmac.compare_digest(sign(payload, key), signature)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="平台身份签名/验证")
    ap.add_argument("action", choices=["init", "sign", "verify"], help="动作")
    ap.add_argument(
        "--platform", required=True, help="平台标识 hermes/trae/code/workbuddy"
    )
    ap.add_argument("--payload", help="签名内容（字符串）")
    ap.add_argument("--signature", help="验证时传")
    ap.add_argument("--keys-dir", help="keys 目录")
    args = ap.parse_args()

    keys_dir = Path(args.keys_dir) if args.keys_dir else DEFAULT_KEYS_DIR
    key = get_or_create_key(args.platform, keys_dir)

    if args.action == "init":
        print(f"[{args.platform}] key 已就绪: {keys_dir / f'{args.platform}.key'}")
        return 0
    if args.action == "sign":
        if not args.payload:
            print("--payload 必填", file=sys.stderr)
            return 1
        sig = sign(args.payload.encode("utf-8"), key)
        print(sig)
        return 0
    if args.action == "verify":
        if not args.payload or not args.signature:
            print("--payload 和 --signature 必填", file=sys.stderr)
            return 1
        ok = verify(args.payload.encode("utf-8"), args.signature, key)
        print("OK" if ok else "FAIL")
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
