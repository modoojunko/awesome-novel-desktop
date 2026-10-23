# c-cover-avatar-ui · 任务

## 1. 配置页

- [x] 1.1 图像模型页第三页签：列表/新增/编辑/删除/恢复/默认
- [x] 1.2 换供应商显式确认；未填新 Key/模型时清空旧值，不把旧 Key 发到新 Base
- [x] 1.3 软删恢复 + 影响书数提示；默认配置补位与后端一致

## 2. 工坊

- [x] 2.1 封面工坊：上传（XHR FormData + 进度）、候选列表、采用、8s 撤销、丢弃候选
- [x] 2.2 头像工坊：同上；角色设置 GET/PATCH 回填
- [x] 2.3 书级设置 PATCH：只改模型/画风/seed 不清未提交字段
- [x] 2.4 签名 URL 过期：图片 onError 走 `/image-assets/{id}/links` 重取一次
- [x] 2.5 免费用户只能上传；生成/测试/批量只放入口占位（阶段 3）

## 3. 展示与状态

- [x] 3.1 书架书卡/角色列表/详情展示 cover/avatar，无图占位可点
- [x] 3.2 采用/撤销后刷新书架/角色列表/角色详情/资产列表
- [x] 3.3 删除书/角色确认文案与后端级联一致；撤销角色不恢复头像
- [x] 3.4 时间字段统一 `parseServerTime`；撤销倒计时和签名刷新不用裸 `new Date`

## 4. 验证

- [x] 4.1 前端单测：配置面板/工坊上传/采用/撤销/丢弃、书卡封面入口、图像页签；`tsc` 全绿；`vitest run` 1772 passed；coverage contract 100%；`npm run build` 通过
- [x] 4.2 e2e（隔离栈：专属 vite 5174 + uvicorn 18000 + /tmp DATA_ROOT）：API 建书 → 上传 → 候选 → 采用 → 书架可见封面 → 首次采用撤销回无图 → 再采用书架可见；`image-workshop.spec.ts` 1 passed
- [x] 4.3 书卡封面入口同步进 `docs/design-c/prototypes/list.html`；`design:lint` 通过；design-parity（书架/配置/预览 10 场景）全绿
- [x] 4.4 8s 撤销跨弹窗续期：采用结果上抛书架层保存，重开工坊以 `initialUndo` 续撤销（单测覆盖状态传递）
