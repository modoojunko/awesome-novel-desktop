# client/packaging/pywebview_app.py
"""Awesome Novel 桌面应用入口 — pywebview 壳"""

import json
import os
import random
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

# 模块级导入：NativeBridge 方法内引用 webview 常量，函数级导入会让 F821 误判未定义；
# import 本身不初始化 GUI（start() 才会），--smoke 路径同样安全
import webview


def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    # Dev 模式: pywebview_app.py 在 client/packaging/build/ → 项目根目录
    return Path(__file__).parent.parent.parent


APP_DIR_NAME = "AwesomeNovel"
LEGACY_APP_DIR_NAME = "AI Novel"

# 提示词包验签公钥的生产默认（c-prompt-pack-delivery）：这是**公钥**，就该随包分发——
# 发布构建经 release.json 的 pack_pubkeys（vars.CLIENT_PACK_PUBKEYS 可覆盖，用于轮换）
# 注入 CLIENT_PACK_PUBKEYS env；本地直接打包（无 release.json 烘焙）也据此有钥可验。
# 签名私钥只在发布方离线保管，永不入仓/入产物。
PROD_PACK_PUBKEYS = '{"pack-k1":"UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM="}'

# 运行时可调参数与「装载挂死自愈」（shell-render-resilience）
SHELL_CONFIG_NAME = "shell.json"          # <运行目录>/shell.json，可选的人工调参文件（见 get_runtime_dir）
RENDER_HANG_MARKER = "render-hang.flag"   # 存在＝上次装载挂死过 → 从此固定走安全模式
RELAUNCH_ENV_KEY = "AI_NOVEL_SHELL_RELAUNCHED"  # 父进程注入给孩子：本进程＝重启代（最多重启一轮）
SAFE_MODE_ARGS = "--disable-gpu"          # 安全模式追加的 WebView2 参数（VM/无 GPU 渲染挂死常见解）
DEFAULT_BACKEND_TIMEOUT = 180             # 后端就绪等待（秒）。2026-10-06 现场：首次冷启动
                                          # 被杀软首扫 + 慢盘拖到 >60s 被判死（第二次才进来）
DEFAULT_APP_LOAD_TIMEOUT = 60             # 应用页装载看门狗（秒）
RUNTIME_PROBE_NAME = ".awesome-novel-write-probe"  # 安装目录可写性探针（写完即删）


def _appdata_base() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("APPDATA", "."))


def _migrate_legacy_appdata(base: Path) -> Path:
    """旧名目录 AI Novel → AwesomeNovel（一次性换名；失败不阻断、绝不丢数据）。

    macOS 上这个目录就是书稿数据目录（get_install_dir 冻结态直接取它），所以
    改名必须无痛：同卷 os.rename 原子换名，并在旧路径留一个指向新目录的符号
    链接——「装回旧版本」的用户照旧能找到自己的书。改名失败（被占用/权限不足）
    就继续用旧目录：名字可以晚点再换，书不能看不见。"""
    new = base / APP_DIR_NAME
    old = base / LEGACY_APP_DIR_NAME
    if not old.exists() or new.exists():
        return new
    try:
        old.rename(new)
    except OSError:
        return old
    try:
        old.symlink_to(new, target_is_directory=True)
    except OSError:
        pass  # 只是回滚兼容的便利，建不出来不影响本次启动
    return new


def get_appdata() -> Path:
    r"""用户级目录 — 跨平台；macOS 上它同时是书稿数据目录。
    Windows: %APPDATA%\AwesomeNovel；macOS: ~/Library/Application Support/AwesomeNovel。
    旧名 AI Novel 目录（≤v0.27 品牌）在 macOS 首启自动换名并在旧路径留软链；
    Windows 侧旧目录只剩历史日志，不迁移（卸载器两个都清）。

    Windows 安装版上它自 shell-runtime-dir 起只是**运行时文件的兜底**：
    安装目录可写时运行目录＝安装目录（与 data\ 在一起），写不了才落这里。"""
    base = _appdata_base()
    if sys.platform == "darwin":
        return _migrate_legacy_appdata(base)
    return base / APP_DIR_NAME


def get_install_dir() -> Path:
    """数据目录（DATA_ROOT）。Windows 便携式：exe 同目录；macOS：不写进 .app bundle，
    数据放 Application Support（与运行时目录一致）。"""
    if getattr(sys, 'frozen', False):
        if sys.platform == "darwin":
            return get_appdata()
        return Path(sys.executable).parent
    # Dev 模式: 项目根目录
    return Path(__file__).parent.parent.parent


def _install_dir_writable(install_dir: Path) -> bool:
    """安装目录可写探测：写一个探针文件再删（判据＝真的写得进去，不是权限位猜的）。"""
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        probe = install_dir / RUNTIME_PROBE_NAME
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def get_runtime_dir() -> Path:
    r"""壳层运行时文件（日志/端口/错误页/挂死标记/调参）的落点（shell-runtime-dir）。

    Windows 安装版：安装目录写得进去就用安装目录——用户找得到（和 data\ 在一起），
    也从「翻 %APPDATA%」这件事里解放出来；写不进去（典型：装到 C:\Program Files
    且标准用户运行）回落 %APPDATA%\AwesomeNovel——诊断文件必须永远写得出来，
    这是壳层启动链的底线（写不出日志＝下次排查从零开始）。

    macOS / dev：等同 get_appdata()（macOS 上该目录同时是数据目录；dev 不往仓库里写）。"""
    appdata = get_appdata()
    if sys.platform == "darwin" or not getattr(sys, "frozen", False):
        return appdata
    install_dir = get_install_dir()
    if _install_dir_writable(install_dir):
        return install_dir
    return appdata


def _legacy_runtime_dir(runtime_dir: Path) -> Path | None:
    """运行目录落在安装目录时，返回 %APPDATA% 旧位置作兼容读取源；同目录/异常＝None。

    v0.28.1 的 shell.json 指引写的是 %APPDATA%（当时运行目录只在那儿）；升到本版后
    用户按旧指引放的文件不该被静默忽略——只读兼容，不写回。"""
    try:
        appdata = get_appdata()
    except Exception:
        return None
    return None if appdata == runtime_dir else appdata


