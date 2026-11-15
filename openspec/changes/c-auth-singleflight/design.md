## Context

S端 CloudBase MinNum=0：缩零后首请求冷启动 30~60s（`call_server_api` timeout=60 的注释明示「10s 会误报超时」）——护栏只能建在「少付、复用」，不能砍超时。前端四处触发点（useAuthHeal 启动自愈 / ExpiryNoticeBar 到期提示 / LicenseProvider 路由切换＋window focus，各自带 60s 节流但互不共享）在冷启动窗口并发叠加：2026-11-14 08:57 实测三连 30.2s。相关代码：`client/backend/auth_local/service.py`（`browser_auth(silent=True)` 静默探测）、`client/backend/auth_local/router.py:27`（`/check-auth` 端点）。

## Goals / Non-Goals

**Goals:**
- 同一窗口同一时刻，check-auth 静默探测出网至多一次；缓存命中调用变本地毫秒级。
- 保住两个既有语义：useAuthHeal 失败间隔重试等实例唤醒（失败不缓存）；PromptPackModal 重新授权等待的即时感知（fresh=1 旁路）。

**Non-Goals:**
- 不砍 timeout（60s 是冷启动预算）。
- 不改前端四处触发点与其节流（后端单飞已消重，前端本地 HTTP 开销毫秒级，收口属过度工程）。
- 不动 `/auth/verify`（820ms 形态另行观察）与 `call_server_api` 本体（多端点共用，动它面太大）。
- 不做 App 启动自动清扫孤儿 WebView（本次只落运维脚本；启动自清扫另行立项）。

## Decisions

1. **缓存放后端端点层，不放大到 `call_server_api`**：`call_server_api` 是多端点共用底座（换钥/设备/包等），加缓存会误伤需要即时性的消费方；只在 `browser_auth(silent=True)` 之上包一层 `browser_auth_silent_cached(fresh=False)`，影响面=check-auth 一个端点。
2. **模块级三件套**（service.py 全局）：`_check_auth_cache`（最近一次 code 0 envelope dict）/ `_check_auth_cached_at`（`time.monotonic()`）/ `_check_auth_inflight`（`asyncio.Task`）。
   - 命中：非 fresh ∧ 有缓存 ∧ age < 60s → 直接返回。
   - 单飞：非 fresh ∧ 在途 Task 未完成 → `await` 同一 Task（并发共享一次出网）。
   - 回填：任何来源（含 fresh 活调）取得 code 0 → 写缓存；code != 0 不回填。
   - fresh=True：不读缓存、不共享在途（授权等待要即时真态）。
3. **失效挂两点**：`browser_auth()`（非静默）入口调 `invalidate_check_auth_cache()`；账号注销/凭据清除路径若在 apply 时确认可达，同样挂（实现时核对，宁多勿漏——宁多活调不误判）。
4. **Task 异常语义与现状一致**：`browser_auth` 内部已把网络异常收敛为 code -1 dict，Task 不预期抛异常；若真抛，向上传播（与今天单调用者 500 行为相同），`finally` 复位在途指针防泄漏。
5. **PromptPackModal 两处 GET 带 `fresh=1`**（等待轮询 ~2s 间隔 + 手动「重新检测」）：该场景响应恒为非 code 0（未授权完成），本不进缓存；带 fresh 防「缓存里旧 code 0」边界（登出后 60s 窗内发起重新授权会被旧快照误判早退）。
6. **测试不改真网**：monkeypatch `browser_auth`（而非 httpx 层），单飞断言用 `asyncio.gather` 收集结果 + 计数器断言「被调次数 == 1」；conftest 夹具重置三件套全局（模块级状态防串测）。

## Risks / Trade-offs

- 快照 stale ≤60s：登出/注销后账号菜单可能短窗显示旧登录态 → 接受（与 LicenseProvider 既有 60s 节流同量级）；登录/重授权路径已失效，且注销清除路径挂失效钩。
- 单飞窗口内新到请求要等在途完成（最坏 60s）→ 正是设计目标（等同单次出网），但注意 useAuthHeal 重试与在途共享后拿到同一 -1，重试节奏不变（20s 间隔由前端控制）。
- 并发写缓存竞态：asyncio 单线程事件循环内三件套读写无 await 间隙即原子；回填只在 Task 完成后单点执行，无锁需求。

## Migration

无数据迁移、无配置项、无发包顺序约束；随下个 C端 版本发布即生效，旧客户端零改动兼容。
