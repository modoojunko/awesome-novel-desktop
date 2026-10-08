"""c-prompt-pack-client 2.x：本地布局与 loader 解析序测试。

覆盖：receipt 原子读写/清除、高水位、版本目录解析（含 min_client_version 拒载
回落）、loader 三跳解析序（包目录→包内目录→PromptPackMissing）、强制包模式、
读时 sha256 校验。
"""

import hashlib
import importlib
import json
import os

import pytest


@pytest.fixture()
def pack_env(tmp_path, monkeypatch):
    """隔离 DATA_ROOT + 重载 prompt_pack/prompts（模块级缓存 hash 需清）。"""
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("PROMPT_PACK_MODE", raising=False)
    import prompt_pack
    import prompts

    importlib.reload(prompt_pack)
    importlib.reload(prompts)
    yield tmp_path, prompt_pack, prompts
    importlib.reload(prompt_pack)
    importlib.reload(prompts)


def _make_pack(root, version, templates: dict[str, str], min_client_version=None, tier="free"):
    """在 {DATA_ROOT}/prompt-pack 落一个已装版本目录＋receipt。"""
    vdir = os.path.join(str(root), "prompt-pack", f"v{version}")
    os.makedirs(vdir, exist_ok=True)
    hashes = {}
    for name, content in templates.items():
        with open(os.path.join(vdir, f"{name}.prompt"), "w", encoding="utf-8") as f:
            f.write(content)
        hashes[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest = {"version": version}
    if min_client_version:
        manifest["min_client_version"] = min_client_version
    with open(os.path.join(vdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    receipt = {
        "version": version,
        "tier": tier,
        "key_id": f"k-{tier}-{version}",
        "templates": hashes,
    }
    if min_client_version:
        receipt["min_client_version"] = min_client_version
    return vdir, receipt


def test_receipt_roundtrip_and_clear(pack_env):
    root, pp, _ = pack_env
    assert pp.read_receipt() is None
    _vdir, receipt = _make_pack(root, "3", {"a": "hello"})
    pp.write_receipt(receipt)
    assert pp.read_receipt()["version"] == "3"
    pp.clear_receipt()
    assert pp.read_receipt() is None


def test_resolve_dir_prefers_receipt_version(pack_env):
    root, pp, _ = pack_env
    _make_pack(root, "2", {"a": "old"})
    vdir3, receipt3 = _make_pack(root, "3", {"a": "new"})
    pp.write_receipt(receipt3)
    assert pp.resolve_dir() == vdir3


def test_resolve_dir_gate_falls_back_to_previous(pack_env):
    root, pp, _ = pack_env
    v2dir, _receipt2 = _make_pack(root, "2", {"a": "ok"})
    _v3dir, receipt3 = _make_pack(root, "3", {"a": "future"}, min_client_version="99.0.0")
    pp.write_receipt(receipt3)
    # 3 要求客户端 99.0.0（本机 dev/低版本）→ 拒载，回落 v2
    assert pp.resolve_dir() == v2dir


def test_resolve_dir_no_pack_returns_none(pack_env):
    _, pp, _ = pack_env
    assert pp.resolve_dir() is None


def test_highwatermark_roundtrip(pack_env):
    _, pp, _ = pack_env
    assert pp.read_highwatermark() == ""
    pp.write_highwatermark("7")
    assert pp.read_highwatermark() == "7"


def test_loader_reads_installed_pack(pack_env):
    root, pp, prompts = pack_env
    _vdir, receipt = _make_pack(root, "5", {"write_chapter": "<<system>>\npack 版正文"})
    pp.write_receipt(receipt)
    assert "pack 版正文" in prompts.load("write_chapter")


def test_loader_tampered_pack_falls_back_to_bundled(pack_env, monkeypatch):
    root, pp, prompts = pack_env
    # 回落源（解析序②）：主库零模板后 CI 无包内镜像，显式给 DEV_DIR 桩目录
    dev_dir = os.path.join(str(root), "dev-templates")
    os.makedirs(dev_dir, exist_ok=True)
    with open(os.path.join(dev_dir, "write_chapter.prompt"), "w", encoding="utf-8") as f:
        f.write("桩回落正文")
    monkeypatch.setenv("PROMPT_PACK_DEV_DIR", dev_dir)
    vdir, receipt = _make_pack(root, "5", {"write_chapter": "原件"})
    # 安装后手改文件 → 读时 sha256 不过 → 视为缺失 → 回落开发态模板目录
    with open(os.path.join(vdir, "write_chapter.prompt"), "w", encoding="utf-8") as f:
        f.write("被手改")
    pp.write_receipt(receipt)
    text = prompts.load("write_chapter")
    assert "被手改" not in text
    assert "桩回落正文" in text


def test_loader_force_mode_pack_missing(pack_env, monkeypatch):
    _, _pp, prompts = pack_env
    monkeypatch.setenv("PROMPT_PACK_MODE", "force")
    # 强制包模式 + 无已装包 → 禁用包内目录跳 → PromptPackMissing
    with pytest.raises(prompts.PromptPackMissing):
        prompts.load("write_chapter")
    assert issubclass(prompts.PromptPackMissing, FileNotFoundError)


def test_loader_force_mode_reads_pack(pack_env, monkeypatch):
    root, pp, prompts = pack_env
    monkeypatch.setenv("PROMPT_PACK_MODE", "force")
    _vdir, receipt = _make_pack(root, "5", {"write_chapter": "<<system>>\n包内版"})
    pp.write_receipt(receipt)
    assert "包内版" in prompts.load("write_chapter")


def test_load_layers_still_works_from_pack(pack_env):
    root, pp, prompts = pack_env
    body = "<<system>>\n## 头注释\n你是助手。\n<<user>>\n素材：{x}"
    _vdir, receipt = _make_pack(root, "5", {"write_chapter": body})
    pp.write_receipt(receipt)
    sys_seg, user_seg = prompts.load_layers("write_chapter")
    assert "你是助手。" in sys_seg and "头注释" not in sys_seg
    assert "素材：{x}" in user_seg


def test_verify_file_caches_by_mtime_size(pack_env):
    root, pp, _ = pack_env
    path = os.path.join(str(root), "t.prompt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("abc")
    expect = hashlib.sha256(b"abc").hexdigest()
    assert pp.verify_file(path, expect) is True
    assert pp.verify_file(path, "0" * 64) is False  # 缓存签名命中，比对值不同即 False
