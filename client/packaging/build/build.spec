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

# ═══ 可配置：Windows 版本资源（exe 文件属性/任务管理器里的「发布者」「公司」）═══
# 不烘版本资源时 Windows 对 exe 一律显示「发布者: 未知」。发布者 = 版权人 = 经营主体，
# 字段全部取自 brand/brand.json（与两端前端同源，唯一声明处，勿在此写死）。
# 版本口径与 build.bat / CI 安装包同源：环境变量 APP_VERSION > git describe > 0.0.0
# （CI 在 Build app 步骤注入 github.ref_name；本地 build.bat 已 set 同名变量）。
# version_info.txt 是构建产物（.gitignore 已排除），仅 Windows 生成并使用，
# macOS 构建不生成文件但同样过字段门禁（为 mac 侧将来补主体元数据预留）。
_brand = json.loads((root_dir / "brand" / "brand.json").read_text(encoding="utf-8"))


def _brand_field(key: str) -> str:
    """品牌源字段门禁：缺键/非串/空白串一律显式失败，不静默出「未知发布者」的包。"""
    v = _brand.get(key)
    if not isinstance(v, str) or not v.strip():
        raise SystemExit(
            f"brand/brand.json 缺有效字符串字段 {key}（经营主体/品牌署名需要）——补齐后再构建"
        )
    return v.strip()


APP_PUBLISHER = _brand_field("company")
APP_BRAND_NAME = _brand_field("name")
APP_BRAND_NAME_EN = _brand_field("nameEn")


def _detect_version() -> str:
    v = os.environ.get('APP_VERSION', '').strip()
    if not v:
        try:
            r = subprocess.run(
                ['git', 'describe', '--tags', '--always', '--dirty'],
                capture_output=True, text=True, cwd=str(root_dir))
            v = r.stdout.strip() if r.returncode == 0 else ''
        except OSError:
            v = ''
    v = v[1:] if v.startswith('v') else v  # tag 去 v 前缀
    # 清洗进字符串字段（提交哈希/斜杠等不进元数据），数字位由 findall 另取
    return re.sub(r'[^A-Za-z0-9.+_-]', '-', v) or '0.0.0'


_version_file = None
if sys.platform == 'win32':
    _ver = _detect_version()
    # 数字版本位只取首个点分数字前缀（四段各为 16 位 WORD）：
    # describe 尾巴（提交哈希/PR 号等）不进数字位，超段 clamp 0–65535
    _prefix = re.match(r'\d+(?:\.\d+)*', _ver)
    _segs = [min(int(seg), 65535) for seg in (_prefix.group(0).split('.') if _prefix else [])]
    _nums = (_segs + [0, 0, 0, 0])[:4]
    _file_desc = f'{APP_BRAND_NAME} ({APP_BRAND_NAME_EN})'
    _copyright = f'© {APP_PUBLISHER}'
    _version_file = spec_dir / 'version_info.txt'
    # 模板用 !r 生成合法字面量——值含引号/反斜杠也不炸加载器 eval，勿改回裸插值
    _version_file.write_text(f"""# -*- coding: utf-8 -*-
# 由 build.spec 自动生成——勿手改、勿提交
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple(_nums)},
    prodvers={tuple(_nums)},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0, 0, 0)),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', {APP_PUBLISHER!r}),
         StringStruct('FileDescription', {_file_desc!r}),
         StringStruct('FileVersion', {_ver!r}),
         StringStruct('InternalName', 'AwesomeNovel'),
         StringStruct('LegalCopyright', {_copyright!r}),
         StringStruct('OriginalFilename', 'AwesomeNovel.exe'),
         StringStruct('ProductName', {APP_BRAND_NAME!r}),
         StringStruct('ProductVersion', {_ver!r})])
      ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""", encoding='utf-8')

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
        # AI 提示词模板**不再随包**（c-prompt-pack-client 硬切，2026-10-05 拍板）：
        # 装完登录后按权益从 CDN 拉加密包装本地（prompt_pack/sync.py），loader 缺包时
        # 抛 PromptPackMissing → 503 {reason: prompts_missing} → 四态卡引导。
        # 回归由 client-package.yml / build_release.ps1 的「产物零 *.prompt」断言钉住。
        # 发布期注入的 S端 地址（CI 构建时生成在 spec 同目录；本地开发无此文件则不打）。
        # 注意 datas 的目标段是「目录」语义——写成文件名会造出同名目录套娃，须落资源根 "."。
        *([(str(spec_dir / "release.json"), ".")] if (spec_dir / "release.json").exists() else []),
        # 品牌单源（brand-name-single-source）：brand.json 落资源根，backend/brand.py 运行时探测读取
        (str(root_dir / "brand" / "brand.json"), "."),
        # EULA 与第三方开源声明随包（relicense-proprietary）：PyInstaller ≥6 落 _internal/
        # （macOS 唯一通道；Windows 另由 installer.iss [Files] 显式落 {app} 根，双份属预期冗余）
        (str(root_dir / "LICENSE"), "."),
        (str(root_dir / "THIRD-PARTY-NOTICES.txt"), "."),
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
        'backup', 'backup.router', 'backup.export', 'backup.format', 'backup.importer',
        'job_runner',
        'manuscript', 'manuscript.router', 'manuscript.service', 'manuscript.content', 'manuscript.render',
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
