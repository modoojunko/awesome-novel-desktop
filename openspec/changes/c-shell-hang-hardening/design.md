# Design: c-shell-hang-hardening

## 一、现场判定（证据链）

三份真实日志（Windows 11 用户机，v0.28.1；`startup.log` / `uvicorn.log` / `pywebview.log`）：

| 事实 | 证据 |
|---|---|
| run 1（20:15）后端 2 秒就绪、`app page loaded`、20:17:11 `GUI loop exited`，全程正常 | startup.log:1-10 |
| run 1 期间 `check-auth` 吃了一次 WinError 32 / 500，随后自愈（500 后 40 秒内 browser-auth/verify/novels 全 200） | uvicorn.log:12-48 → :53-73 |
| run 2（20:20）后端就绪、导航已发出，**之后再无任何输出**（缺 `app page loaded`、缺 20:21:44 必然出现的 `app page NOT loaded in 60s`、缺 `GUI loop exited`） | startup.log:11-19 |
| run 2 的 js_api 注入在 `_pywebviewready`(44.906) 后只落了一条错误(44.923)即停 | pywebview.log:225-230 |
| 注入风暴本体：`window_ref.native.AccessibilityObject.Bounds.Empty…`（单行 6000+ 字符、978 个 `.Empty`）与跨线程 COM 报错（`CoreWebView2 … only be accessed from the UI thread` / `E_NOINTERFACE`） | pywebview.log:5-87、:140-223 |

## 二、根因（经两轮独立复核 + 第三方分析三方一致）

pywebview 注入 JS API 时递归遍历 `js_api` 对象的公开非方法属性（`webview/util.py`：`for name in
dir(obj)` / `if name.startswith('_'): continue` / 非可调用且带 `__module__` 的对象 → 递归）。我们的
`NativeBridge.window_ref` 是**公开**属性并指向 pywebview `Window`，于是：

```
window_ref → Window.native(WinForms Form) → browser/webview(WebView2) → …
            └── AccessibilityObject.Bounds.Empty.Empty.Empty…（纯 Python 无限递归，撞 recursion limit）
```

两条必须说清的口径（与外部两版分析的分歧点）：

1. **不是"报错把程序搞崩"**。每个属性的异常都被 pywebview 就地吞掉并记一条 ERROR
   （`util.py:207-208`），且注入线程的异常分支**同样会 `loaded.set()`**（`util.py:236-238`）。
   run 1 带着同样的风暴完成了两次注入（+246ms / +155ms）。⇒ 风暴本身只是代价与噪音，
   **死因是遍历里某次取值阻塞**（跨线程 COM 取值要排队到 UI 线程）。
2. **不是只在启动时扫一次**：注入发生在**每次** `NavigationCompleted`（`edgechromium.py:389`），
   每次页面装载都会重放一遍这场遍历。
3. run 2 缺 `app page NOT loaded` 这行 ⇒ **整进程在 44.923 之后停止执行**（GIL 被卡在原生调用的
   线程占死，或进程已被杀）；这也把"关窗后残留进程"定性为该冻住进程本身，而不是"没停 uvicorn"
   （uvicorn 线程是 `daemon=True`，拦不住退出；真正会 join 的是 pywebview 那三处**非 daemon**
   线程 `util.py:243/303/335`）。

## 三、外部两版分析的对照

| 外部说法 | 判定 |
|---|---|
| 第 2 版（属性扫描 → 无限递归 → 下划线私有化） | **一致**：根因与修法都对 |
| 第 2 版"程序崩溃" | 不准确：错误被逐属性吞掉，注入链仍会继续/置位；本次表现是**阻塞**而非崩溃 |
| 第 2 版"启动时扫描一次" | 不准确：每次导航完成都扫 |
| 第 2 版"其他可能性：Pandas/IDE 辅助功能" | 与本仓无关（桥只有 5 个方法，无复杂对象；IDE 设置是编辑器侧） |
| 第 1 版"白屏＝鉴权 500 卡死前端" | **不成立**：500 在第一次运行且自愈；第二次运行无 check-auth 请求 |
| 第 1 版"没停 uvicorn → 僵尸进程持锁" | 机制错（uvicorn 是 daemon）：残留的真实机制是"非 daemon 注入线程 join"或"整进程冻住" |
| 第 1 版"退出生命周期缺失是根因" | 症状对、归因错：退出硬化是**兜底**（本轮 task 2），根因是本轮 task 1 |

## 四、修法映射

| 本 change 任务 | 对应问题 | 为什么这样修 |
|---|---|---|
| 1.x `_window_ref` + 守卫测试 + AST 门禁 + 锁版本 | 根因 | 一行消除遍历入口；两道门禁防回归（运行期 + 打包 CI）；契约依赖未文档化行为故钉死 6.2.1 |
| 2.x 有界优雅收尾 + `os._exit` | 关窗后残留（用户实见） | 非 daemon 注入线程卡住时解释器会 join 它；不硬退就留进程。SQLite 是 WAL、日志逐行 flush ⇒ 硬退不坏库 |
| 3.x 时间戳 / 看门狗心跳 / faulthandler thread-dump | 判据缺口 | 本轮只能判定到"注入段停摆"，因为**没有任何带时间的中间证据**；三件补齐后下一次现场 5 分钟定案 |
| 4.x config.json 唯一 tmp + 重试（仍抛出） | WinError 32 的 500 | 瞬态句柄冲突不该放大成 500；但**不许吞**——吞＝文件与缓存都不更新却报成功，状态丢失更难查 |
| 6.x（不做，另轮） | 单实例互斥 / bridge 源校验 / 前端自检卡 / middleware 读口径 / threadpool 化 | 单实例是**数据安全项**（无 If-Match 的自动保存双写会丢稿），需带"唤醒已有窗口"完整设计；其余收益小于本批风险 |

## 五、残留不确定项（诚实标注）

- run 2 到底是"GIL 被占死的冻结"还是"进程已被杀"，**现有日志无法区分**（两者都表现为后续无输出）。
  3.3 的 `faulthandler` dump 是为此设计的：下一次白屏会直接给出各线程栈与卡点。
- 跨线程 COM 取值具体堵在哪个成员上，同样要等下一次 dump（本次只有"哪一步没走完"）。
