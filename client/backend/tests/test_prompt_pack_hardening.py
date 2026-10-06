"""c-prompt-pack-hardening：本机提取防护的回归钉子。

覆盖 spec「prompt-pack-delivery」新增/修改的行为契约：
- 落盘零明文（容器 + 不落任何可直读模板文本）
- 本地包密钥绑机器与用户（跨机/换钥 → 解不开 → 按未装，不得退回明文可用）
- 容器 AAD 绑版本（掉包到别的版本目录要解不开）
- 读路径不落中间文件、模板文本不进日志
- 旧版明文包就地迁移（离线可用）；迁移失败＝按未装（不得保留明文）

钥匙库统一走 `AINOVEL_PACK_KEYSTORE=weak`（派生式）——避免测试触碰真实 Keychain/DPAPI；
弱档与真档只换钥匙、不改语义，故上述契约同等生效。
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import time

import pytest

MARK = "你是助手（hardening-marker-7f3a）"
TEMPLATE = f"{MARK}\n<<system>>系统段\n<<user>>用户段"


@pytest.fixture()
def packenv(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("PROMPT_PACK_MODE", "force")
    monkeypatch.setenv("AINOVEL_PACK_KEYSTORE", "weak")
    import prompt_pack
    import prompt_pack.container
    import prompt_pack.localkey
    import prompt_pack.sync
    import prompts

    mods = (prompt_pack, prompt_pack.localkey, prompt_pack.container, prompt_pack.sync, prompts)
    for m in mods:
        importlib.reload(m)
    yield tmp_path, prompt_pack, prompts
    for m in mods:
        importlib.reload(m)


def _write_pack(pp, version: str = "7", templates: dict[str, str] | None = None, *, plaintext: bool = False) -> str:
    """按需造一个已装包（容器或旧版明文）＋receipt，返回版本目录。"""
    templates = templates or {"write_chapter": TEMPLATE}
    root = pp.pack_root()
    vdir = os.path.join(root, f"v{version}")
    os.makedirs(vdir, exist_ok=True)
    if plaintext:
        for name, text in templates.items():
            with open(os.path.join(vdir, f"{name}.prompt"), "w", encoding="utf-8") as f:
                f.write(text)
    else:
        with open(os.path.join(vdir, pp.container.CONTAINER_NAME), "wb") as f:
            f.write(pp.container.seal(templates, version))
    with open(os.path.join(vdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version}, f)
    pp.write_receipt(
        {
            "version": version,
            "tier": "free",
            "key_id": "k-test",
            "installed_at": time.time(),
            "templates": {n: hashlib.sha256(t.encode("utf-8")).hexdigest() for n, t in templates.items()},
        }
    )
    return vdir


def _iter_files(root: str):
    for base, _dirs, names in os.walk(root):
        for n in names:
            yield os.path.join(base, n)


def test_installed_pack_contains_no_plaintext(packenv):
    """落盘零明文：包目录里没有 .prompt，也没有任何文件含模板文本（含 receipt/manifest）。"""
    _tmp, pp, _prompts = packenv
    _write_pack(pp)
    files = list(_iter_files(pp.pack_root()))
    assert files, "包目录为空——断言本身失效"
    assert not [f for f in files if f.endswith(".prompt")], "容器形态下不该再出现 .prompt 明文"
    for f in files:
        with open(f, "rb") as fh:
            assert MARK.encode("utf-8") not in fh.read(), f"{f} 里出现了模板明文"


def test_container_is_bound_to_key_and_version(packenv):
    """容器 AAD 绑版本；换钥匙即解不开（ContainerInvalid）。"""
    _tmp, pp, _prompts = packenv
    templates = {"write_chapter": TEMPLATE}
    blob = pp.container.seal(templates, "7")
    assert pp.container.open_container(blob, "7") == templates

    with pytest.raises(pp.container.ContainerInvalid):
        pp.container.open_container(blob, "8")  # 掉包到别的版本目录

    pp.localkey.drop_key(pp.pack_root())
    # 另一台机器（机器指纹不同）→ 派生钥匙不同 → 同一份容器解不开
    orig = pp.localkey.machine_id
    pp.localkey.machine_id = lambda: "another-machine-uuid"
    try:
        with pytest.raises(pp.container.ContainerInvalid):
            pp.container.open_container(blob, "7")
    finally:
        pp.localkey.machine_id = orig


def test_pack_unreadable_on_another_machine(packenv, monkeypatch):
    """换机场景：解不开 → 按「未装包」（load 抛 PromptPackMissing），不得退回明文或垃圾。"""
    _tmp, pp, prompts = packenv
    _write_pack(pp)
    assert MARK in prompts.load("write_chapter")

    monkeypatch.setattr(pp.localkey, "machine_id", lambda: "another-machine-uuid")
    assert pp.read_all_templates() is None
    with pytest.raises(prompts.PromptPackMissing):
        prompts.load("write_chapter")


def test_plaintext_pack_migrates_offline(packenv, monkeypatch):
    """存量明文包：首次读就地加密迁移 → 无需联网即可用；迁移后目录零明文。"""
    _tmp, pp, prompts = packenv
    vdir = _write_pack(pp, plaintext=True)

    def _no_network(*_a, **_k):  # 任何出站都视为失败：迁移必须是纯本地的
        raise AssertionError("迁移路径不应发起网络请求")

    monkeypatch.setattr(pp.sync, "_fetch_bytes", _no_network)
    monkeypatch.setattr(pp.sync, "_fetch_json", _no_network)

    assert MARK in prompts.load("write_chapter"), "迁移后应照常可读（离线）"
    assert os.path.isfile(os.path.join(vdir, pp.container.CONTAINER_NAME)), "迁移应产出容器"
    assert not [n for n in os.listdir(vdir) if n.endswith(".prompt")], "迁移后明文必须清掉"
    assert MARK in prompts.load("write_chapter"), "二次读仍可用（幂等）"


def test_migration_failure_leaves_no_plaintext(packenv, monkeypatch):
    """迁移失败（如钥匙不可用）→ 按未装处理，且**不得保留明文可用态**。"""
    _tmp, pp, prompts = packenv
    vdir = _write_pack(pp, plaintext=True)

    def _boom(*_a, **_k):
        raise RuntimeError("seal failed")

    monkeypatch.setattr(pp.container, "seal", _boom)
    with pytest.raises(prompts.PromptPackMissing):
        prompts.load("write_chapter")
    assert not [n for n in os.listdir(vdir) if n.endswith(".prompt")], (
        "迁移失败后仍留着明文模板——违反「不得退回明文可用态」"
    )


def test_read_path_writes_nothing(packenv, tmp_path):
    """读模板不落任何中间文件：包目录与系统临时目录读前后零变化。"""
    import tempfile

    _tmp, pp, prompts = packenv
    _write_pack(pp)

    def snapshot(root: str) -> set[tuple[str, int, int]]:
        out = set()
        for base, _dirs, names in os.walk(root):
            for n in names:
                p = os.path.join(base, n)
                st = os.stat(p)
                out.add((p, st.st_size, st.st_mtime_ns))
        return out

    tmpdir = tempfile.gettempdir()
    before_pack, before_tmp = snapshot(pp.pack_root()), set(os.listdir(tmpdir))
    prompts.load("write_chapter")
    prompts.load_layers("write_chapter")
    assert snapshot(pp.pack_root()) == before_pack, "读路径改动了包目录"
    assert set(os.listdir(tmpdir)) == before_tmp, "读路径在系统临时目录落了东西"


def test_template_text_never_reaches_logs(packenv, caplog):
    """模板文本不进日志：安装/迁移/读全链在 DEBUG 级别下也不出现模板内容。"""
    import logging

    _tmp, pp, prompts = packenv
    with caplog.at_level(logging.DEBUG):
        _write_pack(pp, plaintext=True)  # 触发迁移路径
        prompts.load("write_chapter")
        pp.read_all_templates()
    assert MARK not in caplog.text, "日志里出现了模板明文"


def test_keystore_level_is_explicit(packenv, monkeypatch):
    """弱保护档要显式可见（不静默）：env 指定生效，且弱档钥匙随机器指纹变化。"""
    _tmp, pp, _prompts = packenv
    assert pp.localkey.protection_level() == pp.localkey.PROTECTION_WEAK
    k1 = pp.localkey.get_or_create_key(pp.pack_root())
    monkeypatch.setattr(pp.localkey, "machine_id", lambda: "another-machine-uuid")
    k2 = pp.localkey.get_or_create_key(pp.pack_root())
    assert len(k1) == 32 and k1 != k2

def test_key_unavailable_falls_back_to_not_installed(packenv, monkeypatch):
    """钥匙不可用（换机/换用户/封装损坏）＝按未装包：读侧拒绝、不抛到调用栈外、不留明文。"""
    _tmp, pp, prompts = packenv
    _write_pack(pp)
    assert MARK in prompts.load("write_chapter")

    def _unavailable(_pack_root):
        raise pp.localkey.LocalKeyUnavailable("DPAPI 解封失败（换了机器或用户账户）")

    monkeypatch.setattr(pp.localkey, "get_or_create_key", _unavailable)
    assert pp.read_all_templates() is None
    with pytest.raises(prompts.PromptPackMissing):
        prompts.load("write_chapter")