def get_resource_root() -> Path:
    """打包内前端 dist 与 reference 模板所在目录。
    onedir(Windows): _MEIPASS=_internal；.app(macOS): Contents/Frameworks(_MEIPASS)
    或 Contents/Resources(PyInstaller 把 datas 放这里，按实际布局探测)。"""
    base = get_base_dir()
    candidates = [base, base.parent / "Resources"]
    for cand in candidates:
        if (cand / "frontend").exists() and (cand / "reference").exists():
            return cand
    return base


def _load_brand():
    """品牌桥接入（brand-name-single-source）：单源是 backend/brand.py。
    壳与后端的 sys.path 布局不同，这里自行引导；import 或取值任何异常都
    回落字面量默认——窗口创建路径上零新增可炸点（v0.15 教训）。"""
    try:
        backend_dir = get_base_dir() / "backend"
        if not backend_dir.exists():
            # Dev: 本文件在 client/packaging/build/ → backend 在 client/backend/
            backend_dir = Path(__file__).resolve().parents[2] / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        import brand

        return brand
    except Exception:
        class _BrandFallback:
            BRAND_NAME = "爱小说"
            BRAND_NAME_EN = "Awesome Novel"
            BRAND_MARK = "爱"
            BRAND_TAGLINE = "AI 辅助长篇小说写作"

        return _BrandFallback


def window_title() -> str:
    """系统窗口标题 = 品牌名（与产品名一致，替代历史「AI Novel」）。"""
    try:
        return _load_brand().BRAND_NAME
    except Exception:
        return "爱小说"


# ── 启动日志与失败兜底（shell-startup-diagnostics）─────────────────────────
# 现场形态：GUI 包「长期停在启动页」的报告，旧壳有两条静默失败路径——
# ① server 线程死在早段（try 之外）② 轮询线程异常。两者都零日志零提示，
# 只能靠猜。现在每一步都落 startup.log，且写日志永远不依赖 UI 线程
# （窗口挂死时仍要能写盘、能开浏览器兜底）。


def log_line(appdata: Path, message: str) -> None:
    """把一行带时间戳的启动日志追加到 <运行目录>/startup.log（运行目录见 get_runtime_dir）。

    运行目录不可写时退到系统临时目录（极端：安装目录与 %APPDATA% 都写不进去），
    再失败则静默——日志本身绝不能把启动打崩。"""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for target in (appdata, Path(tempfile.gettempdir()) / APP_DIR_NAME):
        try:
            target.mkdir(parents=True, exist_ok=True)
            with open(target / "startup.log", "a", encoding="utf-8") as f:
                f.write(f"[{stamp}] {message}\n")
            return
        except Exception:
            continue


# ── 可调参数（shell.json）与「装载挂死自愈」（shell-render-resilience）──────
# 现场（2026-10-06 测试机 startup.log）：窗口活着、后端就绪、导航已发出，但 60 秒内
# WebView2 连 NavigationCompleted 都没发生（pywebview 的 loaded 事件不判导航成败——
# 连接被拒也会置位；超时＝整条 WebView2 链没走完）。根因待现场确认，本段给三条腿：
# ①参数可调（不改包就能试 flag／放宽超时）②挂死后自动进安全模式并自愈重启
# ③判据写进日志（WebView2 版本、pywebview 调试链、后端访问日志）。


def _clamp_timeout(value, default: int) -> int:
    """超时参数收敛到 5..600 秒；非法值回落默认——配置文件永远不能把启动打崩。"""
    try:
        return min(600, max(5, int(value)))
    except (TypeError, ValueError):
        return default


def load_shell_config(runtime_dir: Path, legacy_dir: Path | None = None) -> dict:
    r"""读 <运行目录>/shell.json（可选；不存在＝全默认）。

    legacy_dir：安装目录当运行目录时，顺带认一眼 %APPDATA%\AwesomeNovel\shell.json
    （v0.28.1 时代的位置）——升级到新版后调参不因位置变化被静默忽略；命中即留日志。

    支持键（都可缺省，非法值回落默认并留日志）：
      webview_args      str   追加给 WebView2 的浏览器参数
      backend_timeout   int   后端就绪等待秒数（5..600，默认 60）
      app_load_timeout  int   应用页装载看门狗秒数（5..600，默认 60）
      safe_mode         bool  强制开/关安全模式（缺省＝按 render-hang.flag 自动判定）
    """
    cfg: dict = {}
    path = runtime_dir / SHELL_CONFIG_NAME
    source = ""
    if not path.exists() and legacy_dir is not None and (legacy_dir / SHELL_CONFIG_NAME).exists():
        path = legacy_dir / SHELL_CONFIG_NAME
        source = "（旧位置 %APPDATA%）"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except Exception:
        log_line(runtime_dir, f"shell.json 读取失败{source}，按默认参数继续：\n" + traceback.format_exc())
        return cfg
    if source:
        log_line(runtime_dir, f"shell.json 取自 {path}{source}——建议挪到运行目录")
    if not isinstance(raw, dict):
        log_line(runtime_dir, f"shell.json 不是对象（{type(raw).__name__}），忽略")
        return cfg
    if "webview_args" in raw:
        if isinstance(raw["webview_args"], str) and raw["webview_args"].strip():
            cfg["webview_args"] = raw["webview_args"].strip()
        else:
            log_line(runtime_dir,
                     f"shell.json: webview_args={raw['webview_args']!r} 非法（需非空字符串），忽略")
    for key, default in (
        ("backend_timeout", DEFAULT_BACKEND_TIMEOUT),
        ("app_load_timeout", DEFAULT_APP_LOAD_TIMEOUT),
    ):
        if key in raw:
            cfg[key] = _clamp_timeout(raw[key], default)
            if cfg[key] != raw[key]:
                # 非数值回落默认 / 越界夹取都必须留痕：现场调参最怕"写了却没生效"
                log_line(runtime_dir,
                         f"shell.json: {key}={raw[key]!r} 不可用或越界（5..600），按 {cfg[key]} 秒生效")
    if "safe_mode" in raw:
        if isinstance(raw["safe_mode"], bool):
            cfg["safe_mode"] = raw["safe_mode"]
        else:
            log_line(runtime_dir,
                     f"shell.json: safe_mode={raw['safe_mode']!r} 非布尔，忽略（按标记自动判定）")
    return cfg


