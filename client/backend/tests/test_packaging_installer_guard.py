"""安装器门禁：installer.iss 不得对 Inno 卸载器本体（unins000.*）动刀。

v0.26 卸载事故：旧版在 [Run] 里 `rename unins000.exe uninstall.exe`，但 Inno 卸载器
按「自身文件名」推导数据文件（uninstall.exe 会去找 uninstall.dat），且安装期写死的
注册表卸载项 UninstallString 固定指向 unins000.exe——只改 exe 使「设置 → 应用」与
安装目录内双击两条卸载路径同时失效（报「uninstall.dat 不存在，无法卸载」）。

为什么必须用静态门禁兜：打包流水线只在推 tag 时跑（PR 不编译 .iss，2026-10-02 省额度
拍板），改名与否没有任何运行时测试会红。故在此钉死：活跃指令行（去注释）中出现
unins000 即视为重命名/挪动卸载器，直接转红。
"""

from __future__ import annotations

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


def test_installer_iss_exists():
    assert INSTALLER_ISS.is_file(), f"找不到安装脚本：{INSTALLER_ISS}"


def test_no_active_directive_touches_inno_uninstaller():
    """活跃行不得引用 unins000：Inno 未提供卸载器改名机制，动了就是 v0.26 事故重演。"""
    offenders = [
        (no, line)
        for no, line in _active_lines(INSTALLER_ISS.read_text(encoding="utf-8"))
        if "unins000" in line.lower()
    ]
    assert not offenders, (
        "installer.iss 的活跃指令引用了 Inno 卸载器本体 unins000（重命名/移动它会让"
        "「设置 → 应用」与目录内双击两条卸载路径同时失效，v0.26 事故复现）：\n"
        + "\n".join(f"  L{no}: {line}" for no, line in offenders)
    )


def test_legacy_renamed_pair_is_cleaned_on_install():
    """升级安装须清掉 ≤v0.26 留下的残缺改名件，否则用户会继续点到报错的那个 exe。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    for name in ("uninstall.exe", "uninstall.dat"):
        assert f'Name: "{{app}}\\{name}"' in text, (
            f"[InstallDelete] 缺 {name} 清理项——旧版改名残件会留在安装目录里"
        )
