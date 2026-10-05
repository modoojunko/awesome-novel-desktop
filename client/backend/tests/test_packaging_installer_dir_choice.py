"""安装器门禁：安装位置必须由用户可配置，默认落在可写目录且目录名无空格。

背景（2026-10-05）：安装器默认 `{autopf}\\AI Novel`＝Program Files，而数据目录
跟随程序目录（便携式，`{app}\\data`）。标准用户对 Program Files 无写权限——
安装后那一次自动启动是管理员身份能写，之后从快捷方式启动就写不进库，后端静默
死在建目录那一步（界面只剩「正在启动…」，startup.log 一个字没有）。同时 Inno
`DisableDirPage` 默认 `auto` 会在升级时静默沿用旧目录，用户全程没有确认过位置。
同日用户拍板：目录名 `AI Novel` → `AwesomeNovel`（纯 ASCII 无空格——目录名会进
外部脚本/命令行/备份路径，空格与中文是常见坑），并把目录名与显示名解耦。

打包流水线只在推 tag 时跑（PR 不编译 .iss），此改动没有任何运行时测试会红，
故在此钉死不变量：位置页恒显示、默认不给 Program Files、路径 token（安装目录名/
程序本体名/构建产物名）纯 ASCII 无空格、data\\ 对用户可写。
"""

from __future__ import annotations

import re
from pathlib import Path

INSTALLER_ISS = (
    Path(__file__).resolve().parents[2] / "packaging" / "build" / "installer.iss"
)


def _active_lines(text: str) -> list[tuple[int, str]]:
    """去掉 Inno 注释行（`;` 起头）与空行，返回 (行号, 内容) 的活跃指令行。"""
    lines = []
    for no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(";"):
            continue
        lines.append((no, stripped))
    return lines


def _active_value(text: str, key: str) -> str:
    for _no, line in _active_lines(text):
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"installer.iss 缺活跃指令 {key}=")


def _define(text: str, name: str) -> str:
    m = re.search(rf'^#define {name} "([^"]*)"', text, re.MULTILINE)
    assert m, f"installer.iss 缺 #define {name}"
    return m.group(1)


def test_installer_iss_exists():
    assert INSTALLER_ISS.is_file(), f"找不到安装脚本：{INSTALLER_ISS}"


def test_dir_page_always_shown():
    """安装位置页恒显示：默认 auto 会在升级时静默沿用旧目录，用户无从确认。"""
    assert _active_value(INSTALLER_ISS.read_text(encoding="utf-8"), "DisableDirPage") == "no"


def test_upgrade_prefills_previous_dir():
    """升级预填上一次安装目录（用户可改，但直接下一步＝原地升级、data\\ 不动）。"""
    value = _active_value(INSTALLER_ISS.read_text(encoding="utf-8"), "UsePreviousAppDir")
    assert value == "yes", "升级页必须预填旧目录，否则老用户下一步就把数据落到新目录"


def test_default_dir_is_user_writable():
    """默认安装目录必须是用户可写位置——数据跟随程序目录，Program Files 会写不进去。"""
    default_dir = _active_value(INSTALLER_ISS.read_text(encoding="utf-8"), "DefaultDirName")
    assert "{autopf}" not in default_dir, "默认目录回到 Program Files 了（标准用户写不进 data\\）"
    assert "Program Files" not in default_dir
    assert "{localappdata}" in default_dir, "默认目录必须落在用户可写的 per-user 位置"


