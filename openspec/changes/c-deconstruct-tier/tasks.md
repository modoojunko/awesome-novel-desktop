# c-deconstruct-tier · 任务

## 1. 权益键

- [x] 1.1 registry/契约/fallback 增 `deconstruct`（PRO）/`deconstruct-import`（MAX），两端镜像同批
- [x] 1.2 旧快照隐式放行按 key 分档（前后端同口径，max 键不放 trial/pro）

## 2. 门禁

- [x] 2.1 deconstruct 路由：新建/续拆/重试上传/导出挂 `deconstruct`＋`require_ai_access`；import-book 挂 `deconstruct-import`＋`require_ai_access`；清单/详情/预览/取消/删除不设门
- [x] 2.2 前端：创建页提交锁＋升级弹窗；详情出口弹窗建书（MAX）/导出（PRO）锁＋升级弹窗；正文导入链不挂门

## 3. 售卖面

- [x] 3.1 S端 PlansPage/tierCopy/seed selling_points：AI 拆书＋导出 md=PRO 起；拆书产物建书=MAX；去「即将上线」

## 4. 验证

- [x] 4.1 门禁矩阵测试（免费/标准拒；trial/pro 过 deconstruct；建书仅 max；旧快照隐式放行；开放端点不设门；过期锁）
- [x] 4.2 registry 对拍/REQUIRED_CONSUMERS/契约↔fallback↔seed 测试同批绿；前端 tsc/vitest 绿
- [ ] 4.3 真机抽检：免费/标准/PRO/MAX 四档走一遍创建→出口
