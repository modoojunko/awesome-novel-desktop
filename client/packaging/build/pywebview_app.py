# client/packaging/pywebview_app.py
"""AI Novel 桌面应用入口 — pywebview 壳"""

import os
import sys
import json
import threading
import random
import time
from pathlib import Path

# 模块级导入：NativeBridge 方法内引用 webview 常量，函数级导入会让 F821 误判未定义；
# import 本身不初始化 GUI（start() 才会），--smoke 路径同样安全
import webview


def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    # Dev 模式: pywebview_app.py 在 client/packaging/build/ → 项目根目录
    return Path(__file__).parent.parent.parent


def get_appdata() -> Path:
    """运行时数据目录（日志/端口文件等）— 跨平台。
    Windows: %APPDATA%\AI Novel；macOS: ~/Library/Application Support/AI Novel。"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("APPDATA", "."))
    return base / "AI Novel"


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
            BRAND_NAME_EN = "AI Novel"
            BRAND_MARK = "爱"
            BRAND_TAGLINE = "AI 辅助长篇小说写作"

        return _BrandFallback


def window_title() -> str:
    """系统窗口标题 = 品牌名（与产品名一致，替代历史「AI Novel」）。"""
    try:
        return _load_brand().BRAND_NAME
    except Exception:
        return "爱小说"


def start_server():
    """启动 FastAPI 后端"""
    base_dir = get_base_dir()
    backend_dir = base_dir / "backend"
    if backend_dir.exists():
        sys.path.insert(0, str(backend_dir))

    # 安装目录: 数据就跟着 exe 走
    install_dir = get_install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)
    # 运行时目录（日志等临时文件）— 跨平台取 appdata
    appdata = get_appdata()
    appdata.mkdir(parents=True, exist_ok=True)
    # 数据目录（DATA_ROOT）— 全新机器上 data/ 不存在，不建的话 sqlite 打不开 DB
    data_root = install_dir / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    # 写一条启动日志
    log_file = appdata / "startup.log"
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
        # setdefault 语义保证装机后手工改 config.json / 环境变量始终优先。
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

        with open(log_file, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] Starting uvicorn on port {port}\n")

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
        with open(log_file, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] ERROR: {e}\n")
            import traceback
            traceback.print_exc(file=f)


def wait_for_server(appdata: Path, timeout: int = 15) -> int:
    """等待后端启动，返回端口号。超时返回 None。"""
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


def check_backend_and_navigate(window, appdata):
    """后台轮询，等后端就绪后跳转到应用页面"""
    port = wait_for_server(appdata, timeout=60)
    if port:
        with open(appdata / "startup.log", "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] Backend ready, navigating...\n")
        window.load_url(f"http://127.0.0.1:{port}")
    else:
        # 跨平台错误：写 error.html 并加载到窗口（窗口本就是 HTML，免去 Windows MessageBox）
        import html
        try:
            with open(appdata / "startup.log") as f:
                logs = f.read()
        except Exception:
            logs = "无日志"
        err_path = appdata / "error.html"
        err_path.write_text(
            "<html><head><meta charset='utf-8'></head><body "
            "style='font-family:-apple-system,sans-serif;padding:40px;"
            "background:#1a1a2e;color:#e0e0e0'><h2>" + html.escape(window_title()) + " 启动失败</h2>"
            "<p>后端启动超时，请检查日志:</p><pre "
            "style='white-space:pre-wrap;background:#0f3460;padding:16px;border-radius:8px'>"
            + html.escape(logs[-500:]) + "</pre></body></html>",
            encoding="utf-8",
        )
        window.load_url(err_path.as_uri())


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


# 模块级单例：main() 在 create_window 后注入 window_ref（v0.15 曾漏掉本行，
# js_api=bridge 直接触发 NameError——GUI 启动即炸且 --smoke 测不到）
bridge = NativeBridge()


def main():
    """主入口"""
    appdata = get_appdata()
    appdata.mkdir(parents=True, exist_ok=True)

    # CI 冒烟模式：不起 GUI，直接跑后端（uvicorn.run 阻塞），供打包验证脚本轮询
    # /api/health + 断言前端被服务。headless runner 上可靠，也方便本地快速验证打包后端。
    if "--smoke" in sys.argv:
        start_server()
        return

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
    bridge.window_ref = window

    # 后台启动后端
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    with open(appdata / "startup.log", "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] Started server thread\n")

    # 后台轮询，等后端就绪后跳转
    threading.Thread(
        target=check_backend_and_navigate,
        args=(window, appdata),
        daemon=True,
    ).start()

    webview.start(debug=False)


if __name__ == "__main__":
    main()
