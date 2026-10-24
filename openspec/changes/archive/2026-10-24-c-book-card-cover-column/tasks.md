## 1. 原型先行（硬性流程：先原型后实现）

- [x] 1.1 `docs/design-c/prototypes/list.html` 书卡改两列形态：左列 104px 3:4 封面/占位列＋右信息列（照 drafts 原型 .gl-book-card 尺寸节奏：padding 16、gap 16、h3 19px、stats/foot 收紧、≤820px 收 88px），有封面/无封面有章节（占位按钮「生成封面」）/0 章（不可点「可稍后添加」）三态齐全；验证＝浏览器打开三态截图与 drafts 原型 05-shelf-applied.jpg 对拍
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记本轮偏差与拍板出处（§4.3 拍板 C；0 章占位不可点、菜单「封面…」第二入口、来源行文案口径）；验证＝条目可溯源到设计说明章节号

## 2. 实现落笔

- [x] 2.1 `ImageWorkshopModal.tsx` 画风词表导出为 `IMAGE_STYLES`（工坊内部改用同一来源）；验证＝tsc 全绿、工坊画风下拉不回归
- [x] 2.2 `NovelListPage.tsx` 书卡结构重排：左列 `.book-cover`（ImageThumb 或占位按钮/不可点占位＋悬浮 `.cover-act`「换封面」）＋右列 `.book-main`（顶行胶囊/标题/简介/统计/页脚/`.cover-meta` 来源行）；⋯ 菜单第一项加「封面…」（stopPropagation 防误开书，占位/悬浮同）；44×44 `.cover-wrap`/`.cover-edit`/`.book-cover-img` 退役；验证＝tsc 全绿
- [x] 2.3 `list.css` `.book-card` 改两列 grid＋右列节奏收紧；`image-assets.css` 落 `.book-cover/.cover-empty(.is-later)/.cover-act/.cover-meta` 与 ≤820px 88px 缩放，删 44px 旧样式；验证＝design:lint 通过、无未登记新词
- [x] 2.4 来源行文案映射：source=upload→「本地上传」；其余→「AI 封面 · {IMAGE_STYLES[style_key] 或降级『AI 封面』}」；无封面→「封面位留给作者」；验证＝单测三态断言

## 3. 测试改钉与回归

- [x] 3.1 `novelListPage.test.tsx` 按新形态改钉：两列结构/占位按钮开工坊/0 章占位不可点/悬浮换封面/菜单「封面…」第一项/来源行三态；验证=`vitest run` 全绿
- [x] 3.2 `e2e/image-workshop.spec.ts` 入口选择器由「添加封面」改「生成封面」（占位块）路径，全链（上传→候选→采用→书架可见→撤销→再采用）复跑；验证＝隔离栈 e2e 绿
- [x] 3.3 parity 基线同步：design parity 书架场景重录对拍，其余场景确认零漂移；验证＝design:check 全绿（存量已知红除外，需 A/B 定罪）
  - 证据：design-parity 8/8 绿（books/group/empty-filter/empty/finish/quota/pagination＋preview），阈值 0.2% 内零红；原型与应用两列书卡逐像素一致（长夜灯 0 章 is-later 占位在 books 场景内覆盖）

## 4. 收口验证

- [x] 4.1 前端四件：`tsc`＋`vitest run`＋`npm run build`＋`design:lint` 全绿；验证＝本地命令输出
  - 证据：tsc 零错；vitest 1795/1795（143 文件）；build 含 check-inline-colors 通过（legacy-colors 227.5KB 再生）；design:lint 绿（原型 data-URI 封面改 SVG 命名色过严格范围）
- [x] 4.2 隔离栈真机走查：有封面/无封面有章节/0 章/待完本/已完结五态书卡＋窄屏（≤820px）缩放各截一张，对拍 drafts 原型；验证＝截图对拍无版式漂移
  - 证据：隔离栈（vite 5174＋独立容器后端 18000＋/tmp 数据目录）实拍 `walkthrough/wt-1..4.png`——有封面（本地上传来源行）／有章节占位（生成封面 CTA）／0 章弱化（可稍后添加）＋悬浮「换封面」＋窄屏 88px 收缩；待完本/已完结页脚行未改动、由 parity group/finish/已完结场景像素钉住
- [x] 4.3 归档 sync 同 PR 清理：主 spec `cover-avatar` 内历史遗留的双前缀头（`### Requirement:### Requirement: …`）统一清为单前缀（纯标题改动，scenario 不动）；验证＝`openspec validate` 无 INFO、sync 后主 spec 头格式统一
  - 证据：sync 落主 spec（MODIFIED 工坊入口措辞＋ADDED 书卡封面版式 7 scenario）；清 9 个双前缀头；`openspec validate --specs` 68 passed / 0 failed

## 5. Review 整改（2026-10-24，PR #943 review 两 P2）

- [x] 5.1 窄屏 88px 失效修复：媒体查询宽度收窄落 image-assets.css 基础规则后（main.tsx 加载序 list.css 先行，轨道/宽度必须分文件同位对齐）；原型同病同修（820 规则挪到 .book-cover 基础规则之后）；验证＝级联实测 780px 轨道 88/宽 88/gap 16 双侧一致＋e2e 窄屏几何钉（expect.poll 等壳层 page-enter 0.4s 入场动画收敛后断言，量早了会吃到 scale 0.98 中间态）
- [x] 5.2 书卡 Enter 冒泡修复：卡片 onKeyDown 加 `e.target === e.currentTarget` 守卫（内部按钮 Enter 各走各的 click 语义，不再冒泡触发开书吞掉目标动作）；验证＝两键盘回归钉（占位钮/换封面 Enter 不导航＋click 开工坊；卡片自身 Enter 仍导航）＋vitest 1800 全绿
