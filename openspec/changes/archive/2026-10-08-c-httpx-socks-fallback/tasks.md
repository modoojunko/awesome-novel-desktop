# c-httpx-socks-fallback 任务清单

## 1. 依赖与降级工厂

- [x] 1.1 `client/backend/requirements.txt`：`httpx>=0.27.0` →
  `httpx[socks]>=0.27.0`；本地 venv 复装后 `python -c "import socksio; print(socksio.__version__)"`
  验证可导入。验证：pip 安装日志无冲突、导入成功。
- [x] 1.2 backend 根新建 `http_client.py` 工厂（sync/async 双入口）：封装出网
  `AsyncClient`/`Client` 构造——首笔构造抛 `Exception` 时 logger.warning 留痕
  （降级原因＋代理形态，**只记 scheme＋host:port、剔除 userinfo**——代理 URL 可能
  内嵌凭据，ai_client._host_of 判例）后以 `trust_env=False` 重建返回；构造成功
  原样返回。实现硬约束（design D3）：内部以 `httpx.AsyncClient`/`httpx.Client`
  模块属性**晚绑定**调用（不得导入期绑定——既有 7 处测试夹具 monkeypatch 模块
  属性）；kwargs 全量透传（含 transport=/follow_redirects=）。
  单测三分支（pytest，见 design D5）：ALL_PROXY=socks5://… 下构造走 SOCKS 路径，
  断言 mounts/transport 确为代理传输（可辨别，非「非 500」）；monkeypatch 首笔
  构造抛 ImportError 时降级生效、留痕无凭据；干净 env 下返回的 client 与直构
  行为一致。验证：新用例绿。

## 2. 九处构造点迁移

- [x] 2.1 `auth_local/service.py` `call_server_api` 与 `auth_local/router.py`
  `devices/current` 两处（timeout 60s/5s/3s）换用工厂，原参数逐点核对不丢。
  验证：auth_local 既有 pytest 全绿 + 1.2 新用例绿。
- [x] 2.2 `update_check.py`、`zhuque/client.py`、`prompt_pack/sync.py`（两处**同步**
  `httpx.Client` 走同步入口，probe/sync 链路一并获得降级兜底）、
  `api_configs/connection.py`（两处）换用工厂，原参数逐点核对不丢
  （timeout/follow_redirects）。
  验证：update/zhuque/prompt_pack/api_configs 既有 pytest 全绿。
- [x] 2.3 全仓 grep 复核：backend 非测试代码零 `httpx.AsyncClient(` 与
  `httpx.Client(` 直构残留（两种形态都查；openai/anthropic SDK 内部与测试桩豁免）。
  验证：grep 输出仅剩 SDK/测试命中。

## 3. 打包链

- [ ] 3.1 socksio 钉入 `bundle_manifest.py` 的 `HIDDEN_IMPORTS` **单源**
  （PyInstaller/Nuitka 双引擎共同消费；只在 build.spec 私加会让 Nuitka 产物静默
  漏收——缺条目不 FATAL，design D4）。验证：dispatch 演练出双引擎
  Windows/macOS 包成功；tests/test_bundle_manifest.py parity 绿。
  进度：清单已钉 socksio（连同 http_client），parity `4 passed` ✓；
  dispatch 双引擎出包演练随本 PR 发版链执行（Actions 配额墙期间不单独空跑）。
- [ ] 3.2 双平台产物解包抓特征串自证 socksio 在包内
  （c-prompt-pack-hardening 判例：抓产物特征串，别只看构建命令成功）。
  验证：两平台产物各附一条特征串命中证据。

## 4. 回归与发版

- [x] 4.1 `cd client/backend && pytest` 全量绿（worktree/正确解释器口径）；
  push 前 `pip install ruff==0.16.3` 对齐 CI 版本复核全后端零新增告警
  （ruff-ci-version-pin 判例）。
  验证：pytest 汇总行 + ruff 零输出贴任务下。
  证据：`2076 passed, 1 skipped in 75.46s`（共享 venv 解释器、worktree 内）；
  `ruff 0.16.3 check .` → `All checks passed!`（曾揪出 SIM117 一处，已修复）。
- [x] 4.2 前端门禁不适用判定：本改零 UI、零共享段、零前端文件
  （proposal 无 Design Impact 段即判定依据），design:lint / design:check /
  vitest / e2e 不涉及。
  验证：`git diff --stat` 无 client/frontend 命中。
  证据：worktree `git status --short` 全部命中仅 client/backend/** 与
  client/packaging/** 与 openspec/**，零 frontend。
- [ ] 4.3 发版后用户复测口径：SOCKS 系统代理 VPN 开启状态下，
  登录检测在 120s 轮询窗口内成功、更新检查非 500
  （发布前用户侧临时解法＝关 VPN 重新检测或切 HTTP 代理模式）。
  验证：用户回执或复测 app.log 中 check-auth 返回 200。