def render_hang_flagged(appdata: Path) -> bool:
    """上次运行把「应用页装载挂死」写进了 render-hang.flag。

    一旦置位就固定走安全模式（同一台机器/同一个 WebView2 运行时上，默认渲染路径
    已被证明会挂）——比每天赌一次强。回正常模式的出口：删掉该文件，或 shell.json
    写 "safe_mode": false。"""
    try:
        return (appdata / RENDER_HANG_MARKER).exists()
    except Exception:
        return False


def flag_render_hang(appdata: Path, note: str) -> None:
    """落「装载挂死」标记（写失败只留日志——兜底路径本身不能成为新炸点）。"""
    try:
        (appdata / RENDER_HANG_MARKER).write_text(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} {note}\n", encoding="utf-8"
        )
    except Exception:
        log_line(appdata, "写 render-hang.flag 失败：\n" + traceback.format_exc())


def safe_mode_enabled(appdata: Path, cfg: dict) -> bool:
    """安全模式判定：shell.json 显式值 > render-hang.flag 标记。"""
    if "safe_mode" in cfg:
        return bool(cfg["safe_mode"])
    return render_hang_flagged(appdata)


def webview_browser_args(cfg: dict, safe_mode: bool) -> str:
    """拼 WebView2 浏览器参数：配置里的 webview_args ＋（安全模式）--disable-gpu。"""
    parts = []
    if cfg.get("webview_args"):
        parts.append(cfg["webview_args"])
    if safe_mode:
        parts.append(SAFE_MODE_ARGS)
    return " ".join(parts)


# 叠加前的 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS 原值（首次 apply_webview_args 时记下；
# 自愈重启据此把孩子进程的环境还原成"用户原始态"）
_webview_args_original = None


def apply_webview_args(args: str) -> None:
    """把参数并进 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS（必须在 create_window 之前调）。

    WebView2 对该环境变量是**追加**语义（官方文档：环境变量值 append 到
    CreateCoreWebView2EnvironmentWithOptions 的参数上），所以既不覆盖用户已有值，
    也不与 pywebview 自塞的 --disable-features=ElasticOverscroll 冲突。"""
    global _webview_args_original
    if _webview_args_original is None:
        # 记下叠加前的原值：自愈重启要把它原样交给孩子进程，否则孩子会二次叠加
        _webview_args_original = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    if not args:
        return
    existing = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "").strip()
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"{existing} {args}".strip()