def test_dir_name_is_plain_ascii_without_spaces():
    """目录名走独立 define 且纯 ASCII 无空格（2026-10-05 拍板：AI Novel → AwesomeNovel）。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    default_dir = _active_value(text, "DefaultDirName")
    assert default_dir.endswith("{#MyAppDirName}"), "DefaultDirName 必须用目录名 define（与显示名解耦）"

    dir_name = _define(text, "MyAppDirName")
    assert dir_name, "安装目录名不得为空"
    assert dir_name.isascii(), f"安装目录名必须纯 ASCII：{dir_name!r}"
    assert " " not in dir_name, f"安装目录名不得含空格：{dir_name!r}"


def test_executable_name_is_plain_ascii_without_spaces():
    """程序本体名同为路径 token：纯 ASCII 无空格（旧值 `AI Novel.exe` 带空格）。"""
    exe_name = _define(INSTALLER_ISS.read_text(encoding="utf-8"), "MyAppExeName")
    assert exe_name.isascii() and " " not in exe_name, f"程序本体名必须纯 ASCII 无空格：{exe_name!r}"


def test_build_spec_output_names_are_plain_ascii():
    """PyInstaller 产物名（exe / dist 目录 / .app）同为路径 token，不得含空格。"""
    spec = (INSTALLER_ISS.parent / "build.spec").read_text(encoding="utf-8")
    names = re.findall(r"name='([^']+)'", spec)
    assert names, "build.spec 缺 name= 命名"
    for name in names:
        base = name.removesuffix(".app")
        assert base.isascii() and " " not in base, f"构建产物名必须纯 ASCII 无空格：{name!r}"


def test_data_dir_granted_users_modify():
    """{app}\\data 必须显式授「用户可写」ACL：兜住用户自选受限目录的情形。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    entries = [
        line for _no, line in _active_lines(text)
        if line.startswith("Name:") and "{app}\\data" in line
    ]
    assert entries, "installer.iss 缺 {app}\\data 的 [Dirs] 条目"
    assert any("Permissions:" in line for line in entries), (
        "该条目必须带 Permissions:（users-modify），否则受限目录下标准用户写不进库"
    )
    assert any("users-modify" in line for line in entries)


def test_artifact_names_use_new_brand():
    """安装包文件名 AwesomeNovel_*（2026-10-05 更名「AI Novel 都换掉」）。

    旧名 AI_Novel_* 只允许出现在流水线的过渡期兼容副本里（见下一例），
    构建链（安装器/macOS 脚本/本地发版脚本）不得再产出旧名。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    base = _active_value(text, "OutputBaseFilename")
    assert base.startswith("AwesomeNovel_Setup_v"), base
    assert "AI_Novel" not in base

    mac = (INSTALLER_ISS.parent / "build_mac.sh").read_text(encoding="utf-8")
    assert "AwesomeNovel_mac_$APP_VERSION.dmg" in mac and "AI_Novel_mac_" not in mac

    ps1 = (INSTALLER_ISS.parent / "build_release.ps1").read_text(encoding="utf-8")
    assert "AwesomeNovel_Setup_*.exe" in ps1 and "AI_Novel_Setup_" not in ps1


def test_release_pipeline_ships_legacy_named_copies():
    """过渡期不变量：流水线必须同发旧名副本＋校验其可达。

    线上落地页/存量消费方仍按 download/v<VER>/AI_Novel_* 拼直链，改名那一刻
    若不发副本＝用户下载 404。S端 切新名后的下个版本可移除，届时本测试同批更新。"""
    repo_root = INSTALLER_ISS.parents[3]  # client/packaging/build/installer.iss → 仓库根
    wf_path = repo_root / ".github" / "workflows" / "client-package.yml"
    wf = wf_path.read_text(encoding="utf-8")
    assert "AwesomeNovel_Setup_*.exe" in wf, "主产物 glob 必须是新名"
    assert "AwesomeNovel_Setup_v{ver}.exe" in wf, "notes.html 直链必须是新名"
    assert "artifacts/legacy/AI_Novel_Setup_v$VER.exe" in wf, "过渡期必须同发旧名副本（Release 资产）"
    assert "artifacts/legacy/AI_Novel_mac_v$VER.dmg" in wf, "过渡期必须同发旧名副本（macOS）"
    assert "download/v$VER/$LEGACY_EXE" in wf, "旧名副本必须上传静态托管"
    assert 'check "https://www.awesomenovel.com/download/v$VER/$LEGACY_EXE"' in wf, (
        "旧名副本必须进发布校验（否则线上 404 无人发现）"
    )


def test_dir_page_tells_user_where_books_live():
    """位置页须对用户讲明「安装目录＝书稿数据落点」（2026-10-06 评审整改）。

    位置页恒显示后，升级用户手改目录会把 data\\ 留在旧处而页面零提示——观感即
    「书没了」。两条不变量：标准句原样保留（别把 Next/Browse 指引吞掉）＋点名 data。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    originals = {
        "chinesesimplified": "安装程序将安装 [name] 到下面的文件夹中。",
        "english": "Setup will install [name] into the following folder.",
    }
    for lang, original in originals.items():
        line = next(
            (ln for ln in text.splitlines() if ln.startswith(f"{lang}.SelectDirLabel3=")),
            None,
        )
        assert line, f"缺 {lang}.SelectDirLabel3 覆盖——位置页少了数据目录提示"
        message = line.split("=", 1)[1]
        assert message.startswith(original), f"{lang} 标准句被改动（须原样保留再追加提示）"
        assert "data" in message, f"{lang} 提示必须点名 data 子目录"
