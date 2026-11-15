## Why

本地 C端 书架页偶发打开干等 30~60 秒：S端 是 CloudBase MinNum=0 缩零架构，冷启动/发布窗口期间 `check-auth` 单次出网就要 30~60s（2026-11-14 实锤：08:57 三连 30.2s 正撞 S端发版窗口；11-13 11:49 两发 30s 冷启动形态），而前端 useAuthHeal / ExpiryNoticeBar / LicenseProvider（路由切换＋window focus）四处各自打 `GET /auth/check-auth`，无缓存无单飞——同一窗口并发三发各付一次 30s。护栏建在「少付、复用」，不是砍超时（60s 超时是冷启动预算，注释明示 10s 会误报）。

## What Changes

- 后端 `GET /auth/check-auth` 增加成功快照缓存（60s）与出网单飞（并发共享同一在途探测）：同一窗口同一时刻出网至多一次，多数调用变本地毫秒级。
- 失败结果（code -1 冷启动/网络错误）**不缓存**——失败后下一次调用重新出网，保住 useAuthHeal「间隔重试等实例唤醒」的自愈语义。
- 新增 `?fresh=1` 旁路：跳过缓存读取并绕过在途共享强制活调，活调取得的 code 0 结果回填缓存。PromptPackModal 的授权等待轮询与手动「重新检测」两处使用，防止旧 code 0 快照让重新授权误判早退。
- 非静默登录（`POST /auth/browser-auth`）后失效缓存：登录后的首次 check-auth 必为活调。
- 随车 `scripts/kill-orphan-webcontent.sh`：孤儿 WebKit WebContent 清扫脚本（ppid=1＋无 TCP 句柄＋CPU>50% → kill），运维级止血 2026-11-14 事故类问题（App 卡死重启后旧 WebView XPC 泄漏，100% CPU＋4.7GB 内存烧 2.5 天拖慢整机）。

## Capabilities

### New Capabilities
- `auth-check-dedup`: check-auth 出网去重契约——成功快照缓存、单飞共享、失败不缓存、fresh 旁路、登录动作后失效。

### Modified Capabilities
- 无：useAuthHeal 钩子行为与 `frontend-auth-heal` spec 不变（启动仍恰一次探测、失败重试节奏不变），重复出网由后端单飞自然消掉。

## Impact

- `client/backend/auth_local/service.py`：新增缓存单飞包装与失效函数（浏览器 OAuth 静默探测路径）。
- `client/backend/auth_local/router.py`：`/check-auth` 增加 `fresh` 查询参数。
- `client/frontend/src/components/novel/license/PromptPackModal.tsx`：两处轮询 GET 带 `fresh=1`（仅加参数，行为不变）。
- `client/backend/tests/`：新增缓存单飞测试套。
- `scripts/kill-orphan-webcontent.sh`：新增运维脚本（不进 spec，属工具链）。
- 兼容性：响应 envelope 形状不变；前端其余调用点零改动；旧客户端不传 `fresh` 走缓存路径即目标行为。

## Design Impact

无用户可见界面改动：纯后端网络层＋授权轮询加参数＋运维脚本。不触碰两端共享设计段，免原型；无新增文案与语气词。
