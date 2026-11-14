"""知识树 CDN 同步（c-kb-tree-cdn）：C 端不打包 taxonomy，树只从 CDN 获取。

- 缓存：``{DATA_ROOT}/kb-tree/``——``receipt.json``（当前版本账）＋
  ``v{N}/taxonomy.json``（CDN 原始字节，绝不重新序列化）＋``v{N}/meta.json``
  （签名指针副本，目录可自验）＋``highwatermark``（防回退）。
- 信任模型：latest 指针 Ed25519 验签（内容仓 ``tree_publish.py`` 的 **legacy
  三字段格式**：``{version,taxonomy_sha256,size}``、默认 JSON 分隔符——与
  ``manifest_crypto`` 的 canonical 规则**不兼容**，本模块自带 verifier）＋
  下载体 sha256/size 校验＋结构校验（单根/父可解析/slot_map 指向存在/无环）
  ＋ https/可信域/公网 SSRF 防线（与 kb.baseline 同源；空 allowlist 直接拒）。
- 同步挂启动补偿：静默、失败可重试、不阻断启动；``KB_TREE_SYNC=0`` 关启动钩
  （手动 ``sync_tree()`` 不受影响）。树是设备级公共资产，缓存走文件不走
  AppMeta（AppMeta 随 app 版本换库，会假报版本）。
- 版本口径：只认 CDN ``version``；同版本且缓存完整＝current；同版本缓存损坏
  ＝同版本修复重下；**低版本一律拒绝**（本地比线上新＝回退保护），要回退删
  ``receipt.json`` 手工覆盖。
- 树未就绪（无缓存/结构空）：``kb.taxonomy`` 返回空树——总结/提炼据此明确
  拒绝（``tree_not_ready``），**不**回落任何内置知识。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import outbound_guard

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
_FETCH_TIMEOUT = 8.0
_DEFAULT_TREE_CDN_BASE = "https://www.awesomenovel.com/knowledge/tree"
_DEFAULT_TREE_CDN_BASE_FALLBACK = (
    "https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/knowledge/tree"
)

# {kid: 32B raw}——非空即优先（测试/联调注入）；否则 CLIENT_TREE_PUBKEYS →
# CLIENT_KB_PUBKEYS → CLIENT_PACK_PUBKEYS（**与提示词包共用 pack-k1**）→ 生产默认。
_TRUST_PUBKEYS: dict[str, bytes] = {}
_PROD_PUBKEYS_JSON = '{"pack-k1":"UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM="}'

_syncing = False
_sync_task = None  # 持引用防 GC


# ── 缓存路径（运行期读 DATA_ROOT，测试可重定向；照 prompt_pack.pack_root）──


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
    """v{N}/taxonomy.json 存在且（有 sha 期望时）哈希一致 → 返回路径。"""
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
    """当前可用缓存路径：receipt 优先（带 sha 复验），坏账回退扫 v*/meta.json。"""
    receipt = read_receipt()
    if receipt:
        version = int(receipt.get("version") or 0)
        sha = str(receipt.get("taxonomy_sha256") or "")
        if version > 0:
            path = _cached_file_ok(version, sha) or _cached_file_ok(version)
            if path is not None:
                return str(path)
    # receipt 缺/坏：找已安装版本里能自洽的（meta.json 带 sha）
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
                sha = str(json.loads(meta.read_text(encoding="utf-8")).get("taxonomy_sha256") or "")
            except (OSError, ValueError):
                sha = ""
        path = _cached_file_ok(version, sha) or _cached_file_ok(version)
        if path is not None:
            candidates.append((version, path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return str(candidates[0][1])


# ── 信任钥 / 出网防线（与 kb.baseline 同源；空 allowlist 直接拒）──────────


def _cdn_base() -> str:
    return (
        os.environ.get("KNOWLEDGE_TREE_CDN_BASE") or _DEFAULT_TREE_CDN_BASE
    ).strip().rstrip("/")


def _cdn_bases() -> list[str]:
    if (os.environ.get("KNOWLEDGE_TREE_CDN_BASE") or "").strip():
        return [_cdn_base()]
    out = [_cdn_base()]
    fb = _DEFAULT_TREE_CDN_BASE_FALLBACK.strip().rstrip("/")
    if fb and fb != out[0]:
        out.append(fb)
    return out


def _trusted_hosts() -> set[str]:
    hosts: set[str] = set()
    for base in _cdn_bases():
        host = urlparse(base).hostname
        if host:
            hosts.add(host.lower())
    return hosts


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


def _validate_outbound(url: str) -> tuple[bool, str]:
    """出站校验单源（outbound_guard）：返回 (放行, verdict)。

    https＋可信域（空 allowlist 直接拒）＋解析判定；http＋环回宿主为本地测试
    逃生口（旧语义逐字保持）。verdict ∈ ok／fakeip（TUN 代理 fake-ip DNS 全命中，
    放行）／blocked——fake-ip 环境下的获取失败由调用方记 proxy_fake_ip。
    """
    return outbound_guard.validate_outbound(
        url, _trusted_hosts(), allow_dev_loopback=True, trusted_required=True,
    )


def _derive(base: str, name: str) -> str:
    """基址即发布目录（…/knowledge/tree）：latest 与 vN/ 同级；不采信指针里任何 URL。"""
    p = urlparse(base)
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}/{name}"


async def _fetch_json(client, url: str) -> dict | None:

    try:
        r = await client.get(url, timeout=_FETCH_TIMEOUT, follow_redirects=False)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


async def _fetch_bytes(client, url: str) -> bytes | None:

    try:
        r = await client.get(url, timeout=_FETCH_TIMEOUT, follow_redirects=False)
        if r.status_code != 200 or len(r.content) > _MAX_TREE_BYTES:
            return None
        return r.content
    except Exception:  # noqa: BLE001
        return None


# ── 指针验签（legacy 三字段格式；与 manifest_crypto 的 canonical 不同）────


def verify_tree_pointer(latest: dict, pubkeys: dict[str, bytes]) -> bool:
    """tree_publish.py 的 latest 签名：对 ``{version,taxonomy_sha256,size}``
    ``json.dumps(sort_keys=True)``（默认分隔符）做 Ed25519 验签；kid 必须在
    信任集内。兼容可选的紧凑/全指针变体（未来发布器迁移时按序尝试）。"""
    signature = str(latest.get("signature") or "")
    kid = str(latest.get("signer_key_id") or "")
    key = pubkeys.get(kid)
    if not signature or key is None:
        return False
    try:
        sig = base64.b64decode(signature)
        candidates = [
            # ① 发布器现行：三字段子集、默认分隔符、不带 kid
            json.dumps({k: latest[k] for k in TREE_SIG_FIELDS if k in latest}, sort_keys=True),
            # ② 未来迁移：三字段子集、紧凑分隔符
            json.dumps(
                {k: latest[k] for k in TREE_SIG_FIELDS if k in latest},
                sort_keys=True, separators=(",", ":"),
            ),
            # ③ 未来迁移：全指针 canonical（同 manifest_crypto 口径，sha 兼作内容绑定）
            json.dumps(
                {k: v for k, v in latest.items() if k != "signature"},
                sort_keys=True, separators=(",", ":"),
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


# ── 结构校验 ─────────────────────────────────────────────────────────────


def validate_tree_payload(raw: bytes) -> tuple[bool, str]:
    """下载体结构闸：UTF-8/JSON、nodes 非空 dict、唯一根、parent 可解析、
    slot_map 指向存在、无环。返回 (ok, 稳定原因码)。"""
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
    # 环检测先于单根判定：纯环节点没有 parent=="" 的根，先报环才是真实病因
    for key in nodes:
        seen = {key}
        cur = str(nodes[key].get("parent") or "")
        while cur:
            if cur in seen:
                return False, "tree_cycle"
            seen.add(cur)
            cur = str(nodes[cur].get("parent") or "")
    roots = [k for k, n in nodes.items()
             if isinstance(n, dict) and not str(n.get("parent") or "")]
    if len(roots) != 1:
        return False, "tree_root_not_single"
    for key in slot_map.values():
        if str(key) not in nodes:
            return False, "tree_slot_map_dangling"
    return True, ""


# ── 同步主流程 ───────────────────────────────────────────────────────────


def _install(version: int, raw: bytes, latest: dict) -> bool:
    """staging → v{N} 原子 rename → receipt 最后写。

    同版本处理分三种：文件与 CDN 字节一致＝幂等；文件损坏（sha 对不上签名
    指针里的 taxonomy_sha256）＝修复补写；文件完好但与 CDN 字节不同＝版本
    不可变拒绝（内容仓 build/tree_publish 同款红线）。
    """
    root = tree_root()
    vdir = version_dir(version)
    target = vdir / TREE_FILE_NAME
    expected_sha = str(latest.get("taxonomy_sha256") or "")
    if vdir.exists():
        if target.is_file():
            existing = target.read_bytes()
            existing_sha = hashlib.sha256(existing).hexdigest()
            if existing == raw:
                pass  # 幂等重装
            elif expected_sha and existing_sha != expected_sha:
                # 缓存损坏（与签名指针声明的哈希不符）＝修复，不是覆盖好内容
                _atomic_write_bytes(target, raw)
                _atomic_write_text(
                    vdir / META_NAME, json.dumps(latest, ensure_ascii=False, indent=1))
            else:
                logger.error(
                    "event=kb_tree_immutable version=%s——同版本异内容，拒绝覆盖", version)
                return False
        else:
            # 文件缺（上次半途）：修复补写
            _atomic_write_bytes(target, raw)
            _atomic_write_text(
                vdir / META_NAME, json.dumps(latest, ensure_ascii=False, indent=1))
    else:
        staging = root / f"{STAGING_PREFIX}{version}"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / TREE_FILE_NAME).write_bytes(raw)
        _atomic_write_text(
            staging / META_NAME, json.dumps(latest, ensure_ascii=False, indent=1))
        os.rename(staging, vdir)
    write_receipt({
        "version": version,
        "taxonomy_sha256": str(latest.get("taxonomy_sha256") or ""),
        "size": int(latest.get("size") or 0),
        "signer_key_id": str(latest.get("signer_key_id") or ""),
        "installed_at": latest.get("generated_at") or "",
    })
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
        except OSError as exc:  # noqa: BLE001 — Windows 句柄延迟：跳过下次再清
            logger.warning("event=kb_tree_cleanup_failed dir=%s err=%s", child.name, exc)


async def sync_tree() -> dict:
    """拉一次 CDN 树。返回 {status: synced|current|skipped|failed, ...}；
    永不抛异常、永不覆盖好缓存。"""
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
    import asyncio

    import httpx

    keys = _trust_keys()
    if not keys:
        return {"status": "skipped", "reason": "not_configured"}

    async with httpx.AsyncClient() as client:
        latest = None
        base = ""
        verdicts: list[str] = []
        for candidate in _cdn_bases():
            latest_url = _derive(candidate, "latest.json")
            ok, verdict = await asyncio.to_thread(_validate_outbound, latest_url)
            verdicts.append(verdict)
            if not ok:
                continue
            probe = await _fetch_json(client, latest_url)
            if probe is not None and verify_tree_pointer(probe, keys):
                base, latest = candidate, probe
                break
        if latest is None:
            reason = "proxy_fake_ip" if "fakeip" in verdicts else "latest_invalid"
            return {"status": "failed", "reason": reason}
        try:
            version = int(latest.get("version") or 0)
        except (TypeError, ValueError):
            return {"status": "failed", "reason": "latest_version_invalid"}
        sha = str(latest.get("taxonomy_sha256") or "")
        size = latest.get("size")
        if version <= 0 or len(sha) != 64 or not isinstance(size, int):
            return {"status": "failed", "reason": "latest_fields_invalid"}

        receipt = read_receipt()
        receipt_version = int(receipt.get("version") or 0) if receipt else 0
        if receipt_version and version < receipt_version:
            return {
                "status": "skipped", "reason": "older_than_installed",
                "installed": receipt_version, "latest": version,
            }
        if receipt_version == version and _cached_file_ok(version, sha) is not None:
            return {"status": "current", "version": version}
        # 同版本缓存损坏/丢失 → 走到下面的修复重下（不 return current）

        tree_url = _derive(base, f"v{version}/taxonomy.json")
        tree_ok, _v = await asyncio.to_thread(_validate_outbound, tree_url)
        if not tree_ok:
            return {"status": "failed", "reason": "unsafe_url"}
        raw = await _fetch_bytes(client, tree_url)
        if raw is None:
            return {"status": "failed", "reason": "tree_fetch"}
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
    import asyncio

    import httpx

    keys = _trust_keys()
    installed = int((read_receipt() or {}).get("version") or 0)
    if not keys:
        return {"installed": installed, "latest": 0,
                "update_available": False, "reason": "not_configured"}
    async with httpx.AsyncClient() as client:
        probe_verdicts: list[str] = []
        for candidate in _cdn_bases():
            url = _derive(candidate, "latest.json")
            ok, verdict = await asyncio.to_thread(_validate_outbound, url)
            probe_verdicts.append(verdict)
            if not ok:
                continue
            probe = await _fetch_json(client, url)
            if probe is not None and verify_tree_pointer(probe, keys):
                try:
                    version = int(probe.get("version") or 0)
                except (TypeError, ValueError):
                    version = 0
                return {
                    "installed": installed, "latest": version,
                    "update_available": bool(version and version != installed),
                    "reason": "",
                }
    reason = "proxy_fake_ip" if "fakeip" in probe_verdicts else "latest_invalid"
    return {"installed": installed, "latest": 0,
            "update_available": False, "reason": reason}


def _reload_taxonomy() -> None:
    from kb.taxonomy import reload

    reload()


def schedule_sync() -> None:
    """启动补偿：KB_TREE_SYNC=0 关（测试/诊断）；手动 sync_tree 不受闸。"""
    import asyncio

    global _sync_task
    if (os.environ.get("KB_TREE_SYNC") or "").strip() == "0":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # 无运行中 loop（纯脚本/导入期）＝不安排
    _sync_task = loop.create_task(_sync_with_logging())


async def _sync_with_logging() -> None:
    result = await sync_tree()
    if result.get("status") in ("synced", "failed"):
        logger.info("event=kb_tree_sync %s", json.dumps(result, ensure_ascii=False))


def tree_state() -> dict:
    """给 API/UI 的只读状态：树是否就绪、版本、缓存路径。"""
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
    "probe_latest",
    "read_receipt",
    "schedule_sync",
    "sync_tree",
    "tree_root",
    "tree_state",
    "validate_tree_payload",
    "verify_tree_pointer",
    "write_receipt",
]
