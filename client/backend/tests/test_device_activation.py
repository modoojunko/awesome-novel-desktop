"""C端 设备注册与激活 — 编解码 + 平台身份链测试"""

import base64
import hashlib
import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _fresh_identity_memo():
    """身份值进程内 memoize：身份相关用例前后各清一次，防用例间串味。"""
    from auth_local.service import _reset_identity_memo

    _reset_identity_memo()
    yield
    _reset_identity_memo()

# ── encode_device_profile 测试 ──


def test_encode_device_profile_roundtrip():
    """编解码往返一致"""
    from auth_local.service import encode_device_profile

    result = encode_device_profile(
        {
            "fingerprint": "FP-001-ABCD",
            "hostname": "主开发机",
            "os": "Windows 11",
            "os_arch": "AMD64",
        }
    )
    assert isinstance(result, str)
    assert "=" not in result  # no padding

    # decode & verify
    raw = base64.urlsafe_b64decode(result + "==")
    data = json.loads(raw)
    assert data["f"] == "FP-001-ABCD"
    assert data["h"] == "主开发机"
    assert data["o"] == "Windows 11"
    assert data["a"] == "AMD64"


def test_encode_device_profile_empty_fields():
    """空字段编码正常"""
    from auth_local.service import encode_device_profile

    result = encode_device_profile(
        {
            "fingerprint": "",
            "hostname": "",
            "os": "",
            "os_arch": "",
        }
    )
    assert isinstance(result, str)
    raw = base64.urlsafe_b64decode(result + "==")
    data = json.loads(raw)
    assert data["f"] == ""
    assert data["h"] == ""


def test_encode_device_profile_minimal():
    """仅 fingerprint 也能编码"""
    from auth_local.service import encode_device_profile

    result = encode_device_profile({"fingerprint": "FP-X"})
    raw = base64.urlsafe_b64decode(result + "==")
    data = json.loads(raw)
    assert data["f"] == "FP-X"
    assert data["h"] == ""


# ── 占位值检测 ──


def test_identity_placeholder_detection():
    """空串 / 全 0 / 全 F（任意大小写与连字符形态）判无效，其余有效"""
    from auth_local.service import _is_valid_identity

    assert not _is_valid_identity("")
    assert not _is_valid_identity("   ")
    assert not _is_valid_identity("00000000-0000-0000-0000-000000000000")
    assert not _is_valid_identity("FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF")
    assert not _is_valid_identity("ffffffff-ffff-ffff-ffff-ffffffffffff")
    assert _is_valid_identity("12345678-90AB-4CDE-8F01-23456789ABCD")
    assert _is_valid_identity("5a1c9e02-machine-guid-like-value")
    assert _is_valid_identity("unknown")


# ── 采集链主路径（mock 子进程，按命令分发）──

_IOREG_OUT = (
    "+-o Root  <class IOPlatformExpertDevice, id 0x100000>\n"
    '    "IOPlatformUUID" = "12345678-90AB-4CDE-8F01-23456789ABCD"\n'
)
_PS_UUID = "4C4C4544-0042-5710-8031-B2C04F443532"
_MACHINE_GUID_OUT = (
    "\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography\n"
    f"    MachineGuid    REG_SZ    9f81c2de-guid-fallback-0001\n"
)


def _dispatch_result(**by_cmd):
    """按 cmd[0] 分发的 subprocess.run 替身：未命中命令抛 FileNotFoundError"""

    def fake_run(cmd, **kwargs):
        handler = by_cmd.get(cmd[0])
        if handler is None:
            raise FileNotFoundError(cmd[0])
        return handler

    return fake_run


def test_identity_macos_ioreg():
    """macOS 主路径：IOPlatformUUID 被采纳，pc_hash 与指纹同源且与主机名无关"""
    from auth_local.service import (
        _platform_identity,
        collect_device_profile,
        generate_pc_hash,
    )

    with (
        patch(
            "subprocess.run",
            side_effect=_dispatch_result(ioreg=type("R", (), {"returncode": 0, "stdout": _IOREG_OUT, "stderr": ""})()),
        ),
        patch("platform.node", return_value="drifting-hostname.local"),
    ):
        assert _platform_identity() == "12345678-90AB-4CDE-8F01-23456789ABCD"
        profile = collect_device_profile()
        expected = hashlib.sha256(
            b"12345678-90AB-4CDE-8F01-23456789ABCD"
        ).hexdigest()
        assert profile["fingerprint"] == expected
        # 同源：pc_hash = 指纹的前 32 位
        assert generate_pc_hash() == expected[:32]


def test_identity_macos_independent_of_hostname():
    """主机名漂移（换网络改名）不改变采集链产出的身份"""
    from auth_local.service import _platform_identity, _reset_identity_memo

    with patch(
        "subprocess.run",
        side_effect=_dispatch_result(ioreg=type("R", (), {"returncode": 0, "stdout": _IOREG_OUT, "stderr": ""})()),
    ):
        with patch("platform.node", return_value="MacBook-Pro.local"):
            first = _platform_identity()
        _reset_identity_memo()
        with patch("platform.node", return_value="MacBook-Pro-2.local"):
            second = _platform_identity()
    assert first == second == "12345678-90AB-4CDE-8F01-23456789ABCD"


def test_identity_windows_smbios_uuid():
    """Windows 主路径：PowerShell CIM 取 SMBIOS UUID，MachineGuid 不被消费"""
    from auth_local.service import _platform_identity

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "ioreg":
            raise FileNotFoundError(cmd[0])
        if cmd[0] == "powershell":
            return type("R", (), {"returncode": 0, "stdout": _PS_UUID + "\n", "stderr": ""})()
        raise FileNotFoundError(cmd[0])

    with patch("subprocess.run", side_effect=fake_run):
        assert _platform_identity() == _PS_UUID
    assert "reg" not in calls


