"""打包清单单源（c-nuitka-full）：双引擎（PyInstaller / Nuitka）共同消费的烘焙清单。

为什么抽出来：hiddenimports/datas 在 build.spec 里只能被 PyInstaller 消费，
build_nuitka.py 手抄第二份必然漂移——死条目就是现成教训（`filesystem.composite_storage`
与 `threads` 模块早已退役，PyInstaller 对缺失 hiddenimport 只告警，Nuitka 直接 FATAL，
spike 首轮即被逼出）。本文件是唯一清单，两引擎各自映射成自己的旗标；parity 由
tests/test_bundle_manifest.py 钉住（两引擎组装集合 ⊆ 单源）。

注意：本文件与 build.spec 同目录，被 PyInstaller 在 spec 执行期 import（spec 侧已把
本目录塞进 sys.path），也被 build_nuitka.py / 测试直接 import——保持零重依赖。
"""

from __future__ import annotations

# ── hiddenimports ────────────────────────────────────────────────
# PyInstaller 的静态分析看不到函数内懒导入；Nuitka 的 --include-module 全量显式列出
# 比依赖自动 follow 稳（spike 判例）。清单必须诚实：模块退役时同批从这里删除。
HIDDEN_IMPORTS: tuple[str, ...] = (
    "main", "config", "brand", "db", "ai_client",
    "aiosqlite", "sqlalchemy.ext.asyncio",
    "anthropic", "openai",
    "yaml", "httpx", "jose", "multipart",
    "auth_local", "auth_local.middleware", "auth_local.models",
    "auth_local.router", "auth_local.service",
    "settings", "chapters", "prompt", "write", "archive",
    # 提示词包（c-prompt-pack-hardening 阶段二）：container/localkey/sync 编译成原生
    # 扩展且被函数内懒导入——不显式列出则冻结包缺模块（运行期解密直接崩）
    "prompt_pack", "prompt_pack.container", "prompt_pack.localkey", "prompt_pack.sync",
    "api_configs", "genres", "workflow", "workflow.engine", "workflow.gates", "workflow.tier",
    "filesystem", "filesystem.storage", "filesystem.init",
    "settings.render",
    "story", "story.engine", "story.character_agent", "story.models",
    "novels",
    "models", "models.user", "models.project", "models.token_log", "models.chapter", "models.volume",
    "backup", "backup.router", "backup.export", "backup.format", "backup.importer",
    "job_runner",
    "manuscript", "manuscript.router", "manuscript.service", "manuscript.content", "manuscript.render",
)

# ── datas ────────────────────────────────────────────────────────
# (仓库根相对路径, 包内目标)。「frontend」必须整份 dist（index.html 用 <script
# src="./env.js"> 引用，只收 html+assets 会 404）；prompts 刻意不在清单——
# 提示词包硬切（c-prompt-pack-client）：模板走 CDN 加密包，「产物零 *.prompt」
# 由打包门禁断言钉住，勿以任何形式加回。
DATAS: tuple[tuple[str, str], ...] = (
    ("client/frontend/dist", "frontend"),
    ("client/backend/reference", "reference"),
    ("brand/brand.json", "."),  # 品牌单源：backend/brand.py 运行时探测读取
    ("LICENSE", "."),  # EULA/声明随包：PyInstaller≥6 落 _internal/（macOS 唯一通道；
    ("THIRD-PARTY-NOTICES.txt", "."),  # Windows 另由 installer.iss 显式落 {app} 根，双份冗余属预期）
)

# 发布期条件 datas：CI 构建时生成在 spec 同目录；本地开发无此文件则不打。
# 目标段落资源根 "."（datas 目标段是「目录」语义——写文件名会造同名目录套娃）。
CONDITIONAL_DATAS: tuple[tuple[str, str], ...] = (
    ("release.json", "."),  # spec_dir 相对；S端 地址族八键烘焙（installer-release spec）
)

# 引擎无关的排除名单（PyInstaller excludes / Nuitka --nofollow-import-to 同源映射）
EXCLUDED_IMPORTS: tuple[str, ...] = (
    "tkinter", "matplotlib", "PIL", "pandas", "numpy", "notebook", "test", "unittest",
)
