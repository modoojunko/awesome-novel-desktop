## 1. 后端缓存单飞

- [ ] 1.1 `client/backend/auth_local/service.py`：新增 `browser_auth_silent_cached(fresh=False)` 包装与模块级三件套（`_check_auth_cache`/`_check_auth_cached_at`/`_check_auth_inflight`）、`invalidate_check_auth_cache()`；`browser_auth()` 非静默入口挂失效。验证：函数可导入，单测覆盖
- [ ] 1.2 核对注销/凭据清除路径（`service.py` 内清 token 段落）并挂失效钩（design 决策 3，宁多勿漏）。验证：清单写在任务下
- [ ] 1.3 `client/backend/auth_local/router.py`：`/check-auth` 端点增 `fresh: bool = False` 查询参数透传。验证：`GET /api/auth/check-auth?fresh=1` 走活调
- [ ] 1.4 `client/frontend/src/components/novel/license/PromptPackModal.tsx`：等待轮询与手动「重新检测」两处 GET 带 `fresh=1`。验证：tsc 绿 + 既有测试绿
- [ ] 1.5 新增 `client/backend/tests/test_auth_check_singleflight.py` 五案：缓存命中零出网 / 失败(-1)不缓存重出网 / 并发 gather 出网 1 次三请求同结果 / fresh=1 绕过缓存与在途且回填 / browser_auth 非静默后失效（夹具重置三件套）。验证：pytest 该文件绿

## 2. 孤儿清扫脚本（随车，不进 spec）

- [ ] 2.1 `scripts/kill-orphan-webcontent.sh`：筛选 ppid=1 的 WebKit WebContent + `lsof` 无 TCP 句柄 + CPU>50%，默认 `--dry-run` 只列不杀，`--force` 才 `kill -TERM`，输出处置清单。验证：`shellcheck`（若有）或 `bash -n` 绿
- [ ] 2.2 本机实测：当前无孤儿状态输出空清单；构造对照确认 Safari（PID 460 常驻）与其余 0% CPU 孤儿不在处置集。验证：脚本输出摘录贴任务下

## 3. 回归

- [ ] 3.1 后端：`pytest client/backend/tests`（新案＋存量 auth 套含 test_check_auth_contract_client.py）全绿。验证：输出摘要贴任务下
- [ ] 3.2 前端：`npx vue-tsc --noEmit` 不适用（无 Vue 改动）；`tsc --noEmit` 绿。验证：输出摘要贴任务下
- [ ] 3.3 design 门禁：无界面改动，`design:lint` / `design:check` 不适用（proposal Design Impact 判定：纯后端＋轮询加参数＋运维脚本）；无新增文案与语气词。验证：本条引用 proposal 判定依据
- [ ] 3.4 真机走查（随下版发装后）：S端 发版窗口或冷启动期打开书架——app.log 中 check-auth 并发出网仅 1 次、其余毫秒级（对照 2026-11-14 三连 30.2s 消失）；PromptPackModal 重新授权轮询即时感知、无旧快照误判早退。验证：走查记录贴任务下
