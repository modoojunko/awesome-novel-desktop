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

## 4. 评审整改（review-agent，2026-10-06）

- [x] 4.1 **P1 重启环**：守卫不再依赖「下一代会进安全模式」——父进程给孩子注入
      `AI_NOVEL_SHELL_RELAUNCHED=1`，重启代一律不再重启；`shell.json` 显式 `safe_mode:false`
      时不重启；被跳过的原因落日志。三条成环路径（标记正常/标记写失败/显式 opt-out）脚本实证：
      父代重启、子代不再重启
- [x] 4.2 **P3 静默回落**：shell.json 每个键被拒绝/夹取都留日志（含原值与生效值）——
      与新立 spec 的「类型不符/越界 SHALL 回落默认并留日志」对齐
- [x] 4.3 测试：守卫六态（含重启代/opt-out）、孩子进程深度标记、回落留痕 4 键、重启代集成与
      opt-out 集成；28 → **31 例全绿**

## 6. 第二轮现场追加（2026-10-06 夜，用户机 Windows 11；用户拍板"文件都在安装目录"）

- [x] 6.1 运行目录选择：`get_runtime_dir()`＝Windows 安装版实测安装目录可写→安装目录，否则回落
      `%APPDATA%\AwesomeNovel`；macOS/dev 不变（dev 不往项目目录写）；`main()`/`start_server()`
      两个调用点接线，`shell main() entered` 行增记 `runtime_dir`
- [x] 6.2 `shell.json` 兼容旧位置：运行目录优先，`%APPDATA%` 同名文件兜底并留「取自旧位置」日志；
      配置由 main() 读好后传进 `check_backend_and_navigate`（消除二次读取口径分叉）
- [x] 6.3 打包链路随行：Windows smoke（client-package.yml）与 `build_release.ps1` 两候选目录定位
      port.json/日志；`installer.iss` 补 `[UninstallDelete]` 清 `{app}` 里的运行时产物；
      `install_portable.bat` 完成提示改口径；macOS smoke 路径不变
- [x] 6.4 就绪等待：默认 180 秒（现场首次冷启动 >60s 被杀软首扫拖穿）；等待期每 ~15s 心跳
      （已等秒数＋探测分类：连接被拒＝仍在导入 / 已监听无响应＝lifespan 进行中）；
      判负文案分因（线程退出 vs 超时但仍在导入），不再用一句含糊话
- [x] 6.5 测试：探针三态（拒/超时/200）、心跳行＋分类、判负两文案、运行目录三态、探针文件即删、
      旧位置配置兼容与优先级；31 → **42 例全绿**
- [ ] 6.6 真机复验（用户侧）：换包后首次启动应落 `startup.log` 心跳行；`shell.json` 直接放
      `D:\AwesomeNovel\`；后台 60s+ 时心跳能看出"在导入"而非"崩了"

## 7. 验收与收尾

- [x] 7.1 门禁：`ruff check --extend-select F811,F821,F841` 改动文件零新增；
      `ruff check --select F821 client/packaging/build/pywebview_app.py`（打包 CI 同款）绿
- [x] 7.2 全量 `client/backend` pytest：**1954 passed / 1 skipped / 0 failed**（68s；与 main 基线零新增红）
- [x] 7.3 macOS 真机非 GUI 自证：真实 pywebview 6.2.1 下 `pywebview.log` 落盘（含 `Loading URL` /
      `loaded event fired` 两判据）、安全模式两态（无标记＝无参数 / 有标记＝`--disable-gpu`）、
      追加注入语义、shell.json 生效＋参数合成、`webview2_version()` 非 Windows 回落 unknown
- [x] 7.4 `openspec validate c-shell-render-resilience --specs`（`--strict`）复验通过
- [ ] 7.5 提交＋推送更新 PR（标题不带硬编码 PR 号）；打包随下一版本窗口（测试同学要新包才谈得上复验 3.4）
