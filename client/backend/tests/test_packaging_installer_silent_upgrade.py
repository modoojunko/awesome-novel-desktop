"""安装器门禁：静默升级承重柱两条（silent-upgrade-lab 实验分支，2026-10-13）。

背景：自动升级要求安装器能被命令行以 **per-user 静默**形态覆盖安装（免 UAC），
并在装完后**自动拉起**新版 GUI。承重柱与形态细节的判例全部记在
installer.iss 注释与设计草案 §4.3/§4.4（评审 P1：裸 /AUTOLAUNCH 判不中、
skipifsilent 让静默链恒跳过、runhidden 起 GUI 未证）。打包链 PR 不编译 .iss
（省额度拍板 2026-10-02），与目录选择门禁同理由——用文本钉兜住。
"""

from __future__ import annotations

from pathlib import Path

INSTALLER_ISS = (
    Path(__file__).resolve().parents[2] / "packaging" / "build" / "installer.iss"
)


def _text() -> str:
    return INSTALLER_ISS.read_text(encoding="utf-8")


def _active_lines(text: str) -> list[str]:
    return [
        raw.strip()
        for raw in text.splitlines()
        if raw.strip() and not raw.strip().startswith(";")
    ]


def test_privileges_override_allows_commandline():
    """免 UAC 静默链的开关：缺这行，/CURRENTUSER 无效、自动升级必弹框。"""
    lines = _active_lines(_text())
    assert "PrivilegesRequiredOverridesAllowed=commandline" in lines, (
        "缺 PrivilegesRequiredOverridesAllowed=commandline——更新器传 /CURRENTUSER 会被忽略"
    )
    # 缺省权限级别仍是 admin：手动安装路径（HKLM 卸载项/公用桌面/ACL）不得被顺手改掉
    assert any(line == "PrivilegesRequired=admin" for line in lines), (
        "PrivilegesRequired 必须仍为 admin（手动链缺省行为不变）"
    )


def test_autolaunch_entry_shape():
    """/AUTOLAUNCH=1 自动拉起条的形状钉：Check 判参数、不带两个致命 flag。"""
    lines = _active_lines(_text())
    entry = [ln for ln in lines if ln.startswith("Filename:") and "AutoLaunchRequested" in ln]
    assert len(entry) == 1, f"自动拉起条目应恰一条，实得 {entry!r}"
    line = entry[0]
    assert "Check: AutoLaunchRequested" in line, "必须经 Check 判命令行参数（手动安装零触发）"
    assert "skipifsilent" not in line, (
        "静默链里 skipifsilent＝恒跳过，自动拉起会成死键（评审 P1 判例）"
    )
    assert "runhidden" not in line, "runhidden 以 SW_HIDE 起 GUI，窗口可见性未证（评审 P1）"
    assert "postinstall" in line and "nowait" in line, (
        "postinstall（原始用户令牌起 GUI）＋nowait（不拦安装器收尾）缺一不可"
    )
    assert "Description:" not in line, (
        "不带 Description——手动向导不多显勾选项，条目只在带参数时静默生效"
    )


def test_autolaunch_param_form_is_value_flag():
    """判据函数必须比对带值形态 '1'（裸 flag 落官方 {param:} 的空值分支，判不中）。"""
    text = _text()
    assert "function AutoLaunchRequested: Boolean;" in text
    assert "ExpandConstant('{param:AUTOLAUNCH|}') = '1'" in text, (
        "判据必须是 {param:AUTOLAUNCH|} 与 '1' 的精确比较（形态 V-3 真机钉死）"
    )


def test_package_workflow_cleans_smoke_residue_before_iscc():
    """打包卫生钉（10-14 真机实验实锤）：Windows iscc 前必须有「清冒烟残留」步骤。

    --smoke 在 onedir 目录内就地写 startup.log/logs/port.json/data\\novel-dev.db，
    [Files] 整目录收会把构建机残留烧进安装包（升级覆盖用户哨兵库／新用户首启带脏数据）。
    步骤必须排在 Build Windows installer **之前**，且带清不干净即 throw 的自断言。
    """
    repo_root = INSTALLER_ISS.parents[3]
    wf = (repo_root / ".github" / "workflows" / "client-package.yml").read_text(encoding="utf-8")
    clean_at = wf.find("Clean smoke residue before packaging (Windows)")
    build_at = wf.find("Build Windows installer")
    assert clean_at != -1, "缺 iscc 前的冒烟残留清理步骤（打包卫生闸）"
    assert build_at != -1 and clean_at < build_at, "清理步骤必须排在打安装包之前"
    assert 'Remove-Item -Recurse -Force "$APP\\logs","$APP\\data"' in wf
    assert "冒烟残留未清干净" in wf, "清理后必须自断言，未净即红"
    assert "[InstallDelete]" in (INSTALLER_ISS.read_text(encoding="utf-8"))  # 不变式在场
