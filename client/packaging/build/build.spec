# -*- mode: python ; coding: utf-8 -*-
#
# AI Novel — PyInstaller build spec
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

# ── Analysis ──
a = Analysis(
    ['pywebview_app.py'],  # 与 build.spec 同目录
    pathex=[str(root_dir), str(backend_dir)],
    binaries=[],
    datas=[
        # 前端整份 dist：index.html + assets/ + env.js + public/*.svg
        # （只收 index.html + assets 会漏 env.js，index.html 用 <script src="./env.js"> 引用 → 冻结包 404）
        (str(frontend_dist), "frontend"),
        (str(backend_dir / "reference"), "reference"),
        # AI 提示词模板：prompts/*.prompt 是运行时数据（prompts/__init__.py 靠 __file__ 定位），
        # 不打包进 datas 则冻结包内 load_prompt() 抛 FileNotFoundError → 所有 AI 功能崩
        (str(backend_dir / "prompts"), "prompts"),
        # 发布期注入的 S端 地址（CI 构建时生成在 spec 同目录；本地开发无此文件则不打）。
        # 注意 datas 的目标段是「目录」语义——写成文件名会造出同名目录套娃，须落资源根 "."。
        *([(str(spec_dir / "release.json"), ".")] if (spec_dir / "release.json").exists() else []),
        # 品牌单源（brand-name-single-source）：brand.json 落资源根，backend/brand.py 运行时探测读取
        (str(root_dir / "brand" / "brand.json"), "."),
    ],
    hiddenimports=[
        'main', 'config', 'brand', 'db', 'ai_client',
        'aiosqlite', 'sqlalchemy.ext.asyncio',
        'anthropic', 'openai',
        'yaml', 'httpx', 'jose', 'multipart',
        'auth_local', 'auth_local.middleware', 'auth_local.models',
        'auth_local.router', 'auth_local.service',
        'settings', 'chapters', 'prompt', 'write', 'archive',
        'api_configs', 'genres', 'workflow', 'workflow.engine', 'workflow.gates', 'workflow.tier',
        'filesystem', 'filesystem.storage', 'filesystem.init', 'filesystem.composite_storage',
        'settings.render',
        'story', 'story.engine', 'story.character_agent', 'story.models',
        'threads', 'novels',
        'models', 'models.user', 'models.project', 'models.token_log', 'models.chapter', 'models.volume',
    ],
    hookspath=[str(spec_dir / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PIL', 'pandas', 'numpy', 'notebook', 'test', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── 可执行文件 ──
_exe_kwargs = dict(
    name='AI Novel',
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
)

if is_onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], **_exe_kwargs)
else:
    # onedir：EXE 只打包启动器，binaries/zipfiles/datas 由 COLLECT 收集。
    # （若 EXE 与 COLLECT 同时接收 a.binaries，macOS 构建会报
    #   “Resource 'dist/AI Novel' is not a valid file” —— 输出与收集循环引用。）
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_exe_kwargs)
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='AI Novel',
    )
    # macOS: 把 COLLECT 包成 .app（仅 darwin 且 onedir；Windows CI 走不到这里）
    if sys.platform == "darwin":
        app = BUNDLE(
            coll,
            name='AI Novel.app',
            icon=APP_ICON_ICNS,
            bundle_identifier='com.ainovel.desktop',
        )
