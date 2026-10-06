"""c-prompt-pack-client 3.x：同步器全链测试。

本地假 CDN（http.server 线程）＋ Ed25519 测试钥对 ＋ AES-GCM bundle fixture；
SSRF 校验以 monkeypatch 放行（校验逻辑本身另由真实域断言覆盖）。
"""

import base64
import hashlib
import http.server
import importlib
import json
import os
import threading

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    # force 模式：模拟 frozen 发布包（无包内目录）——get_status 暴露原始状态机，
    # dev 兜底可用性由专项测试（delenv）单独验证
    monkeypatch.setenv("PROMPT_PACK_MODE", "force")
    import prompt_pack
    import prompt_pack.sync as sync_mod
    import prompts

    importlib.reload(prompt_pack)
    importlib.reload(sync_mod)
    importlib.reload(prompts)
    yield tmp_path, prompt_pack, sync_mod, prompts
    importlib.reload(sync_mod)
    importlib.reload(prompt_pack)
    importlib.reload(prompts)


@pytest.fixture()
def cdn(tmp_path, monkeypatch):
    """假 CDN：tmp 目录作根 + http.server 线程；返回 (base_url, publish)。"""
    root = tmp_path / "cdn"
    root.mkdir()
    import functools

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: ANN002
            pass

    handler = functools.partial(_Quiet, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("CLIENT_PROMPT_PACK_URL", f"{base}/prompts/latest.json")
    monkeypatch.setenv("CLIENT_PROMPT_PACK_URL_FALLBACK", f"{base}/prompts/latest.json")
    yield base, root
    srv.shutdown()


# ── 加密/签名 fixture ────────────────────────────────────────────────────────

def _keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return sk, base64.b64encode(pub).decode()


def _sign(manifest_without_sig: dict, sk) -> str:
    blob = json.dumps(manifest_without_sig, sort_keys=True, separators=(",", ":")).encode()
    return base64.b64encode(sk.sign(blob)).decode()


def _bundle(templates: dict, version: str, tier: str, cek: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    plain = json.dumps({"version": version, "tier": tier, "templates": templates}).encode()
    return nonce + AESGCM(cek).encrypt(nonce, plain, None)


def _publish(root, version, tier_map, templates_by_tier, sk, kid,
             min_client_version=None, min_pack_version=None):
    """tier_map: {tier: (key_id, cek_bytes)}；模板清单跨档相同（test 简化）。"""
    import pathlib

    vdir = pathlib.Path(root) / "prompts" / f"v{version}"
    vdir.mkdir(parents=True, exist_ok=True)
    tpl_hashes = {n: hashlib.sha256(t.encode()).hexdigest() for n, t in templates_by_tier.items()}
    tiers = {}
    for tier, (kid_, cek) in tier_map.items():
        blob = _bundle(templates_by_tier, version, tier, cek)
        (vdir / f"{tier}.bin").write_bytes(blob)
        tiers[tier] = {
            "key_id": kid_,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "template_count": len(templates_by_tier),
        }
    manifest = {
        "schema_version": 1,
        "version": version,
        "signer_key_id": kid,
        "tiers": tiers,
        "templates": tpl_hashes,
    }
    if min_client_version:
        manifest["min_client_version"] = min_client_version
    manifest["signature"] = _sign(manifest, sk)
    (vdir / "manifest.json").write_text(json.dumps(manifest))
    latest = {
        "schema_version": 1,
        "version": version,
        "min_client_version": min_client_version or "",
        "min_pack_version": min_pack_version or "",
        "published_at": "2026-10-05T00:00:00Z",
        "tiers": tiers,
        "signer_key_id": kid,
    }
    manifest_for_latest = dict(latest)
    latest["signature"] = _sign(manifest_for_latest, sk)
    (pathlib.Path(root) / "prompts").mkdir(exist_ok=True)
    (pathlib.Path(root) / "prompts" / "latest.json").write_text(json.dumps(latest))
    return manifest, latest


TPL = {"write_chapter": "<<system>>\n你是助手\n<<user>>\n写"}


def _wire(env, monkeypatch, sk, pub_b64, exchange):
    _, pp, sync_mod, _ = env
    monkeypatch.setattr(sync_mod, "_validate_outbound", lambda url: True)
    monkeypatch.setenv("CLIENT_PACK_PUBKEYS", json.dumps({"test-kid": pub_b64}))
    monkeypatch.setattr(sync_mod, "_exchange_cek", exchange)
    return pp, sync_mod


def test_sync_happy_path_installs(env, cdn, monkeypatch):
    root, _ = cdn if False else cdn  # base, root
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))

    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "ready"
    receipt = pp.read_receipt()
    assert receipt["version"] == "5" and receipt["tier"] == "free"
    assert pp.read_highwatermark() == "5"
    # loader 读包内版本
    _, _, _, prompts = env
    assert "你是助手" in prompts.load("write_chapter")


