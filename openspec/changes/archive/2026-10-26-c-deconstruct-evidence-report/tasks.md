# Tasks：c-deconstruct-evidence-report

## 1. 后端渲染单源

- [x] 1.1 新建 `deconstruct/mdrender.py`：迁入 `_MD_LABELS`/`_CONF_CN`/`_DIM_LABEL_OVERRIDES`/
      `_md_cell`/`render_md`（原 `_render_md`），新增 `EVIDENCE_KEYS` 剥除、条目/节空守卫、
      列表值「；」连接、页脚退役；新增 `render_evidence(dim_name, data)` 证据视图与
      `md_map_from_products(products_raw)`（data 现渲染、缺失回退存量 md）。
- [x] 1.2 新契约键补中文标签：`need` 读者需求、`transferable` 可迁移、`repro_steps` 复现步骤、
      `emotion_chain` 情绪链、`swappable` 可替换、`no_copy` 勿照搬、`item` 条目。
- [x] 1.3 `pipeline.py`：改从 mdrender 导入；产物组装不再写 `md` 键（`{dim: {file, data}}`）；
      `models/deconstruct.py` docstring 存储形状同步。

## 2. 后端读取侧与端点

- [x] 2.1 `service.py`：`products_of` 走 `md_map_from_products`；`task_view` product_meta
      size 取现渲染长度。
- [x] 2.2 `apply.py`：`_md_map` 改走 `md_map_from_products`（导出 md 与预览同口径）。
- [x] 2.3 `router.py`：`GET /tasks/{task_id}/evidence`——鉴权/归属同预览端点；非完成态与
      无产物返回 `dims: []`；只下发有证据内容的维度。

## 3. 前端

- [x] 3.1 `deconstructApi.ts`：`DeconstructEvidence` 类型＋`getDeconstructEvidence`。
- [x] 3.2 `TaskDetailPage.tsx`：完成态按钮行加「证据报告」；证据弹窗（维度分组＋head＋证据
      单元格＋空态），加载/失败/过期响应守卫同预览弹窗；结果目录头与页脚 hint 提证据去向。
- [x] 3.3 工具页样式追加（证据行/组头），存量类优先不新造轮子。

## 4. 测试与门禁

- [x] 4.1 后端：渲染去证据（含页脚退役/条目空守卫/列表值 join）、render_evidence 形状、
      evidence 端点（归属 404/空态/存量任务现渲染）、导出与预览同口径、产物不落 md。
      更新既有 `_render_md` 断言（import 换 mdrender）。
- [x] 4.2 前端 vitest：按钮显隐（完成态）、弹窗分组渲染、空态、失败 toast；更新存量
      toolsDetail 断言。
- [x] 4.3 后端 pytest 全量＋ruff；前端 vitest --coverage 全量；`openspec validate
      c-deconstruct-evidence-report`。

## 5. 收尾

- [x] 5.1 openspec sync delta 进主 spec＋移档 archive（随实现 PR 同批）。
- [ ] 5.2 PR 描述：Why（用户 10-26 实拆反馈）＋现渲染判据＋消费面核实（建书吃 data 零影响）。