def webview2_version():
    """WebView2 Runtime 版本（读注册表；非 Windows/读不到返回 None，永不抛）。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except Exception:
        return None
    for hive, sub in (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
         r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    ):
        try:
            with winreg.OpenKey(hive, sub) as key:
                return winreg.QueryValueEx(key, "pv")[0]
        except Exception:
            continue
    return None


def attach_pywebview_log(appdata: Path) -> None:
    """把 pywebview 自己的调试日志旁路到 <运行目录>/pywebview.log。

    GUI 模式下 stderr 是 devnull——缺这一步，pywebview 的 Loading URL /
    loaded event fired 这些关键判据就是黑洞。"""
    try:
        import logging
        from logging.handlers import RotatingFileHandler

        logger = logging.getLogger("pywebview")
        if any(getattr(h, "_ai_novel_file", False) for h in logger.handlers):
            return
        handler = RotatingFileHandler(
            appdata / "pywebview.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8"
        )
        handler._ai_novel_file = True
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    except Exception:
        log_line(appdata, "挂 pywebview 文件日志失败：\n" + traceback.format_exc())


def relaunch_depth_exceeded() -> bool:
    """本进程是被自愈重启拉起来的一代（父进程注入的环境变量）。"""
    return os.environ.get(RELAUNCH_ENV_KEY) == "1"


def should_auto_relaunch(
    *,
    safe_mode: bool,
    frozen: bool,
    platform: str,
    already_relaunched: bool,
    safe_mode_opted_out: bool,
) -> bool:
    """装载挂死后的自愈重启判定（任何情况下最多一轮）。

    守卫 MUST NOT 依赖「下一代会进安全模式」这个前提——标记可能没写成功
    （磁盘/权限/杀软），用户也可能显式关了安全模式；只认重启深度（本进程已是
    重启代就不再重启）＋用户显式 opt-out。非 Windows／dev 模式照旧不重启。"""
    return (
        platform == "win32"
        and frozen
        and not safe_mode
        and not already_relaunched
        and not safe_mode_opted_out
    )


def relaunch_in_safe_mode(appdata: Path) -> bool:
    """拉起新实例（下一轮启动即安全模式）；失败返回 False 走常规兜底。"""
    try:
        import subprocess

        # 孩子进程拿**叠加前**的环境：新实例自己会按 shell.json＋标记重算参数，
        # 直接继承父进程的叠加值会重复（也避免把用户原值盖成父进程的合成值）。
        # 另注入重启深度标记：孩子即使再挂也只走兜底，不会无限重启。
        env = dict(os.environ)
        env[RELAUNCH_ENV_KEY] = "1"
        if _webview_args_original is None:
            env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
        else:
            env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = _webview_args_original
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) if sys.platform == "win32" else 0
        subprocess.Popen([sys.executable], close_fds=True, creationflags=flags, env=env)
        log_line(appdata, f"auto relaunch: 已拉起新实例（{sys.executable}），本轮让位进安全模式")
        return True
    except Exception:
        log_line(appdata, "auto relaunch 失败：\n" + traceback.format_exc())
        return False


def _exit_soon(delay: float = 1.5) -> None:
    """窗口已挂死，走不了正常退出路径——延时强制退出（log_line 逐行落盘，已 flush）。"""
    threading.Timer(delay, lambda: os._exit(0)).start()


# 后端线程存活信号：start_server 一退出（含启动期异常）即置位——
# 健康轮询据此提前判负，不再干等满 60 秒。
_server_exited = threading.Event()

# 后端 Server 句柄（shell-hang-hardening 2.1）：关窗后据此有界请它退出
_server_handle = None

# hang dump 的文件句柄（faulthandler 写入目标；装配后由 cancel 关闭）
_HANG_DUMP_FILE = None


def _app_load_timeout() -> int:
    """应用页装载看门狗时长（秒），env 可调；非法值回落 60。

    优先级：shell.json（见 load_shell_config）> 本 env > 默认。"""
    try:
        return max(5, int(os.environ.get("AI_NOVEL_APP_LOAD_TIMEOUT", str(DEFAULT_APP_LOAD_TIMEOUT))))
    except Exception:
        return DEFAULT_APP_LOAD_TIMEOUT


def _backend_timeout() -> int:
    """后端就绪等待时长（秒），env 可调；非法值回落 60。优先级同 _app_load_timeout。"""
    try:
        return max(5, int(os.environ.get("AI_NOVEL_BACKEND_TIMEOUT", str(DEFAULT_BACKEND_TIMEOUT))))
    except Exception:
        return DEFAULT_BACKEND_TIMEOUT


def stop_server_gracefully(timeout: float = 3.0) -> bool:
    """窗口关闭后的**有界**后端收尾：请 uvicorn 退出并等线程回收（shell-hang-hardening 2.1）。

    返回是否在超时内回收。False 时调用方仍应强制退出——用户关窗的意图优先于在途请求
    （SQLite 是 WAL、日志逐行 flush，硬退不会坏库，代价面只有在途请求）。"""
    server = _server_handle
    if server is None:
        return True
    try:
        server.should_exit = True
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_exited.is_set():
            return True
        time.sleep(0.05)
    return _server_exited.is_set()


def _force_exit(code: int = 0) -> None:
    """进程强制下线。抽成函数是为了可测（单测替换它，避免把 pytest 一起带走）。"""
    os._exit(code)


def arm_hang_dump(appdata: Path, period: float = 60.0) -> None:
    """C 层看门狗（shell-hang-hardening 3.3）：周期把**全部线程栈**dump 到 hang-dump.txt。

    2026-10-06 现场：run 2 在装载注入段整体停摆——之后的 60 秒看门狗行与关窗行全都没写出来，
    即 Python 层已经跑不动了。GIL 被原生调用占死时，普通心跳/看门狗一起失效，只有
    faulthandler 的 C 层定时器还能落盘。装载成功后由 cancel_hang_dump 撤销，避免长会话
    无谓写盘（正常启动几秒内就会取消，实际几乎不产生 dump）。"""
    global _HANG_DUMP_FILE
    try:
        import faulthandler

        f = open(appdata / "hang-dump.txt", "w", encoding="utf-8")
        _HANG_DUMP_FILE = f
        faulthandler.enable(file=f, all_threads=True)
        faulthandler.dump_traceback_later(period, repeat=True, file=f, exit=False)
    except Exception:
        log_line(appdata, "faulthandler 装配失败：\n" + traceback.format_exc())


def cancel_hang_dump() -> None:
    """撤销 hang dump（装载成功/进程下线前）：先停 C 层定时器再关文件（flush）。"""
    global _HANG_DUMP_FILE
    try:
        import faulthandler

        faulthandler.cancel_dump_traceback_later()
    except Exception:
        pass
    if _HANG_DUMP_FILE is not None:
        try:
            _HANG_DUMP_FILE.close()
        except Exception:
            pass
        _HANG_DUMP_FILE = None


def start_server():
    """启动 FastAPI 后端（GUI 模式下跑在后台线程；退出即置 _server_exited）。"""
    appdata = get_runtime_dir()
    try:
        base_dir = get_base_dir()
        backend_dir = base_dir / "backend"
        if backend_dir.exists():
            sys.path.insert(0, str(backend_dir))

        # 安装目录: 数据就跟着 exe 走
        install_dir = get_install_dir()
        install_dir.mkdir(parents=True, exist_ok=True)
        # 运行时目录（日志/端口等）— 安装目录可写即安装目录，否则 appdata（get_runtime_dir）
        appdata.mkdir(parents=True, exist_ok=True)
        # 数据目录（DATA_ROOT）— 全新机器上 data/ 不存在，不建的话 sqlite 打不开 DB
        data_root = install_dir / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        log_line(appdata, f"server thread: dirs ok (data={data_root})")
    except Exception:
        # 目录建不出来＝后端必死（典型：装进 Program Files 且无写权限）。
        # 旧版这段在 try 之外：PermissionError 静默杀掉线程，用户只看到永久
        # 停在启动页，且 startup.log 一个字都没有。
        log_line(appdata, "server thread FATAL preparing dirs:\n" + traceback.format_exc())
        if sys.platform == "win32":
            log_line(appdata, "hint: 数据目录随程序走（便携式）。若安装目录在 "
                              "C:\\Program Files 下，标准用户无权写入——请把应用装到用户目录"
                              "（如 D:\\AwesomeNovel），或以管理员身份运行。")
        _server_exited.set()
        return

    try:
        import uvicorn
        # GUI 模式下 sys.stdout/stderr 为 None，uvicorn 会崩溃
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")

        # 设置环境变量 — 数据目录在安装目录下（便携）
        os.environ.setdefault("DATA_ROOT", str(data_root))

        # PyInstaller 打包后，设置前端 dist 与 reference 模板路径（按打包布局探测）
        res_root = get_resource_root()
        # 品牌单源（brand-name-single-source）：注入资源根供 backend/brand.py 定位
        # （uvicorn 字符串加载的 main:app 等后端模块无法自行探测打包布局）
        os.environ.setdefault("RESOURCE_ROOT", str(res_root))

        # ── S端 地址解析链：显式环境变量 > 发布期 release.json（CI 构建期烘焙）> 占位 ──
        # release.json 由打包工作流生成并随 datas 分发；本地开发没有它 → 行为与历史一致。
        # 注意 server_api 字段自 c-server-api-sync 起 env（release.json 烘焙）恒胜——启动会把 config.json 对齐到本值，手工改 config 会在下次 auth 调用被回滚（其余字段仍手工优先）。
        try:
            from config import load_release_overrides
            release = load_release_overrides(str(res_root))
        except Exception:
            release = {}

        def _env_with_release(name: str, key: str, fallback: str):
            if not os.environ.get(name) and release.get(key):
                os.environ[name] = release[key]
            if not os.environ.get(name):
                os.environ[name] = fallback

        _env_with_release("SERVER_API_BASE", "server_api_base",
            os.environ.get("AI_NOVEL_SERVER_API", "https://your-cloudbase-app.com/api"))
        # S端 兜底基址：自定义域名解析偶发抖动时，call_server_api 自动切直连云托管
        _env_with_release("SERVER_API_FALLBACK", "server_api_fallback",
            os.environ.get("AI_NOVEL_SERVER_API_FALLBACK", ""))
        _env_with_release("PUBLIC_SERVER_API", "public_server_api",
            os.environ.get("AI_NOVEL_PUBLIC_SERVER_API", ""))
        # 会员/客服页门户源（c-package-public-endpoints）：auth_local 对齐消费；
        # 缺省空串＝本地开发无烘焙 → config 默认值不变
        _env_with_release("PORTAL_URL", "portal_url",
            os.environ.get("AI_NOVEL_PORTAL_URL", ""))
        # client-update-notify：版本自报 + 更新检测地址（主/兜底）。
        # 版本默认 dev（本地开发无烘焙 → update_check 跳过检测，行为同历史）；
        # 检测地址默认值与 CI Generate release.json 同源，仅烘焙缺键时兜底。
        _env_with_release("CLIENT_VERSION", "client_version",
            os.environ.get("AI_NOVEL_CLIENT_VERSION", "dev"))
        _env_with_release("CLIENT_UPDATE_URL", "client_update_url",
            os.environ.get("AI_NOVEL_CLIENT_UPDATE_URL",
                "https://www.awesomenovel.com/download/latest.json"))
        _env_with_release("CLIENT_UPDATE_URL_FALLBACK", "client_update_url_fallback",
            os.environ.get("AI_NOVEL_CLIENT_UPDATE_URL_FALLBACK",
                "https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/latest.json"))
        # c-version-build-info：构建信息（仅非 tag 构建烘入，缺省空串——空即 dev 态
        # 由 build_info 落 git 读取或 None）。依赖 config.RELEASE_OVERRIDE_KEYS
        # 白名单含 client_build_branch/client_build_commit，两处须同批改。
        _env_with_release("CLIENT_BUILD_BRANCH", "client_build_branch", "")
        _env_with_release("CLIENT_BUILD_COMMIT", "client_build_commit", "")
        # c-prompt-pack-delivery：提示词包验签公钥（常量定义见文件头；白名单须含 pack_pubkeys）
        _env_with_release("CLIENT_PACK_PUBKEYS", "pack_pubkeys", os.environ.get("AI_NOVEL_CLIENT_PACK_PUBKEYS", PROD_PACK_PUBKEYS))

        frontend_dist = res_root / "frontend"
        if frontend_dist.exists():
            os.environ.setdefault("FRONTEND_DIST", str(frontend_dist))
        ref_dir = res_root / "reference"
        if ref_dir.exists():
            # config.py 的 REFERENCE_DIR 靠 __file__ 相对推导，冻结包对不上 datas 位置 → 显式注入
            os.environ.setdefault("REFERENCE_DIR", str(ref_dir))

        # 使用随机端口避免冲突
        port = random.randint(18000, 18999)

        # 保存端口号
        with open(appdata / "port.json", "w") as f:
            json.dump({"port": port}, f)

        log_line(appdata, f"starting uvicorn on port {port}")
        # GUI 模式下 sys.stdout 为 None，uvicorn 的日志格式化会崩溃
        # 方案: 将日志输出重定向到文件
        # 级别 INFO（shell-render-resilience 起）：WARNING 会把 lifespan 进度
        # （db_lifecycle / seeding / Application startup complete）全吞掉——
        # 「后端就绪超时」类现场就只剩一个空文件。access 日志是判据：渲染进程
        # 的请求到底有没有走到后端（没走到＝卡在 WebView2/网络栈侧）。
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    # 时间戳必须有（2026-10-06 现场）：白屏期间"后端还在不在服务"是核心判据，
                    # 没有时间戳就只能靠猜请求发生在哪一段。
                    "fmt": "%(asctime)s %(levelprefix)s %(message)s",
                    "use_colors": False,
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(appdata / "uvicorn.log"),
                    "mode": "a",
                    "maxBytes": 2_000_000,
                    "backupCount": 2,
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
            },
        }
        # 留句柄（shell-hang-hardening 2.1）：`uvicorn.run()` 一走到底、没有停止入口，关窗后
        # 就只能硬退。换成 Config+Server 后可在窗口关闭时先请它退出再收尾。
        # Server.run() 在非主线程同样跳过信号处理，行为与 run() 一致。
        global _server_handle
        _server_handle = uvicorn.Server(
            uvicorn.Config("main:app", host="127.0.0.1", port=port, log_config=log_config)
        )
        _server_handle.run()
    except Exception as e:
        # 启动期异常（uvicorn 绑定失败 / 导入炸 / lifespan 抛错）必须留全文
        log_line(appdata, f"server thread FATAL: {e!r}\n" + traceback.format_exc())
    finally:
        # 线程退出即置位：轮询线程据此提前判负（用户不用干等 60 秒超时）
        _server_exited.set()
        log_line(appdata, "server thread exited")


def _probe_backend(port: int) -> tuple[bool, str]:
    """打一次 /api/health，返回 (是否就绪, 失败分类)。

    分类是给「慢 vs 死」用的（2026-10-06 现场教训：uvicorn.log 空＋只写一句 timeout，
    没人分得清是导入慢还是死透了）：连接被拒＝uvicorn 还没开始监听（仍在导入 app）；
    已连接但无响应＝已监听、事件循环或 lifespan 还没吐出响应。"""
    import urllib.error
    import urllib.request

    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
        if resp.status == 200:
            return True, ""
        return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}（服务在、健康检查未过）"
    except urllib.error.URLError as e:
        # 注意：urllib 会把 socket 超时包成 URLError(reason=TimeoutError)——两条都要认
        reason = getattr(e, "reason", e)
        text = str(reason).lower()
        if isinstance(reason, TimeoutError) or "timed out" in text or "timeout" in text:
            return False, "已监听但暂无响应（lifespan/app 启动进行中）"
        if isinstance(reason, ConnectionRefusedError) or "refused" in text:
            return False, "连接被拒（uvicorn 尚未开始监听，多半还在导入 app）"
        return False, f"不可达（{reason}）"
    except TimeoutError:
        return False, "已监听但暂无响应（lifespan/app 启动进行中）"
    except Exception as e:  # noqa: BLE001 —— 探测只为分类，绝不外抛
        return False, f"无响应（{type(e).__name__}）"


def wait_for_server(appdata: Path, timeout: int = 15) -> int:
    """等待后端启动，返回端口号。超时返回 None；后端线程已退出则立即判负。

    等待期每 ~15 秒往 startup.log 打一行心跳（已等多久＋本次探测分类）——下次
    「后端就绪超时」现场据此一眼分清"慢"（仍在导入/启动）与"死"（端口不通且线程已退）。"""
    port_file = appdata / "port.json"
    start = time.time()
    last_beat = start
    last_note = "等待 port.json（后端尚未走到监听前）"

    while time.time() - start < timeout:
        port = None
        try:
            with open(port_file) as f:
                port = json.load(f)["port"]
        except Exception:
            port = None
        if port:
            ok, note = _probe_backend(port)
            if ok:
                return port
            last_note = note
        now = time.time()
        if now - last_beat >= 15:
            log_line(appdata, f"backend still starting… {int(now - start)}s（{last_note}）")
            last_beat = now
        # 后端线程已退出且健康检查未过 → 永不会就绪，立即失败（不然干等满超时）
        if _server_exited.is_set():
            return None
        time.sleep(0.5)
    return None


LOADING_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    display: flex; justify-content: center; align-items: center;
    height: 100vh; font-family: -apple-system, sans-serif;
    flex-direction: column; color: #e0e0e0;
  }
  .spinner {
    width: 64px; height: 64px; border: 4px solid rgba(255,255,255,0.1);
    border-top-color: #64b5f6; border-radius: 50%;
    animation: spin 1s linear infinite; margin-bottom: 24px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .title { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
  .subtitle { font-size: 14px; color: #888; animation: pulse 2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.4; } }
</style>
</head>
<body>
  <div class="spinner"></div>
  <div class="title">__BRAND_NAME__</div>
  <div class="subtitle">正在启动…</div>
</body>
</html>"""


