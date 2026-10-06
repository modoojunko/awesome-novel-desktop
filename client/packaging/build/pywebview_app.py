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
    r"""运行时数据目录（日志/端口文件）— 跨平台；macOS 上它同时是书稿数据目录。
    Windows: %APPDATA%\AwesomeNovel；macOS: ~/Library/Application Support/AwesomeNovel。
    旧名 AI Novel 目录（≤v0.27 品牌）在 macOS 首启自动换名并在旧路径留软链；
    Windows 侧旧目录只剩历史日志，不迁移（卸载器两个都清）。"""
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
    """把一行带时间戳的启动日志追加到 <appdata>/startup.log。

    appdata 不可写时退到系统临时目录（如装进 Program Files 且无写权限），
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


# 后端线程存活信号：start_server 一退出（含启动期异常）即置位——
# 健康轮询据此提前判负，不再干等满 60 秒。
_server_exited = threading.Event()


def _app_load_timeout() -> int:
    """应用页装载看门狗时长（秒），env 可调；非法值回落 60。"""
    try:
        return max(5, int(os.environ.get("AI_NOVEL_APP_LOAD_TIMEOUT", "60")))
    except Exception:
        return 60


def start_server():
    """启动 FastAPI 后端（GUI 模式下跑在后台线程；退出即置 _server_exited）。"""
    appdata = get_appdata()
    try:
        base_dir = get_base_dir()
        backend_dir = base_dir / "backend"
        if backend_dir.exists():
            sys.path.insert(0, str(backend_dir))

        # 安装目录: 数据就跟着 exe 走
        install_dir = get_install_dir()
        install_dir.mkdir(parents=True, exist_ok=True)
        # 运行时目录（日志等临时文件）— 跨平台取 appdata
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
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelprefix)s %(message)s",
                    "use_colors": False,
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.FileHandler",
                    "filename": str(appdata / "uvicorn.log"),
                    "mode": "a",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "WARNING", "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": "WARNING", "propagate": False},
            },
        }
        uvicorn.run(
            "main:app",
            host="127.0.0.1",
            port=port,
            log_config=log_config,
        )
    except Exception as e:
        # 启动期异常（uvicorn 绑定失败 / 导入炸 / lifespan 抛错）必须留全文
        log_line(appdata, f"server thread FATAL: {e!r}\n" + traceback.format_exc())
    finally:
        # 线程退出即置位：轮询线程据此提前判负（用户不用干等 60 秒超时）
        _server_exited.set()
        log_line(appdata, "server thread exited")


def wait_for_server(appdata: Path, timeout: int = 15) -> int:
    """等待后端启动，返回端口号。超时返回 None；后端线程已退出则立即判负。"""
    import urllib.request

    port_file = appdata / "port.json"
    start = time.time()

    while time.time() - start < timeout:
        if port_file.exists():
            try:
                with open(port_file) as f:
                    port = json.load(f)["port"]
                # 尝试连接 health 端点
                resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
                if resp.status == 200:
                    return port
            except Exception:
                pass
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


def check_backend_and_navigate(window, appdata):
    """后台轮询，等后端就绪后跳转到应用页面。

    全函数受保护：旧版一旦这里抛异常（如窗口未 shown 时 load_url 抛
    WebViewException），线程静默死亡＝永久停在启动页且零日志——现场报告
    「长期卡在启动页」的最可疑形态。"""
    try:
        port = wait_for_server(appdata, timeout=60)
        if not port:
            log_line(appdata, "backend NOT ready (timeout / server thread exited)")
            _show_error(window, appdata, "后端启动超时或启动失败，请检查下面的日志：")
            return

        log_line(appdata, f"backend ready (port {port}), dispatching navigation...")
        window.load_url(f"http://127.0.0.1:{port}")
        log_line(appdata, "navigation dispatched; waiting for app page load...")

        # 装载看门狗：跳转已发出但应用页始终不装载（WebView 渲染进程挂死/窗口
        # 消息循环被卡）＝「长期停在启动页」的另一种形态。此时 UI 线程大概率
        # 已不响应、错误页也装不进去——所以先落日志、先开浏览器兜底。
        timeout = _app_load_timeout()
        if window.events.loaded.wait(timeout):
            log_line(appdata, "app page loaded")
            return
        log_line(appdata, f"app page NOT loaded in {timeout}s — UI/renderer hang suspected")
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
    window_ref 由 main() 在 create_window 之后注入。"""

    window_ref = None

    def pick_folder(self):
        result = self.window_ref.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def pick_save_file(self, default_name: str = "", file_types=None):
        result = self.window_ref.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name or "",
            file_types=file_types or ("zip 文件 (*.zip)", "All files (*)"),
        )
        return result if isinstance(result, str) else (result[0] if result else None)

    def pick_open_file(self, file_types=None):
        result = self.window_ref.create_file_dialog(
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


# 模块级单例：main() 在 create_window 后注入 window_ref（v0.15 曾漏掉本行，
# js_api=bridge 直接触发 NameError——GUI 启动即炸且 --smoke 测不到）
bridge = NativeBridge()


def main():
    """主入口"""
    appdata = get_appdata()
    try:
        appdata.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # log_line 自带临时目录兜底

    # CI 冒烟模式：不起 GUI，直接跑后端（uvicorn.run 阻塞），供打包验证脚本轮询
    # /api/health + 断言前端被服务。headless runner 上可靠，也方便本地快速验证打包后端。
    if "--smoke" in sys.argv:
        start_server()
        return

    log_line(appdata, "shell main() entered: exe=%s frozen=%s data_dir=%s"
             % (sys.executable, getattr(sys, "frozen", False), get_install_dir()))

    # 清陈旧端口文件：port.json 只应来自本次运行。旧值残留时（上一实例未退干净/
    # 上次启动崩在半途）健康轮询会连上前一个进程并据此跳转，多开场景直接卡启动页。
    try:
        (appdata / "port.json").unlink(missing_ok=True)
    except Exception:
        log_line(appdata, "stale port.json cleanup failed:\n" + traceback.format_exc())

    # 把加载页写入临时文件
    loading_url = ensure_loading_page(appdata)

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
        log_line(appdata, "create_window FAILED:\n" + traceback.format_exc())
        return
    bridge.window_ref = window

    # 「窗口真的显示了」——UI 挂死类报告的第一分界（有这行＝窗口活了，
    # 之后卡住都发生在导航/装载段；没这行＝GUI 初始化段就没起来）
    def _on_window_shown(*_args, **_kwargs):
        log_line(appdata, "window shown")

    try:
        window.events.shown += _on_window_shown
    except Exception:
        log_line(appdata, "register shown handler failed:\n" + traceback.format_exc())

    # 后台启动后端
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    log_line(appdata, "server thread started")

    # 后台轮询，等后端就绪后跳转
    threading.Thread(
        target=check_backend_and_navigate,
        args=(window, appdata),
        daemon=True,
    ).start()

    try:
        webview.start(debug=False)
    except Exception:
        log_line(appdata, "webview.start FAILED:\n" + traceback.format_exc())
        return
    log_line(appdata, "GUI loop exited (window closed)")


if __name__ == "__main__":
    main()
