## 1. 前端实现

- [x] 1.1 `OgPane.tsx`：`archived` prop（props 注释引 c-og-archived-readonly＋后端 409 依据）；查看态门改 `!editing || archived`；查看态动作区（撤回确认/去写正文/确认章纲/编辑章纲）`!archived` 条件渲染。验证：单测「归档查看态四入口不在场、一页纸本体保留」「编辑态残留强制回查看态」过
- [x] 1.2 `ChapterWorkspace.tsx`：prose 分支只读横幅提取为 `archivedBanner` 常量（文案/结构逐字保留），`chTab === "og"` 同挂；OgPane 传 `archived={archived}`；`startOgEdit`/`editAndFlash` 归档短路。验证：集成「归档章横幅＋恢复编辑在场、四入口不在场」「缺口 chip 哑火（无保存草稿表单）」过

## 2. 测试

- [x] 2.1 vitest 单测：`ogPane.plotEdit.test.tsx` Host 扩 `archived`/`confirmed`/`onUnconfirm`，新增「归档章章纲只读」组 2 用例；全量 `npx vitest run` 1164/1164 绿（101 文件），tsc --noEmit 零错
- [x] 2.2 vitest 集成：`chapterWorkspace.plotFlow.test.tsx` mount 加 `archived` opt（每次挂载新建 wb 桩不污染模块级），新增组 2 用例
- [x] 2.3 e2e 断言：`free-writing-flow.spec.ts` ⑥ 免费归档流搭车——归档后切章纲页签，断言 readonly-banner＋恢复编辑在场、og-view 在场、确认章纲/og-edit 不在场（`toHaveCount(0)`）
- [ ] 2.4 e2e 隔离栈实跑（全量回归：modals-pr5 ② 解锁后 og-edit 可见属 unarchive 后场景不受影响、chapter-rewrite 开归档章仅查页签可见性不受影响——均已人工核对无冲突；实跑随 CI/真机验收）

## 3. specs

- [x] 3.1 delta：workbench「章纲页签查看/编辑两态」MODIFIED——新增归档恒只读条款＋归档场景；既有 SHALL 与 7 场景逐字保留。验证：`openspec validate c-og-archived-readonly --strict` 过
- [ ] 3.2 归档批 sync 回主 spec（随归档 PR，本仓惯例实现/归档分批）