def loading_html() -> str:
    """splash 品牌名注入（brand-name-single-source）：CSS 含大量花括号，
    用占位符 replace 而非 format；注入失败回落字面量默认。"""
    name = "爱小说"
    try:
        name = _load_brand().BRAND_NAME or name
    except Exception:
        pass
    return LOADING_HTML_TEMPLATE.replace("__BRAND_NAME__", name)


def write_error_page(appdata: Path, reason: str) -> Path:
    """写启动失败页（含 startup.log 与 uvicorn.log 尾段）并返回路径。

    旧版只带 startup.log 尾段——而后端侧的真实死因（导入炸/lifespan 抛错）
    全在 uvicorn.log 里，报错页反而漏了最有用的那份。"""
    import html

    blocks = []
    for name in ("startup.log", "uvicorn.log"):
        try:
            tail = (appdata / name).read_text(encoding="utf-8", errors="replace")[-1500:]
        except Exception:
            tail = "（无此日志）"
        blocks.append(
            f"<p style='margin:18px 0 6px;color:#9bb'>=== {name} ===</p><pre "
            "style='white-space:pre-wrap;background:#0f3460;padding:16px;"
            "border-radius:8px;max-height:32vh;overflow:auto'>"
            + html.escape(tail) + "</pre>"
        )
    err_path = appdata / "error.html"
    err_path.write_text(
        "<html><head><meta charset='utf-8'></head><body "
        "style='font-family:-apple-system,sans-serif;padding:40px;"
        "background:#1a1a2e;color:#e0e0e0'><h2>" + html.escape(window_title())
        + " 启动失败</h2><p>" + html.escape(reason) + "</p>"
        "<p style='color:#9bb'>日志目录：" + html.escape(str(appdata)) + "</p>"
        "<p style='color:#9bb'>可调参数：" + html.escape(str(appdata / SHELL_CONFIG_NAME))
        + "（webview_args / backend_timeout / app_load_timeout）；"
        "装载挂死后下次启动自动进安全模式（删掉 "
        + html.escape(RENDER_HANG_MARKER) + " 可回默认渲染模式）。</p>"
        + "".join(blocks) + "</body></html>",
        encoding="utf-8",
    )
    return err_path


