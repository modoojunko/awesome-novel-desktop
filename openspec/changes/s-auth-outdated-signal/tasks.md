## 1. S端 契约（authorize/check-auth/标记表）

- [x] 1.1 `authorize_device.py` 分档：challenge 校验失败且用户名密码正确 → code=3 + reason=client_outdated + latest_version + download_url（有则带）；msg 动作导向（去「版本过旧」断言）；密码错误路径不动。验证：pytest——challenge 空+密码对→code=3+落标记；challenge 空+密码错→code=1 不落标记
- [x] 1.2 标记存储：PG 表 `device_outdated_marks(pc_hash PK, rejected_at)`，authorize 分档拒绝后 upsert；读取按 TTL≥10min 读时比较。验证：pytest——落标记→模拟重启（新 session）→TTL 内可读、过期不可读
- [x] 1.3 check-auth 出口：无 grant 且 TTL 内有标记 → code=3 + data{client_outdated:true, latest_version, download_url?}；其余形态不变。验证：pytest——有标记无 grant→code=3；有 grant→正常响应（标记不干扰已授权设备）；无标记→现状
- [x] 1.4 pair/exchange 排除面契约测试：全错误分支响应形状断言不含 outdated 字段。验证：pytest 绿
- [x] 1.5 AuthPage.vue 文案对齐两场景：授权失败区按错误档分流（需更新/暂时无法登录），「版本过旧」措辞全站清零。验证：S端 e2e/组件测试断言新文案；grep 无「版本过旧」

## 2. C端 透传

- [x] 2.1 `auth_local/service.py` check-auth 透传：data 里存在 client_outdated 载荷时原样透传给前端（字段级向后兼容）。验证：pytest——mock S端 code=3 → 本地响应含 client_outdated

## 3. 门禁与部署

- [x] 3.1 S端 全量 pytest＋前端 vitest/e2e 绿；C端 pytest 绿。验证：各套全绿留输出
- [x] 3.2 合 main → s-server-deploy 部署 → 线上验证：构造 code=3 场景（无 challenge 探针）实响应对拍；标记表跨重启存活（等缩容或重启实例后复测）。验证：curl 探针留档
- [x] 3.3 记忆更新：信号契约（code=3/TTL/排除面）与「部署后须同时验 S端 前端」进 s-server 部署配方。验证：记忆落盘
