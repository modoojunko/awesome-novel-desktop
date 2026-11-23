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


def test_release_pipeline_ships_only_new_artifact_names():
    """产物命名唯一口径：流水线只发布 AwesomeNovel_*，不留旧名过渡副本。

    2026-10-06 用户拍板「没有过渡期的产物直接改名」——旧名 AI_Novel_* 不得再出现在
    Release 资产 / 静态托管上传 / 发布校验里（.iss 里对旧程序名 `AI Novel.exe` 与旧
    运行目录的清理引用是历史残留处理，不在此列）。"""
    repo_root = INSTALLER_ISS.parents[3]  # client/packaging/build/installer.iss → 仓库根
    wf_path = repo_root / ".github" / "workflows" / "client-package.yml"
    wf = wf_path.read_text(encoding="utf-8")
    assert "AwesomeNovel_Setup_*.exe" in wf, "主产物 glob 必须是新名"
    assert "AwesomeNovel_Setup_v{ver}.exe" in wf, "notes.html 直链必须是新名"
    assert "AI_Novel_Setup_" not in wf and "AI_Novel_mac_" not in wf, (
        "流水线不得再产出/校验旧名副本（用户拍板直接改名）；"
        "S端 落地页等线上消费方须同批切到 AwesomeNovel_*"
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


# ── c-update-fail-safe §4：安装目录连续性＋快捷方式 ─────────────────────────


def test_desktop_icon_uses_autodesktop():
    """桌面图标走 {autodesktop}：/CURRENTUSER 静默更新下写不了公用桌面（死图标根因）。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    icons = [line for _no, line in _active_lines(text) if line.startswith("Name:") and ".lnk" not in line]
    desktop = [line for line in icons if "desktopicon" in line]
    assert desktop, "缺桌面快捷方式条目"
    assert any("{autodesktop}" in line for line in desktop), "桌面图标必须用 {autodesktop}"
    assert not any("{commondesktop}" in line for line in desktop), (
        "不得再用 {commondesktop}——自动更新 /CURRENTUSER 时不可写，会留下指向旧目录的死图标"
    )


def test_install_dir_pointer_and_registry_prefill_in_code():
    """[Code] 目录预填链：指针文件 → 双 hive（含 32 位视图）→ 覆盖 DirEdit；/DIR 优先。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    assert "install_dir.txt" in text, "必须读应用写的安装目录指针"
    assert "Inno Setup: App Path" in text and "InstallLocation" in text
    for root in ("HKEY_CURRENT_USER_64", "HKEY_CURRENT_USER_32",
                 "HKEY_LOCAL_MACHINE_64", "HKEY_LOCAL_MACHINE_32"):
        assert root in text, f"缺 {root} 视图（跨安装模式看不到旧目录的根因）"
    assert "WizardForm.DirEdit.Text" in text
    assert "ExpandConstant('{param:DIR|}')" in text, "/DIR 显式给出时必须优先"
    assert "procedure InitializeWizard;" in text
    assert "procedure CurPageChanged" in text


def test_shortcut_target_fixed_for_existing_link_only():
    """ssPostInstall 只修已存在的用户桌面 .lnk（尊重用户取消勾选），不强行创建。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    assert "procedure CurStepChanged" in text and "ssPostInstall" in text
    assert "WScript.Shell" in text and "TargetPath" in text
    assert "if FileExists(Lnk)" in text, "只修复已存在的快捷方式"


def test_install_dir_prefill_is_one_shot():
    """位置页只「首次进入」应用解析结果：用户手改目录后返回该页不得被再次覆盖（review P3）。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    assert "InstallDirPrefilled" in text, "缺一次性标志——每次回到位置页都会覆盖用户手选目录"
    assert "if MarkDone and InstallDirPrefilled then exit;" in text
    assert "ApplyInstallDir(True)" in text, "CurPageChanged 的页面级应用必须记账"
    assert "ApplyInstallDir(False)" in text, "InitializeWizard 预填不记账（Inno 页面激活会再写）"


def test_global_var_declared_before_routines_in_code():
    """[Code] 全局 var 必须声明在首个函数/过程之前（Pascal 块结构；iscc 编译要求，review P2）。

    段头按行锚定切（`^[Code]$`）——注释里出现过「[Code]」字样，按子串 split 会从
    注释处裹头假绿（判例：delta 提取器须以 section 头为边界）。
    """
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^\[Code\]\s*$", text)
    assert len(sections) >= 2, "installer.iss 缺行首 [Code] 段头"
    code = sections[-1]
    var_at = code.find("InstallDirPrefilled: Boolean;")
    assert var_at != -1, "缺 InstallDirPrefilled 声明"
    first_routine = min(
        i for i in (code.find("function "), code.find("procedure ")) if i != -1
    )
    assert var_at < first_routine, "全局 var 必须先于首个函数/过程（否则 iscc 可能编译失败）"