def test_sync_tampered_bundle_rejected_keeps_old(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    # 先装 v5 成功
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    # 再发 v6 且篡改 bin（hash 不匹配）
    _publish(cdn_root, "6", {"free": ("k-free-6", cek)}, TPL, sk, "test-kid")
    bin_path = cdn_root / "prompts" / "v6" / "free.bin"
    bin_path.write_bytes(bin_path.read_bytes() + b"x")
    st = sync_mod.sync_once(local_tier="free")
    # 失败矩阵：旧包可用即 ready（全静默）；失败原因保留为诊断字段
    assert st["phase"] == "ready" and st["reason"] == "bundle_hash"
    assert pp.read_receipt()["version"] == "5"  # 旧包保留


def test_sync_bad_signature_rejected(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    man, latest = _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    # 篡改 manifest（保留原签名）→ 验签失败
    man["templates"]["write_chapter"] = "0" * 64
    (cdn_root / "prompts" / "v5" / "manifest.json").write_text(json.dumps(man))
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (None, -1))
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "failed" and st["reason"] == "signature"


def test_sync_highwatermark_blocks_replay(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "7", {"free": ("k-free-7", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    # 攻击者重放 v6（签名合法）→ 高水位挡
    _publish(cdn_root, "6", {"free": ("k-free-6", cek)}, TPL, sk, "test-kid")
    st = sync_mod.sync_once(local_tier="free")
    assert pp.read_receipt()["version"] == "7"
    assert st.get("version") == "7"


def test_sync_403_downgrades_tier(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"pro": ("k-pro-5", cek), "free": ("k-free-5", cek)}, TPL, sk, "test-kid")

    def exchange(kid, ver):
        if kid == "k-pro-5":
            return None, 403  # 本地以为 pro，S端 说不够
        return {"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0

    pp, sync_mod = _wire(env, monkeypatch, sk, pub, exchange)
    st = sync_mod.sync_once(local_tier="pro")
    assert st["phase"] == "ready" and st["tier"] == "free"


def test_sync_all_tiers_403_tier_denied(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (None, 403))
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "tier_denied"


def test_sync_404_reports_key_retired(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (None, 404))
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "failed" and st["reason"] == "key_retired"


def test_sync_min_pack_version_retires_installed(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "3", {"free": ("k-free-3", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    # v4 召回底线=4：已装 v3 被召回，装 v4
    _publish(cdn_root, "4", {"free": ("k-free-4", cek)}, TPL, sk, "test-kid", min_pack_version="4")
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "ready" and pp.read_receipt()["version"] == "4"


def test_sync_already_latest_is_ready(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    calls = []
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (calls.append(1), ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))[1])
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    n = len(calls)
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "ready" and len(calls) == n  # 已最新：不再换钥


def test_sync_no_keys_skips(env, cdn, monkeypatch):
    base, cdn_root = cdn
    _, pp, sync_mod, _ = env
    monkeypatch.setattr(sync_mod, "_validate_outbound", lambda url: True)
    monkeypatch.delenv("CLIENT_PACK_PUBKEYS", raising=False)
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] in ("missing", "failed")  # 不假装成功


# ── 6.x：PromptPackMissing → 503 {reason: prompts_missing}（唯一收敛点）────────

def test_prompts_missing_handler_returns_503_envelope(env):
    """storage_busy 同款处理器形态：503＋reason＋引导文案；无包时 loader 真抛。"""
    import asyncio
    import json as _json

    from main import _prompts_missing_handler
    from prompts import PromptPackMissing

    _, _, sync_mod, prompts = env
    import os as _os

    _os.environ["PROMPT_PACK_MODE"] = "force"  # 禁包内目录跳 → 真抛
    try:
        try:
            prompts.load("write_chapter")
            raise AssertionError("force 模式无包应抛 PromptPackMissing")
        except PromptPackMissing as exc:
            resp = asyncio.run(_prompts_missing_handler(None, exc))  # type: ignore[arg-type]
        body = _json.loads(resp.body)
        assert resp.status_code == 503
        assert body["detail"]["reason"] == "prompts_missing"
        assert "写作能力" in body["detail"]["message"]
    finally:
        import os as _os2

        _os2.environ.pop("PROMPT_PACK_MODE", None)


def test_ai_states_contains_prompts_missing():
    """双端枚举同批（D13）：后端 AI_STATES 必须含新 reason。"""
    from ai_state import AI_STATES

    assert "prompts_missing" in AI_STATES


def test_sync_same_version_tier_upgrade(env, cdn, monkeypatch):
    """同版本换档（免费→PRO）：不短路、补写新增模板、receipt 换档（实测抓到的回归）。"""
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    tpls = {"a": "<<system>>\nA\n<<user>>\nx", "b": "<<system>>\nB\n<<user>>\ny"}
    # free 档只含 a；pro 档含 a+b（bundle 内容不同但 version 相同）
    import hashlib as _h
    import pathlib

    v = "5"
    vdir = pathlib.Path(cdn_root) / "prompts" / f"v{v}"
    vdir.mkdir(parents=True)
    tiers = {}
    for tier, keys in (("free", ["a"]), ("pro", ["a", "b"])):
        sub = {k: tpls[k] for k in keys}
        blob = _bundle(sub, v, tier, cek)
        (vdir / f"{tier}.bin").write_bytes(blob)
        tiers[tier] = {
            "key_id": f"k-{tier}-{v}",
            "sha256": _h.sha256(blob).hexdigest(),
            "size": len(blob),
            "template_count": len(sub),
        }
    man = {"schema_version": 1, "version": v, "signer_key_id": "test-kid", "tiers": tiers,
           "templates": {k: _h.sha256(t.encode()).hexdigest() for k, t in tpls.items()}}
    man["signature"] = _sign(man, sk)
    (vdir / "manifest.json").write_text(json.dumps(man))
    latest = {"schema_version": 1, "version": v, "min_client_version": "", "min_pack_version": "",
              "tiers": tiers, "signer_key_id": "test-kid"}
    latest["signature"] = _sign(latest, sk)
    (pathlib.Path(cdn_root) / "prompts" / "latest.json").write_text(json.dumps(latest))

    def exchange(kid, ver):
        for t, e in tiers.items():
            if e["key_id"] == kid:
                return {"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": t, "version": ver}, 0
        return None, 404

    pp, sync_mod = _wire(env, monkeypatch, sk, pub, exchange)
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    assert len(pp.read_receipt()["templates"]) == 1
    # 升级 PRO（同版本）：应补写 b 并换档
    st = sync_mod.sync_once(local_tier="pro")
    rec = pp.read_receipt()
    assert st["phase"] == "ready" and st["tier"] == "pro"
    assert rec["tier"] == "pro" and len(rec["templates"]) == 2
    _, _, _, prompts = env
    import importlib as _il

    _il.reload(prompts)
    assert "B" in prompts.load("b")


def test_sync_tampered_latest_rejected_not_consumed(env, cdn, monkeypatch):
    """评审 P1：latest 未验签不得消费控制字段——篡改 min_pack_version 不触发清回执、
    篡改 min_client_version 不静默冻结。"""
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    # 篡改 latest：巨大 min_pack_version（意图清回执）＋巨大 min_client_version（意图冻结）——不重签
    latest_p = cdn_root / "prompts" / "latest.json"
    doc = json.loads(latest_p.read_text())
    doc["min_pack_version"] = "99"
    doc["min_client_version"] = "99"
    latest_p.write_text(json.dumps(doc))
    st = sync_mod.sync_once(local_tier="free")
    assert st["reason"] == "latest_signature"  # 验签不过＝该源不可信
    assert pp.read_receipt()["version"] == "5"  # 回执未被清除


def test_sync_404_refetches_latest_and_retries_once(env, cdn, monkeypatch):
    """评审 P3：404（密钥退役）→ 重取 latest（cache-bust）→ 版本变化则重试一次装新版。"""
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "6", {"free": ("k-free-6", cek)}, TPL, sk, "test-kid")
    stale_latest = json.loads((cdn_root / "prompts" / "latest.json").read_text())  # v6 指针快照
    _publish(cdn_root, "7", {"free": ("k-free-7", cek)}, TPL, sk, "test-kid")  # 磁盘上已是 v7

    _, _, sync_mod, _ = env
    monkeypatch.setattr(sync_mod, "_validate_outbound", lambda url: True)
    monkeypatch.setenv("CLIENT_PACK_PUBKEYS", json.dumps({"test-kid": pub}))

    def exchange(kid, ver):
        if kid == "k-free-6":
            return None, 404  # v6 密钥已退役
        return {"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0

    monkeypatch.setattr(sync_mod, "_exchange_cek", exchange)
    orig_fetch = sync_mod._fetch_json

    def fetch(client, url):
        if "?cb=" in url or not url.endswith("latest.json"):
            return orig_fetch(client, url)  # cb 请求与其余资源（manifest/bin）走磁盘
        return stale_latest  # 仅 latest 指针返回陈旧 v6（模拟 CDN 缓存）

    monkeypatch.setattr(sync_mod, "_fetch_json", fetch)
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "ready" and str(st.get("version")) == "7"
    import prompt_pack as pp2

    assert pp2.read_receipt()["version"] == "7"


def test_status_ready_with_dev_fallback(env, monkeypatch):
    """评审 P1：dev/测试态（非 force 且包内目录存在）＝写作能力可用 → ready 全静默。"""
    _, _, sync_mod, _ = env
    monkeypatch.delenv("PROMPT_PACK_MODE", raising=False)  # 模拟 dev 会话
    st = sync_mod.get_status()
    assert st["phase"] == "ready"
    monkeypatch.setenv("PROMPT_PACK_MODE", "force")  # 模拟 frozen：无包则如实报未就绪
    assert sync_mod.get_status()["phase"] != "ready"


def test_exchange_cek_carries_token_flag(env, monkeypatch):
    """换钥必须带登录态（with_token=True）——联调实测缺口回归钉：
    call_server_api 默认不附 Authorization，换钥端点必 401。"""
    import asyncio

    import auth_local.service as svc

    captured = {}

    async def fake_call(endpoint, method="GET", params=None, json_body=None, with_token=False):
        captured.update(endpoint=endpoint, with_token=with_token)
        return {"code": 0, "data": {"cek": "x", "key_id": "k", "tier": "free", "version": "v"}}

    monkeypatch.setattr(svc, "call_server_api", fake_call)
    _, _, sync_mod, _ = env
    value, code = sync_mod._exchange_cek("k-1", "v-1")
    assert code == 0 and value["key_id"] == "k"
    assert captured == {"endpoint": "prompt-pack/key", "with_token": True}


def test_sync_repairs_tampered_installed_pack(env, cdn, monkeypatch):
    """评审 P1：已装包被篡改 → 读侧拒绝（PromptPackMissing）且同步器自愈
    （同版本重装修复）——spec「读时校验失败须可自愈」的触发器回归钉。"""
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"

    fp = os.path.join(pp.pack_root(), "v5", "write_chapter.prompt")
    with open(fp, "a", encoding="utf-8") as f:
        f.write("篡改")

    _, _, _, prompts = env
    import importlib as _il

    _il.reload(prompts)
    with pytest.raises(prompts.PromptPackMissing):
        prompts.load("write_chapter")

    st = sync_mod.sync_once(local_tier="free")  # 同版本，但完整性复核不过 → 重装
    assert st["phase"] == "ready"
    assert "篡改" not in open(fp, encoding="utf-8").read(), "篡改文件未被修复"
    _il.reload(prompts)
    assert "你是助手" in prompts.load("write_chapter")


def test_sync_same_tier_probe_skips_redownload(env, cdn, monkeypatch):
    """评审 P3：本地误报高档、S 判档仍等于已装档且本地完好 → 免重下重装
    （降档收敛探测出口；语义不变：真升档仍走下载安装）。"""
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek), "pro": ("k-pro-5", cek)}, TPL, sk, "test-kid")

    def exchange(kid, ver):
        if kid == "k-pro-5":
            return None, 403  # S 拒绝高档（本地误报）
        return {"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0

    pp, sync_mod = _wire(env, monkeypatch, sk, pub, exchange)
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"

    downloads = []
    orig_fetch_bytes = sync_mod._fetch_bytes
    monkeypatch.setattr(
        sync_mod, "_fetch_bytes",
        lambda c, u: (downloads.append(u), orig_fetch_bytes(c, u))[1],
    )
    st = sync_mod.sync_once(local_tier="pro")  # 本地误报 pro
    assert st["phase"] == "ready" and st["tier"] == "free"
    assert downloads == [], f"同档探测不应重下（实得 {downloads}）"
    assert pp.read_receipt()["tier"] == "free"