def _show_error(window, appdata: Path, reason: str) -> None:
    """把错误页装进窗口。UI 线程若已挂死，本调用会阻塞——调用方先落日志。"""
    err_path = write_error_page(appdata, reason)
    log_line(appdata, f"showing error page: {err_path}")
    window.load_url(err_path.as_uri())


def _open_in_browser_fallback(appdata: Path, port: int) -> None:
    """窗口侧故障时的最后兜底：系统默认浏览器打开本地应用。

    前端对 pywebview 原生桥探测不到即回退 HTTP（见 NativeBridge docstring），
    浏览器里功能面不变；只在窗口装载失败时触发，正常运行永不出现。"""
    url = f"http://127.0.0.1:{port}"
    try:
        import webbrowser

        opened = webbrowser.open(url)
        log_line(appdata, f"browser fallback: open({url}) -> {opened}")
    except Exception:
        log_line(appdata, "browser fallback failed:\n" + traceback.format_exc())


def check_backend_and_navigate(window, appdata, cfg: dict | None = None):
    """后台轮询，等后端就绪后跳转到应用页面。

    全函数受保护：旧版一旦这里抛异常（如窗口未 shown 时 load_url 抛
    WebViewException），线程静默死亡＝永久停在启动页且零日志——现场报告
    「长期卡在启动页」的最可疑形态。

    cfg：会话配置（main() 读好传入，避免二次读取出现两套口径）；缺省自读运行目录。"""
    try:
        cfg = load_shell_config(appdata) if cfg is None else cfg
        safe_mode = safe_mode_enabled(appdata, cfg)
        backend_timeout = cfg.get("backend_timeout") or _backend_timeout()
        port = wait_for_server(appdata, timeout=backend_timeout)
        if not port:
            # 两种判负要分开写：旧文案「timeout / server thread exited」被读成"线程退了"，
            # 把"还在导入"误诊成"启动崩了"（2026-10-06 现场两次误读）。
            if _server_exited.is_set():
                log_line(appdata, "backend NOT ready (server thread exited)")
            else:
                log_line(appdata,
                         f"backend NOT ready (timeout {backend_timeout}s；后端线程仍活着，"
                         "多半还在导入/启动中——明细见同目录 uvicorn.log 与上方心跳行)")
            _show_error(window, appdata, "后端启动超时或启动失败，请检查下面的日志：")
            return

        log_line(appdata, f"backend ready (port {port}), dispatching navigation...")
        window.load_url(f"http://127.0.0.1:{port}")
        log_line(appdata, "navigation dispatched; waiting for app page load...")

        # 装载看门狗：跳转已发出但应用页始终不装载（WebView 渲染进程挂死/窗口
        # 消息循环被卡）＝「长期停在启动页」的另一种形态。此时 UI 线程大概率
        # 已不响应、错误页也装不进去——所以先落日志、先打标记再谈兜底。
        load_timeout = cfg.get("app_load_timeout") or _app_load_timeout()
        # 切片等待（shell-hang-hardening 3.2）：死等 60 秒一声不吭的现场没法判读进度，
        # 每 10 秒落一行心跳——它同时也是"进程还活着"的证据（对比 hang-dump.txt 定冻结）。
        loaded = False
        waited = 0
        while waited < load_timeout:
            slice_s = min(10, load_timeout - waited)
            if window.events.loaded.wait(slice_s):
                loaded = True
                break
            waited += slice_s
            log_line(appdata,
                     f"app page still loading… {waited}s/{load_timeout}s（注入链未完成）")
        if loaded:
            log_line(appdata, "app page loaded")
            cancel_hang_dump()  # 装载成功即撤销 C 层 dump，长会话不再写盘
            if safe_mode:
                log_line(appdata, "safe mode 生效（保留 render-hang.flag，后续启动仍走安全模式）")
            return
        log_line(appdata, f"app page NOT loaded in {load_timeout}s — UI/renderer hang suspected")
        flag_render_hang(appdata, f"app page NOT loaded in {load_timeout}s")
        # 自愈重启（任何情况下最多一轮）：守卫只认重启深度与用户显式 opt-out，
        # 不依赖「下一代会进安全模式」——标记写失败时那个前提不成立，会成重启环。
        frozen = bool(getattr(sys, "frozen", False))
        allowed = should_auto_relaunch(
            safe_mode=safe_mode,
            frozen=frozen,
            platform=sys.platform,
            already_relaunched=relaunch_depth_exceeded(),
            safe_mode_opted_out=("safe_mode" in cfg and not bool(cfg["safe_mode"])),
        )
        if allowed and relaunch_in_safe_mode(appdata):
            _exit_soon()
            return
        if not allowed and sys.platform == "win32" and frozen:
            log_line(appdata,
                     "auto relaunch 跳过：本进程已是重启代，或用户显式关闭了安全模式（最多一轮）")
        _open_in_browser_fallback(appdata, port)
        _show_error(window, appdata,
                    "界面加载超时（桌面窗口可能未响应），已尝试用浏览器打开。请把日志发给开发者：")
    except Exception:
        log_line(appdata, "check_backend_and_navigate FAILED:\n" + traceback.format_exc())
        try:
            _show_error(window, appdata, "启动过程异常，请把日志发给开发者：")
        except Exception:
            log_line(appdata, "error page fallback also failed:\n" + traceback.format_exc())


