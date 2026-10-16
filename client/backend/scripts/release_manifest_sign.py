#!/usr/bin/env python3
"""发布清单签名工具（c-silent-upgrade tasks 2.2/2.5）——CI 发布与重签作业共用。

用法：`python3 release_manifest_sign.py <manifest.json> --key-id update-k1
      --private-b64 "$PRIVATE_KEY"`（或 --private-file <path>，base64(32B raw)）
行为：读清单（无 signature 键）→ Ed25519 顶层签名（canonical 规则与客户端
manifest_crypto.verify 逐字同源）→ 原地写回（原子替换）。
私钥缺失/为空 → 退出码 3（调用方据此走「无钥降级：auto_enabled 强制 false」分支）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from manifest_crypto import sign_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", help="清单 JSON 文件路径（原地写回）")
    ap.add_argument("--key-id", default="update-k1")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--private-b64", help="私钥 base64(32B raw)")
    group.add_argument("--private-file", help="私钥文件（内容为 base64(32B raw)）")
    args = ap.parse_args(argv)

    private_b64 = args.private_b64
    if args.private_file:
        private_b64 = Path(args.private_file).read_text(encoding="utf-8").strip()
    if not private_b64:
        print("::error::私钥为空——无法签名", file=sys.stderr)
        return 3

    path = Path(args.manifest)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"::error::清单不可读/非 JSON：{exc}", file=sys.stderr)
        return 2
    if not isinstance(manifest, dict):
        print("::error::清单必须是 JSON 对象", file=sys.stderr)
        return 2

    from cryptography.exceptions import InvalidSignature

    try:
        signed = sign_manifest(manifest, private_b64, args.key_id)
    except (InvalidSignature, ValueError, TypeError, OSError) as exc:
        # 签名失败必须显式红（脚本进程码即门禁）
        print(f"::error::签名失败：{exc!r}", file=sys.stderr)
        return 2

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(signed, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    os.replace(tmp, path)
    print(f"signed: version={signed.get('version')} kid={args.key_id} "
          f"auto_enabled={signed.get('auto_enabled')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
