## 1. 原型先行（ADJUSTMENTS 登记制）

- [x] 1.1 重铸三屏 appbar：`list.html` / `book.html` / `model-config.html` 顶栏动作区统一收敛为头像胶囊唯一入口；`list.html` 设置弹窗段落替换为控制中心面板段（账号区头/数据组/模型配置/支持组/退出登录+版本行；工作台语境含「本书偏好」项）
- [x] 1.2 核对 `book.html` 本书偏好弹窗既有「归档 AI 摘要」seg（seg-archsum）保留不动；`ADJUSTMENTS.md` 登记本批条目（登记号顺延）；design-language §13 tier 对照表回填短档口径（PRO 会员/试用·剩N天/免费版）
- [x] 1.3 词汇表 lint 与像素 parity 自查过（含 SVG 描边 1.7 与 draft 1.8 的归一或豁免留痕；图标入 icons.tsx 注册表——person 图标新增、caret 复用 chevronDown）

## 2. AcctMenu 组件与徽章口径

- [x] 2.1 新建 `AcctMenu` popover 组件（portal 挂载+fixed 定位换算、右对齐 280px、Esc 回焦/外点关闭（白名单含触发钮防双触发）/方向键循环焦点不逃逸、aria-haspopup/aria-expanded、稳定 data-od-id），按稿 token 逐字
- [x] 2.2 抽共享文案模块 `lib/tier.ts`：tierLabel 完整档（优先级 expired → trial → is_member → 免费版）+ 四态短档映射（≤3 天含 0 天转 warn）；AcctMenu 与 BookPrefsModal 共同消费，会员文案统一「PRO 会员」（BookPrefsModal 归一）；S端失联（前端同步失败信号）文案保持既有档位仅转 warn、恢复自动回色；`entitlement_degraded` 不作为徽章信号
- [x] 2.3 触发钮头像：用户名首字，取不到退化人形图标（icons.tsx 注册）；用户名 >12ch 截断悬停全文
- [x] 2.4 面板菜单项接线：备份/恢复走既有 bridge 流程（RestoreModal 随迁，`onGoConfig` 闭包改为关面板+跳配置）、模型配置跳 `#/config`、联系客服走 `supportUrl()`（portal 单源、`target="_blank"` 锚点、无地址不渲染）、版本行复用应用级缓存失败静默「版本未知」；工作台语境增挂「本书偏好」项（打开 BookPrefsModal）
- [x] 2.5 退出登录轻确认：面板内联二步确认，确认后走既有 `logout()`（回落地页），取消复位无副作用

## 3. 顶栏收敛与 PrefsModal 退役

- [x] 3.1 `Navbar.tsx` 动作区收敛：移除「联系客服」「设置」按钮，挂头像胶囊；`AcctMenu` 提升到 `ClientShell` 全局壳层，列表屏与内页共用一份实例
- [x] 3.2 `LicenseProvider` 上移到 `ClientShell` 已登录分支（`/config` 等路由徽章数据可达；保留未登录页不发 verify 门控）；修 catch 分支「失败清缓存降免费」→ 网络失败保留上次快照判定并置失联标志（对齐「绝不因网络降级会员」注释），失联标志驱动徽章变色，徽章与书架横幅口径一致
- [x] 3.3 工作台顶栏同步：移除「联系客服」按钮；原「设置」（本书偏好）入口由面板「本书偏好」项承接
- [x] 3.4 删除 `PrefsModal.tsx`；`lib/prefs.ts` 导出与回退链保留不动；核对全仓 import 清零；`design-vocab.mjs` 登记簿移除 PrefsModal、加入 AcctMenu

## 4. 测试迁移与门禁

- [x] 4.1 vitest 新增：徽章四态映射（含 0 天边界/判定优先级序）、S端失联变色且档位不变/恢复回色/不清缓存不降级、AcctMenu 交互（Esc/外点/键盘/轻确认）、BookPrefsModal 归档开关回退断言（书级未设置回退全局存量值）；`LicenseProvider.test.tsx` 随上移与失联标志补断言
- [x] 4.2 e2e：modals-pr5「设置」定位用例改控制中心面板链路（全局 seg 用例删除）；**support-link.spec.ts 重写为面板外跳链路**（含 portal_url 为空不渲染、未登录不出现两条既有口径迁移）；design-parity-list / design-parity-book / design-parity-config 三屏基线重录（原型重铸后）
- [ ] 4.3 本机全量 e2e（docker 栈）+ vitest 全绿；`openspec validate` 通过

## 5. 验收走查

- [ ] 5.1 按稿验收清单走查：顶栏单入口、面板结构齐全（工作台语境含本书偏好）、外链纪律、键盘可达、四态徽章（PRO/试用充裕/试用临期含 0 天/免费版含过期）、S端失联变色保持档位且恢复回色、退出轻确认、`/config` 页徽章不翻车
- [ ] 5.2 docker 栈重建后人工核验 5174 实机（含工作台与模型配置页），核对原型-实现 parity 与截图留档