def ensure_loading_page(appdata: Path) -> str:
    """把加载 HTML 写入本地文件，返回 file:// URL"""
    loading_path = appdata / "loading.html"
    loading_path.write_text(loading_html(), encoding="utf-8")
    return loading_path.as_uri()


class NativeBridge:
    """原生对话框桥（c-novel-export-roundtrip）——只暴露文件/目录选择，
    零数据面；前端经 window.pywebview.api 调用，探测不到即回退 HTTP。
    _window_ref 由 main() 在 create_window 之后注入。

    ⚠️ 窗口引用**必须**带下划线前缀：pywebview 枚举 js_api 的公开属性时会**递归**遍历
    非方法属性来收集可调用对象，而原生窗口对象整棵树（WinForms 控件 → WebView2 COM）
    走不通、还只能 UI 线程访问——现场（2026-10-06 用户机 pywebview.log）因此每次装载
    刷出成百上千条 `maximum recursion depth exceeded` / `E_NOINTERFACE` 错误。
    pywebview 的 `get_functions` 只跳过 `_` 前缀名，所以这个下划线不是风格问题。"""

    _window_ref = None

    def pick_folder(self):
        result = self._window_ref.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def pick_save_file(self, default_name: str = "", file_types=None):
        result = self._window_ref.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name or "",
            file_types=file_types or ("zip 文件 (*.zip)", "All files (*)"),
        )
        return result if isinstance(result, str) else (result[0] if result else None)

    def pick_open_file(self, file_types=None):
        result = self._window_ref.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=file_types or ("zip 文件 (*.zip)", "All files (*)"),
            allow_multiple=True,
        )
        return list(result) if result else []

    def open_folder(self, path: str):
        """在系统文件管理器中打开目录（下载成稿完成页出口）。

        Windows 必须用 os.startfile 且不判返回值——explorer 成功也常返回 exit 1，
        按 returncode 判定会假报失败；macOS/Linux 判 returncode。失败返回 False
        不抛（完成页仍显示完整路径，用户可自行前往）。
        """
        import subprocess
        import sys
        from pathlib import Path

        target = Path(path).expanduser() if path else None
        if not target or not target.is_dir():
            return False
        try:
            if sys.platform == "win32":
                import os

                os.startfile(str(target))
                return True
            cmd = ["open", str(target)] if sys.platform == "darwin" else ["xdg-open", str(target)]
            return subprocess.run(cmd, check=False).returncode == 0
        except Exception:
            return False

    def default_dirs(self):
        """常用位置快捷项（下载弹层）：系统文稿/桌面/下载里真实存在的目录。"""
        from pathlib import Path

        home = Path.home()
        names = {"文稿": "Documents", "桌面": "Desktop", "下载": "Downloads"}
        out = []
        for zh, en in names.items():
            p = home / en
            if p.is_dir():
                out.append({"label": zh, "path": str(p)})
        return out


