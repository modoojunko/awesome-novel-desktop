"""知识树同步（s-kb-signed-delivery）：C 端不打包 taxonomy，树只从 S 端签名 URL 获取。

- 缓存：``{DATA_ROOT}/kb-tree/``——``receipt.json``＋``v{N}/taxonomy.json``（原始字节）＋
  ``v{N}/meta.json``（签名指针副本）＋``highwatermark``（防回退）。
- 分发：S 端 `/api/kb/sign` 签 COS 私有桶短时 URL（`tree/latest.json` 与
  `tree/v{N}/taxonomy.json`）；**知识树免费**，不占题材次数，登录即可自动同步/更新。
- 信任模型：latest 指针 Ed25519 验签（legacy 三字段格式——与 manifest_crypto 的
  canonical 不同）＋下载体 sha256/size＋结构校验（单根/父可解析/slot_map 指向存在/无环）
  ＋出站守卫（COS 桶域白名单）。
- 版本：只认 S 端指针 version；同版本缓存完整＝current；同版本损坏＝修复重下；
  低版本一律拒绝（回退保护）。
- 树未就绪（无缓存/结构空）：``kb.taxonomy`` 返回空树，总结/提炼明确拒绝。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path

from kb import server_api

logger = logging.getLogger(__name__)

TREE_DIR_NAME = "kb-tree"
RECEIPT_NAME = "receipt.json"
HIGHWATERMARK_NAME = "highwatermark"
STAGING_PREFIX = ".staging-"
META_NAME = "meta.json"
TREE_FILE_NAME = "taxonomy.json"

# tree_publish.py 的签名域（legacy v1 格式，逐字对齐——改格式要两仓同批）
TREE_SIG_FIELDS = ("version", "taxonomy_sha256", "size")

_MAX_TREE_BYTES = 8 * 1024 * 1024

_TRUST_PUBKEYS: dict[str, bytes] = {}
_PROD_PUBKEYS_JSON = '{"pack-k1":"UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM="}'

_syncing = False
_sync_task = None


def tree_root() -> Path:
    return Path(os.environ.get("DATA_ROOT", "./data")) / TREE_DIR_NAME


def receipt_path() -> Path:
    return tree_root() / RECEIPT_NAME


def highwatermark_path() -> Path:
    return tree_root() / HIGHWATERMARK_NAME


def version_dir(version: int) -> Path:
    return tree_root() / f"v{version}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_receipt() -> dict | None:
    try:
        data = json.loads(receipt_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") else None


def write_receipt(data: dict) -> None:
    _atomic_write_text(receipt_path(), json.dumps(data, ensure_ascii=False, indent=1))


def read_highwatermark() -> int:
    try:
        return int(highwatermark_path().read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def write_highwatermark(version: int) -> None:
    try:
        _atomic_write_text(highwatermark_path(), str(int(version)))
    except OSError as exc:  # noqa: BLE001 — 记账失败不影响安装
        logger.warning("event=kb_tree_highwatermark_write_failed err=%s", exc)


def _cached_file_ok(version: int, expected_sha: str = "") -> Path | None:
    path = version_dir(version) / TREE_FILE_NAME
    if not path.is_file():
        return None
    if not expected_sha:
        return path
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    return path if digest == expected_sha else None


def cached_tree_path() -> str | None:
    receipt = read_receipt()
    if receipt:
        version = int(receipt.get("version") or 0)
        sha = str(receipt.get("taxonomy_sha256") or "")
        if version > 0:
            path = _cached_file_ok(version, sha) or _cached_file_ok(version)
            if path is not None:
                return str(path)
    root = tree_root()
    if not root.is_dir():
        return None
    candidates: list[tuple[int, Path]] = []
    for child in root.glob("v*"):
        try:
            version = int(child.name[1:])
        except ValueError:
            continue
        meta = child / META_NAME
        sha = ""
        if meta.is_file():
            try:
                sha = str(
                    json.loads(meta.read_text(encoding="utf-8")).get("taxonomy_sha256")
                    or ""
                )
            except (OSError, ValueError):
                sha = ""
        path = _cached_file_ok(version, sha) or _cached_file_ok(version)
        if path is not None:
            candidates.append((version, path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return str(candidates[0][1])


def _trust_keys() -> dict[str, bytes]:
    if _TRUST_PUBKEYS:
        return _TRUST_PUBKEYS
    for name in ("CLIENT_TREE_PUBKEYS", "CLIENT_KB_PUBKEYS", "CLIENT_PACK_PUBKEYS"):
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            keys = {str(k): base64.b64decode(str(v)) for k, v in parsed.items()}
        except (ValueError, TypeError, AttributeError):
            continue
        if keys and all(len(v) == 32 for v in keys.values()):
            return keys
    try:
        parsed = json.loads(_PROD_PUBKEYS_JSON)
        return {str(k): base64.b64decode(str(v)) for k, v in parsed.items()}
    except (ValueError, TypeError):
        return {}


def verify_tree_pointer(latest: dict, pubkeys: dict[str, bytes]) -> bool:
    signature = str(latest.get("signature") or "")
    kid = str(latest.get("signer_key_id") or "")
    key = pubkeys.get(kid)
    if not signature or key is None:
        return False
    try:
        sig = base64.b64decode(signature)
        candidates = [
            json.dumps(
                {k: latest[k] for k in TREE_SIG_FIELDS if k in latest}, sort_keys=True
            ),
            json.dumps(
                {k: latest[k] for k in TREE_SIG_FIELDS if k in latest},
                sort_keys=True,
                separators=(",", ":"),
            ),
            json.dumps(
                {k: v for k, v in latest.items() if k != "signature"},
                sort_keys=True,
                separators=(",", ":"),
            ),
        ]
    except (ValueError, TypeError, KeyError):
        return False
    for body in candidates:
        if verify_with_key(key, sig, body.encode("utf-8")):
            return True
    return False


def verify_with_key(key: bytes, sig: bytes, body: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(key).verify(sig, body)
        return True
    except (InvalidSignature, ValueError):
        return False


def validate_tree_payload(raw: bytes) -> tuple[bool, str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False, "tree_not_utf8"
    try:
        data = json.loads(text)
    except ValueError:
        return False, "tree_bad_json"
    if not isinstance(data, dict):
        return False, "tree_not_object"
    nodes = data.get("nodes")
    slot_map = data.get("slot_map")
    if not isinstance(nodes, dict) or not nodes:
        return False, "tree_empty_nodes"
    if not isinstance(slot_map, dict):
        return False, "tree_bad_slot_map"
    for key, node in nodes.items():
        if not isinstance(node, dict):
            return False, "tree_node_not_object"
        parent = str(node.get("parent") or "")
        if parent and parent not in nodes:
            return False, "tree_parent_dangling"
    for key in nodes:
        seen = {key}
        cur = str(nodes[key].get("parent") or "")
        while cur:
            if cur in seen:
                return False, "tree_cycle"
            seen.add(cur)
            cur = str(nodes[cur].get("parent") or "")
    roots = [
        k
        for k, n in nodes.items()
        if isinstance(n, dict) and not str(n.get("parent") or "")
    ]
    if len(roots) != 1:
        return False, "tree_root_not_single"
    for key in slot_map.values():
        if str(key) not in nodes:
            return False, "tree_slot_map_dangling"
    return True, ""


def _install(version: int, raw: bytes, latest: dict) -> bool:
    root = tree_root()
    vdir = version_dir(version)
    target = vdir / TREE_FILE_NAME
    expected_sha = str(latest.get("taxonomy_sha256") or "")
    if vdir.exists():
        if target.is_file():
            existing = target.read_bytes()
            existing_sha = hashlib.sha256(existing).hexdigest()
            if existing == raw:
                pass
            elif expected_sha and existing_sha != expected_sha:
                _atomic_write_bytes(target, raw)
                _atomic_write_text(
                    vdir / META_NAME, json.dumps(latest, ensure_ascii=False, indent=1)
                )
            else:
                logger.error(
                    "event=kb_tree_immutable version=%s——同版本异内容，拒绝覆盖",
                    version,
                )
                return False
        else:
            _atomic_write_bytes(target, raw)
            _atomic_write_text(
                vdir / META_NAME, json.dumps(latest, ensure_ascii=False, indent=1)
            )
    else:
        staging = root / f"{STAGING_PREFIX}{version}"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / TREE_FILE_NAME).write_bytes(raw)
        _atomic_write_text(
            staging / META_NAME, json.dumps(latest, ensure_ascii=False, indent=1)
        )
        os.rename(staging, vdir)
    write_receipt(
        {
            "version": version,
            "taxonomy_sha256": str(latest.get("taxonomy_sha256") or ""),
            "size": int(latest.get("size") or 0),
            "signer_key_id": str(latest.get("signer_key_id") or ""),
            "installed_at": latest.get("generated_at") or "",
        }
    )
    write_highwatermark(version)
    _cleanup_old_versions(version)
    return True


def _cleanup_old_versions(current: int) -> None:
    root = tree_root()
    if not root.is_dir():
        return
    keep = {f"v{current}", f"v{current - 1}"}
    for child in root.glob("v*"):
        try:
            if int(child.name[1:]) >= current - 1:
                continue
        except ValueError:
            continue
        if child.name in keep:
            continue
        import shutil

        try:
            shutil.rmtree(child, ignore_errors=True)
        except OSError as exc:  # noqa: BLE001
            logger.warning("event=kb_tree_cleanup_failed dir=%s err=%s", child.name, exc)


def _reason_from_code(code: object) -> str:
    try:
        value = int(code)
    except (TypeError, ValueError):
        value = -1
    return {
        401: "not_logged_in",
        -2: "not_logged_in",
        -1: "s_unreachable",
    }.get(value, "s_unreachable")


async def _load_pointer() -> dict:
    """sign tree_pointer → 下载/验签；返回 {ok, reason, latest, version, sha, size}。"""
    keys = _trust_keys()
    if not keys:
        return {"ok": False, "reason": "not_configured"}
    resp = await server_api.sign("tree_pointer")
    code = resp.get("code", -1)
    if int(code) != 0:
        return {"ok": False, "reason": _reason_from_code(code)}
    data = resp.get("data") or {}
    raw, verdict = await server_api.fetch_signed(str(data.get("url") or ""), _MAX_TREE_BYTES)
    if raw is None:
        return {
            "ok": False,
            "reason": "proxy_fake_ip" if verdict == "fakeip" else "pointer_fetch",
        }
    try:
        latest = json.loads(raw)
    except ValueError:
        latest = None
    if not isinstance(latest, dict) or not verify_tree_pointer(latest, keys):
        return {"ok": False, "reason": "pointer_invalid"}
    try:
        version = int(latest.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    sha = str(latest.get("taxonomy_sha256") or "")
    size = latest.get("size")
    if version <= 0 or len(sha) != 64 or not isinstance(size, int):
        return {"ok": False, "reason": "latest_fields_invalid"}
    return {
        "ok": True,
        "latest": latest,
        "version": version,
        "sha": sha,
        "size": size,
    }


async def sync_tree() -> dict:
    """同步一次树；永不抛异常、永不覆盖好缓存。树免费（S 端不扣题材次数）。"""
    global _syncing
    if _syncing:
        return {"status": "skipped", "reason": "syncing"}
    _syncing = True
    try:
        return await _sync_inner()
    except Exception as exc:  # noqa: BLE001 — 同步失败不阻断任何调用方
        logger.warning("event=kb_tree_sync_failed", exc_info=True)
        return {"status": "failed", "reason": f"exception: {exc}"}
    finally:
        _syncing = False


async def _sync_inner() -> dict:
    rel = await _load_pointer()
    if not rel["ok"]:
        status = (
            "skipped"
            if rel["reason"] in ("not_logged_in", "not_configured")
            else "failed"
        )
        return {"status": status, "reason": rel["reason"]}

    version = rel["version"]
    sha = rel["sha"]
    size = rel["size"]
    latest = rel["latest"]
    receipt = read_receipt()
    receipt_version = int(receipt.get("version") or 0) if receipt else 0
    if receipt_version and version < receipt_version:
        return {
            "status": "skipped",
            "reason": "older_than_installed",
            "installed": receipt_version,
            "latest": version,
        }
    if receipt_version == version and _cached_file_ok(version, sha) is not None:
        return {"status": "current", "version": version}

    resp = await server_api.sign("tree_data", version=version)
    code = resp.get("code", -1)
    if int(code) != 0:
        status = "skipped" if int(code) in (401, -2) else "failed"
        return {"status": status, "reason": _reason_from_code(code)}
    data = resp.get("data") or {}
    raw, verdict = await server_api.fetch_signed(str(data.get("url") or ""), _MAX_TREE_BYTES)
    if raw is None:
        reason = "proxy_fake_ip" if verdict == "fakeip" else "tree_fetch"
        return {"status": "failed", "reason": reason}
    if len(raw) != size:
        return {"status": "failed", "reason": "tree_size", "size": len(raw)}
    if hashlib.sha256(raw).hexdigest() != sha:
        return {"status": "failed", "reason": "tree_hash"}
    ok, reason = validate_tree_payload(raw)
    if not ok:
        return {"status": "failed", "reason": reason}
    if not _install(version, raw, latest):
        return {"status": "failed", "reason": "install"}

    _reload_taxonomy()
    logger.info("event=kb_tree_sync version=%s size=%d", version, len(raw))
    return {"status": "synced", "version": version, "size": len(raw)}


async def probe_latest() -> dict:
    """只探不装：{installed, latest, update_available, reason}。"""
    installed = int((read_receipt() or {}).get("version") or 0)
    rel = await _load_pointer()
    if not rel["ok"]:
        return {
            "installed": installed,
            "latest": 0,
            "update_available": False,
            "reason": rel["reason"],
        }
    version = rel["version"]
    return {
        "installed": installed,
        "latest": version,
        "update_available": bool(version and version != installed),
        "reason": "",
    }


def maybe_sync() -> None:
    """登录钩子：免费；有新版才拉。`KB_TREE_SYNC=0` 与启动钩同闸。"""
    import asyncio

    if (os.environ.get("KB_TREE_SYNC") or "").strip() == "0":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_maybe_sync_task())


async def _maybe_sync_task() -> None:
    try:
        probe = await probe_latest()
    except Exception:  # noqa: BLE001
        return
    if probe.get("update_available"):
        result = await sync_tree()
        logger.info("event=kb_tree_sync %s", json.dumps(result, ensure_ascii=False))


def _reload_taxonomy() -> None:
    from kb.taxonomy import reload

    reload()


def schedule_sync() -> None:
    """启动补偿：KB_TREE_SYNC=0 关（测试/诊断）；树免费，可自动同步。"""
    import asyncio

    global _sync_task
    if (os.environ.get("KB_TREE_SYNC") or "").strip() == "0":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _sync_task = loop.create_task(_sync_with_logging())


async def _sync_with_logging() -> None:
    result = await sync_tree()
    if result.get("status") in ("synced", "failed"):
        logger.info("event=kb_tree_sync %s", json.dumps(result, ensure_ascii=False))


def tree_state() -> dict:
    path = cached_tree_path()
    receipt = read_receipt() or {}
    return {
        "ready": bool(path),
        "version": int(receipt.get("version") or 0),
        "taxonomy_sha256": str(receipt.get("taxonomy_sha256") or ""),
        "path": path or "",
    }


__all__ = [
    "cached_tree_path",
    "maybe_sync",
    "probe_latest",
    "read_receipt",
    "schedule_sync",
    "sync_tree",
    "tree_root",
    "tree_state",
    "validate_tree_payload",
    "verify_tree_pointer",
]
