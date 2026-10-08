# -*- mode: python ; coding: utf-8 -*-
#
# Awesome Novel — PyInstaller build spec
#
# 两种模式:
#   onefile: 单 exe（启动慢，开发测试用）
#   onedir:  文件夹（启动快，正式分发用）
#
# 用法:
#   pyinstaller build.spec                   → 默认 onedir
#   pyinstaller build.spec --onedir          → onedir（同默认）
#   pyinstaller build.spec --onedir /onefile → 切换模式
#   build.bat                                → 一键构建 + Inno Setup 安装包

import sys
import os
import json
import re
import subprocess
from pathlib import Path

block_cipher = None

# ── 路径 ──
spec_dir = Path(SPEC).parent if 'SPEC' in dir() else Path.cwd()
root_dir = spec_dir.parent.parent.parent   # build/ -> packaging/ -> client/ -> project root
frontend_dist = root_dir / "client" / "frontend" / "dist"
backend_dir = root_dir / "client" / "backend"

# ── 模式：onedir（默认）或 onefile ──
is_onefile = "--onefile" in sys.argv
mode_name = "onefile" if is_onefile else "onedir"
print(f"Building in {mode_name} mode")

# ═══ 可配置：应用图标 ═══
# 换图标 = 替换 client/packaging/build/ 下对应文件（或用 make_icns.sh 从源重生成）：
#   icon.ico  → Windows 应用 + Inno Setup 安装器共用
#   icon.icns → macOS Dock / .app 图标
# 若改名，只需同步改这里两个变量。
APP_ICON_ICO = 'icon.ico'
APP_ICON_ICNS = 'icon.icns'
APP_ICON = APP_ICON_ICNS if sys.platform == "darwin" else APP_ICON_ICO

# ═══ Windows 版本资源（exe 文件属性/任务管理器里的「发布者」「公司」）═══
# 生成逻辑抽为共享模块（c-nuitka-full）：build.bat 的 Nuitka 分支／build_nuitka
# 也走同一生成器，字段门禁与版本口径单点维护——勿在此文件内联第二份。
import win_version_info as _wvi

_version_file = _wvi.write_version_file(spec_dir=spec_dir, root_dir=root_dir)

# ── Analysis ──
# 烘焙清单单源（c-nuitka-full）：datas/hiddenimports/excludes 与 Nuitka 引擎共用
# bundle_manifest.py，分叉即失真——勿在此文件内联手抄清单。
import sys as _sys

_sys.path.insert(0, str(spec_dir))
import bundle_manifest as _manifest

a = Analysis(
    ['pywebview_app.py'],  # 与 build.spec 同目录
    pathex=[str(root_dir), str(backend_dir)],
    binaries=[],
    datas=[
        # AI 提示词模板**不再随包**（c-prompt-pack-client 硬切，2026-10-05 拍板）：
        # 装完登录后按权益从 CDN 拉加密包装本地（prompt_pack/sync.py），loader 缺包时
        # 抛 PromptPackMissing → 503 {reason: prompts_missing} → 四态卡引导。
        # 回归由 client-package.yml / build_release.ps1 的「产物零 *.prompt」断言钉住。
        *[(str(root_dir / src), dest) for src, dest in _manifest.DATAS],
        # 发布期注入的 S端 地址（CI 构建时生成在 spec 同目录；本地开发无此文件则不打）。
        # 注意 datas 的目标段是「目录」语义——写成文件名会造出同名目录套娃，须落资源根 "."。
        *[(str(spec_dir / src), dest)
          for src, dest in _manifest.CONDITIONAL_DATAS
          if (spec_dir / src).exists()],
    ],
    hiddenimports=list(_manifest.HIDDEN_IMPORTS),
    hookspath=[str(spec_dir / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=list(_manifest.EXCLUDED_IMPORTS),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── 可执行文件 ──
_exe_kwargs = dict(
    name='AwesomeNovel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=APP_ICON,
    # Windows 版本资源（发布者等元数据）；非 Windows 平台 _version_file 为 None 不传
    **({'version': str(_version_file)} if _version_file else {}),
)

if is_onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], **_exe_kwargs)
else:
    # onedir：EXE 只打包启动器，binaries/zipfiles/datas 由 COLLECT 收集。
    # （若 EXE 与 COLLECT 同时接收 a.binaries，macOS 构建会报
    #   “Resource 'dist/AwesomeNovel' is not a valid file” —— 输出与收集循环引用。）
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_exe_kwargs)
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='AwesomeNovel',
    )
    # macOS: 把 COLLECT 包成 .app（仅 darwin 且 onedir；Windows CI 走不到这里）
    if sys.platform == "darwin":
        app = BUNDLE(
            coll,
            name='AwesomeNovel.app',
            icon=APP_ICON_ICNS,
            bundle_identifier='com.ainovel.desktop',
        )
