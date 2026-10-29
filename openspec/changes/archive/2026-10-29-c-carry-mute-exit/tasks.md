## 1. 前端收口

- [x] 1.1 `NovelListPage.tsx` 常驻提醒行可见性改为 `!carryRec.suppressed && (carryLater || carryRec.carried_partial) && !carried && !carryConfirmed`，并注释「抑制只绑当前版本候选指纹，入口仍可达」。验证：`novelListPage.test.tsx` 新增「已本版静音：常驻行不渲染」「部分迁移＋本版静音：常驻行不渲染」两例
- [x] 1.2 非部分迁移行文案去掉不可达的 `?` 占位（非 partial 行只在「稍后带」后出现，卡要求书数 > 0）。验证：`novelListPage.test.tsx`「稍后带行展示源书数」一例

## 2. 测试与门禁

- [x] 2.1 改写受影响三例：静音态常驻行断言反过来、`?` 兜底例改走「稍后带」、`carryConfirmed` 收口例改走「稍后带→重开卡→完成确认」。验证：`vitest run src/__tests__/novelListPage.test.tsx` 79 绿
- [x] 2.2 全量覆盖率契约复跑（NovelListPage 属契约文件，perFile 100%）。验证：`vitest run --coverage` exit 0，1900 用例绿，NovelListPage 四项 100%
- [x] 2.3 `tsc --noEmit` 零错
- [x] 2.4 评审 P3 收口：合并重复/过时注释（「唯一提醒面」与静音后不再渲染矛盾）；`refreshCarry` 增 `force`（静音/已阅/搬运终局撞在途请求时补一发），`carryDialog.test.tsx` 加「静音强制重取：补一发新快照」用例