# 模块级单例：main() 在 create_window 后注入 _window_ref（v0.15 曾漏掉本行，
# js_api=bridge 直接触发 NameError——GUI 启动即炸且 --smoke 测不到）
bridge = NativeBridge()


def main():
    """主入口"""
    runtime_dir = get_runtime_dir()
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # log_line 自带临时目录兜底

    # CI 冒烟模式：不起 GUI，直接跑后端（uvicorn.run 阻塞），供打包验证脚本轮询
    # /api/health + 断言前端被服务。headless runner 上可靠，也方便本地快速验证打包后端。
    if "--smoke" in sys.argv:
        start_server()
        return

    log_line(runtime_dir, "shell main() entered: exe=%s frozen=%s data_dir=%s runtime_dir=%s"
             % (sys.executable, getattr(sys, "frozen", False), get_install_dir(), runtime_dir))

    # 调参文件与安全模式（shell-render-resilience）：必须在 create_window 之前——
    # WebView2 环境每次进程只建一次，事后再设参数无效。
    cfg = load_shell_config(runtime_dir, legacy_dir=_legacy_runtime_dir(runtime_dir))
    safe_mode = safe_mode_enabled(runtime_dir, cfg)
    args = webview_browser_args(cfg, safe_mode)
    apply_webview_args(args)
    attach_pywebview_log(runtime_dir)
    # C 层看门狗先架上：GUI 初始化/注入都是可能停摆的段（2026-10-06 现场就停在注入段），
    # 装载成功后 cancel_hang_dump 撤销
    arm_hang_dump(runtime_dir)
    if (runtime_dir / SHELL_CONFIG_NAME).exists():
        log_line(runtime_dir, f"shell.json 生效：{cfg}")
    log_line(runtime_dir, "webview: safe_mode=%s args=%r webview2=%s"
             % (safe_mode, args, webview2_version() or "unknown"))
    if safe_mode:
        log_line(runtime_dir,
                 f"safe mode 说明：删除 {runtime_dir / RENDER_HANG_MARKER} 可回到默认渲染模式")

    # 清陈旧端口文件：port.json 只应来自本次运行。旧值残留时（上一实例未退干净/
    # 上次启动崩在半途）健康轮询会连上前一个进程并据此跳转，多开场景直接卡启动页。
    try:
        (runtime_dir / "port.json").unlink(missing_ok=True)
    except Exception:
        log_line(runtime_dir, "stale port.json cleanup failed:\n" + traceback.format_exc())

    # 把加载页写入本地文件
    loading_url = ensure_loading_page(runtime_dir)

    # 先弹出 pywebview 窗口显示加载动画
    # 自适应屏幕分辨率（跨平台：webview.screens 而非 ctypes.windll.user32）
    try:
        screen = webview.screens[0]
        if hasattr(screen, "width"):  # pywebview 6.x
            win_w = screen.width - 80
            win_h = screen.height - 60
        else:  # pywebview 5.x 的 Screen 只有 resolution 元组
            win_w = screen.resolution[0] - 80
            win_h = screen.resolution[1] - 60
    except Exception:
        win_w, win_h = 1400, 900

    try:
        window = webview.create_window(
            title=window_title(),
            url=loading_url,
            width=win_w,
            height=win_h,
            min_size=(1024, 680),
            resizable=True,
            text_select=True,
            js_api=bridge,
        )
    except Exception:
        # WebView2 运行时缺失等 GUI 初始化炸点：没有窗口可显示，日志是唯一留痕
        log_line(runtime_dir, "create_window FAILED:\n" + traceback.format_exc())
        return
    bridge._window_ref = window

    # 「窗口真的显示了」——UI 挂死类报告的第一分界（有这行＝窗口活了，
    # 之后卡住都发生在导航/装载段；没这行＝GUI 初始化段就没起来）
    def _on_window_shown(*_args, **_kwargs):
        log_line(runtime_dir, "window shown")

    try:
        window.events.shown += _on_window_shown
    except Exception:
        log_line(runtime_dir, "register shown handler failed:\n" + traceback.format_exc())

    # 后台启动后端
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    log_line(runtime_dir, "server thread started")

    # 后台轮询，等后端就绪后跳转（cfg 由本次读取传入，避免两处读到不同结果）
    threading.Thread(
        target=check_backend_and_navigate,
        args=(window, runtime_dir, cfg),
        daemon=True,
    ).start()

    try:
        webview.start(debug=False)
    except Exception:
        log_line(runtime_dir, "webview.start FAILED:\n" + traceback.format_exc())
    else:
        log_line(runtime_dir, "GUI loop exited (window closed)")

    # 退出硬化（shell-hang-hardening 2.2）：pywebview 的注入/DOM 回调/bridge 调用三处线程
    # 都是**非 daemon**（webview/util.py:243/303/335）——一旦卡住，解释器退出时的
    # `threading._shutdown()` 会 join 它们 → 进程残留在任务管理器、并长期占着数据目录句柄
    # （2026-10-06 现场"僵尸实例"即此形态）。所以：先给后端一个有界收尾，再无条件下线。
    # 边界：只覆盖"GUI 循环已退出/启动失败"这两支；GIL 被原生调用占死的冻结形态连
    # threading.Timer 都跑不到，不在本兜底担保范围内（靠 3.3 的 hang dump 取证）。
    cancel_hang_dump()
    graceful = stop_server_gracefully()
    log_line(runtime_dir, f"backend shutdown: graceful={graceful}；强制退出收尾（不留残留进程）")
    _force_exit(0)


if __name__ == "__main__":
    main()