def test_identity_windows_fallback_machine_guid():
    """SMBIOS UUID 为全 0 占位（老主板）时降级注册表 MachineGuid"""
    from auth_local.service import _platform_identity

    def fake_run(cmd, **kwargs):
        if cmd[0] == "powershell":
            return type(
                "R",
                (),
                {
                    "returncode": 0,
                    "stdout": "00000000-0000-0000-0000-000000000000\n",
                    "stderr": "",
                },
            )()
        if cmd[0] == "reg":
            return type(
                "R",
                (),
                {"returncode": 0, "stdout": _MACHINE_GUID_OUT, "stderr": ""},
            )()
        raise FileNotFoundError(cmd[0])

    with patch("subprocess.run", side_effect=fake_run):
        assert _platform_identity() == "9f81c2de-guid-fallback-0001"


def test_identity_linux_machine_id():
    """Linux 主路径：/etc/machine-id 被采纳（macOS/Windows 命令全部缺失）"""
    from auth_local.service import _platform_identity

    def fake_read_text(self, **kwargs):
        if str(self) == "/etc/machine-id":
            return "b0f5a3e1-machine-id-value-0001\n"
        raise OSError(self)

    with (
        patch("subprocess.run", side_effect=_dispatch_result()),
        patch("pathlib.Path.read_text", fake_read_text),
    ):
        assert _platform_identity() == "b0f5a3e1-machine-id-value-0001"


def test_identity_full_chain_failure_falls_back_to_hostname():
    """全链失败（命令缺失+machine-id 不可读）兜底 platform.node()，行为同旧版"""
    from auth_local.service import _platform_identity

    def fake_read_text(self, **kwargs):
        raise OSError(self)

    with (
        patch("subprocess.run", side_effect=_dispatch_result()),
        patch("pathlib.Path.read_text", fake_read_text),
        patch("platform.node", return_value="last-resort-pc"),
    ):
        assert _platform_identity() == "last-resort-pc"


# ── 稳定性（config 丢失重生成同身份）──


def test_pc_hash_stable_across_config_loss(tmp_path, monkeypatch):
    """删 config.json 后重生成 pc_hash 不变（同机身份不随 config 重建漂移）"""
    from auth_local import service as svc

    cfg = tmp_path / "config.json"
    monkeypatch.setattr(svc, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(svc, "CONFIG_FILE", str(cfg))
    svc._reset_config_cache()

    first = svc.load_or_create_config()["pc_hash"]
    assert first

    cfg.unlink()
    svc._reset_config_cache()
    second = svc.load_or_create_config()["pc_hash"]

    assert second == first


# ── collect_device_profile 测试 ──


def test_collect_device_profile_fallback_on_no_subprocess():
    """命令全部不可用时（非 macOS/Windows/Linux 常规环境），使用 platform 兜底"""

    from auth_local.service import collect_device_profile

    with (
        patch("subprocess.run", side_effect=FileNotFoundError("no cmd")),
        patch("platform.node", return_value="test-pc"),
        patch("platform.platform", return_value="Linux-5.15-x86_64"),
        patch("platform.machine", return_value="x86_64"),
    ):
        profile = collect_device_profile()
        assert profile["hostname"] == "test-pc"
        assert profile["os"] == "Linux-5.15-x86_64"
        assert profile["os_arch"] == "x86_64"
        assert len(profile["fingerprint"]) == 64  # sha256 hex


def test_collect_device_profile_fingerprint_derives_from_identity():
    """fingerprint 一定是 64 字符 hex 字符串"""
    from auth_local.service import collect_device_profile

    with (
        patch("subprocess.run", side_effect=FileNotFoundError("no cmd")),
        patch("platform.node", return_value="test-pc"),
        patch("platform.platform", return_value="Linux"),
        patch("platform.machine", return_value="x86_64"),
    ):
        profile = collect_device_profile()
        assert len(profile["fingerprint"]) == 64
        # 验证是 hex
        int(profile["fingerprint"], 16)
        assert profile["fingerprint"] == hashlib.sha256(b"test-pc").hexdigest()


def test_collect_device_profile_wmic_retired():
    """wmic 已退役：采集链不再发出任何 wmic 命令（Win11 24H2 起该命令不存在）"""
    from auth_local.service import collect_device_profile

    seen_cmds = []

    def fake_run(cmd, **kwargs):
        seen_cmds.append(list(cmd))
        raise FileNotFoundError(cmd[0])

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("platform.node", return_value="audit-pc"),
        patch("platform.platform", return_value="Windows 11"),
        patch("platform.machine", return_value="AMD64"),
    ):
        collect_device_profile()
        assert seen_cmds, "采集链应尝试过平台命令"
        assert all(cmd[0] != "wmic" for cmd in seen_cmds)


# ── S端 编解码兼容性验证 ──


def test_encode_decode_compatible_format():
    """C端 编码格式与 S端 期望的格式一致（短字段名）"""
    from auth_local.service import encode_device_profile

    device_info = {
        "fingerprint": "a1b2c3d4e5f6",
        "hostname": "MY-PC",
        "os": "Windows 10",
        "os_arch": "x86_64",
    }
    encoded = encode_device_profile(device_info)
    assert isinstance(encoded, str)

    # 验证 payload 结构：使用短字段名 f/h/o/a
    raw = base64.urlsafe_b64decode(encoded + "==")
    data = json.loads(raw)
    assert "f" in data  # fingerprint
    assert "h" in data  # hostname
    assert "o" in data  # os
    assert "a" in data  # os_arch
    assert data["f"] == "a1b2c3d4e5f6"
    assert data["h"] == "MY-PC"
    assert data["o"] == "Windows 10"
    assert data["a"] == "x86_64"
