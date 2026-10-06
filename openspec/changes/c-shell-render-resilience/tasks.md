# Tasks: c-shell-render-resilience

## 0. 现场判定实验（先做，无需新包）

- [ ] 0.1 让测试同学用**当前 v0.28 包**A/B（命令行 `set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--disable-gpu`
      后启动 `AwesomeNovel.exe`，或设为用户环境变量后双击）：装载成功＝GPU/渲染层假设成立（安全模式方向正确）；
      仍挂＝转查杀软/代理拦 loopback、WebView2 运行时修复，并回收 0.2 证据
- [ ] 0.2 回收：任务管理器进程数（AwesomeNovel.exe / msedgewebview2.exe）、窗口是否"未响应"、
      浏览器兜底 URL 在同机能打开否、WebView2 Runtime 版本、事件查看器有无 msedgewebview2 崩溃

## 1. 可调参数（shell.json）

- [x] 1.1 `load_shell_config`：webview_args / backend_timeout / app_load_timeout / safe_mode；
      缺省＝默认；非法 JSON／非对象／类型不符／越界一律回落＋留日志（永不阻断启动）
- [x] 1.2 接线：`check_backend_and_navigate` 吃会话配置（shell.json > AI_NOVEL_* env > 默认 60）
- [x] 1.3 测试 6 例：缺省、合法值、坏 JSON、非对象、越界夹取＋类型拒绝、超时接线

## 2. 装载挂死自愈

- [x] 2.1 标记：`render-hang.flag`（装载看门狗超时即落，持久；写失败只留日志）
- [x] 2.2 安全模式：`--disable-gpu` 经 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` **追加**注入
      （create_window 之前；不覆盖既有值——WebView2 官方语义为 append）
- [x] 2.3 自愈重启：Windows 安装版且本次非安全模式 → 拉新实例＋延时强制让位（`_exit_soon`）；
      失败/不适用 → 维持浏览器兜底＋错误页
- [x] 2.4 出口：删标记或 shell.json `"safe_mode": false`；日志与错误页都写明路径
- [x] 2.5 测试 6 例：参数拼接、追加语义、判定优先级、重启守卫四态、成功保持安全模式、
      挂死两路分支（重启 / 兜底）

## 3. 证据补齐

- [x] 3.1 startup.log：safe_mode、生效参数、WebView2 Runtime 版本（注册表读；读不到＝unknown，永不抛）
- [x] 3.2 pywebview 调试日志旁路 → `pywebview.log`（rotate 2MB×3；GUI 下 stderr 是 devnull）
- [x] 3.3 uvicorn 级别 WARNING→INFO＋开 access；uvicorn.log 轮转 2MB×3＋utf-8
- [ ] 3.4 真机复验：换包后回收 startup.log＋uvicorn.log＋pywebview.log，按 0.1 结论定安全模式参数

## 4. 验收与收尾

- [x] 4.1 门禁：`ruff check --extend-select F811,F821,F841` 改动文件零新增；
      `ruff check --select F821 client/packaging/build/pywebview_app.py`（打包 CI 同款）绿
- [x] 4.2 全量 `client/backend` pytest：**1892 passed / 0 failed**（66s；与 main 基线零新增红）
- [x] 4.3 macOS 真机非 GUI 自证：真实 pywebview 6.2.1 下 `pywebview.log` 落盘（含 `Loading URL` /
      `loaded event fired` 两判据）、安全模式两态（无标记＝无参数 / 有标记＝`--disable-gpu`）、
      追加注入语义、shell.json 生效＋参数合成、`webview2_version()` 非 Windows 回落 unknown
- [x] 4.4 `openspec validate c-shell-render-resilience --specs` 通过（`--strict` 亦通过）
- [ ] 4.5 提交＋PR（标题不带硬编码 PR 号）；打包随下一版本窗口（测试同学要新包才谈得上复验 3.4）
