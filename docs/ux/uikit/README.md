# uikit — C 端统一组件候选集

回答一个问题：**《统一设计语言规范》里定义的组件词汇，代码里有多少是现成的？**

> 2026-09-11 增补：#347（genre-signup-redesign）沉淀的「改动回执族」（缺口 7）与
> 「就地展开级联选择器」（缺口 8）入库，配套 CSS 第 5/6 段；现网实现分别在
> `src/components/novel/settings/ChangeReceipt.tsx` 与 `GenreSettingForm.tsx`（01 格内嵌），
> 均属「质量够但被锁死在 settings/ 下」，首个第二使用者出现时按 §四 搬运。

结论分三层：

| 层 | 情况 | 结论 |
| --- | --- | --- |
| React 级 | 5 个高质量原语已在全站复用 | **直接用，不要另造** |
| CSS 级 | 约 10 个类只有样式没有组件封装 | 能用；其中几个该补一个薄壳 |
| 缺失 | 状态点锁死作用域、胶囊零基类、confirm 走原生、撤销/空态各写各的 | **真正的缺口就在这一层** |

本目录是缺失层的「可搬运实现」，**不是要新建一套并行体系**——每个文件都建立在你已有的事实上（`Modal` / `toast` / `icons` / `base.css`），API 口径照抄现网用法。

---

## 一、已经现成的（不要重做）

### React 级原语

| 组件 | 位置 | 提供 | 备注 |
| --- | --- | --- | --- |
| `Modal` | `src/components/design/Modal.tsx` | portal、焦点圈、Esc、`locked`、`hideClose`、`headExtra/afterTitle/footer` 插槽 | 全站 30+ 调用点共用，一致性最好 |
| `toast` | `src/lib/toast.tsx` | `error/success/info` + `action` 按钮，底部居中暗色胶囊，`aria-live` | 单例模块 + `Toaster` 挂载一次的模式 |
| `Ico` + `P` | `src/components/icons.tsx` | 38 个登记 path + 供应商图 | 唯一图标来源，尺寸由父级类控制 |
| 表单字段族 | `src/components/novel/settings/FormField.tsx` | `Field`(含 AiFill)/`InputField`/`ListEditor`/`Cfg`/`SettingSaveHandle` | **质量够但被锁死在 settings/ 下**，设定以外没人敢用 |
| `UndoToast` | `src/components/api-config/UndoToast.tsx` | 8 秒撤销窗口、过期回调、fade 态 | 全站唯一软删除范式，值得泛化到 L1/L4 删除 |
| `ChangeReceiptBar`/`RestoreHint` | `src/components/novel/settings/ChangeReceipt.tsx` | 脚部回执+一步撤销、字段失焦恢复提示 | #347 落地即三面板共用；见本目录 [`ChangeReceipt.tsx`](./ChangeReceipt.tsx) 通用化候选（缺口 7） |
| `AiSink` | `src/components/novel/settings/AiSink.tsx` | AI 建议落格下方 + 历史 5 条切换 + 采纳才写回 | 形态已被简介/题材验证两次，值得泛化；暂不收副本（API 还在演化） |

### CSS 级类（有类、无封装）

| 类 | 位置 | 说明 |
| --- | --- | --- |
| `.btn-primary/-secondary/-ghost/-danger` + `.btn-sm/-xs/-lg` | `base.css` | 按钮档位齐全；`.btn-danger-ghost` 却住在 `book.css:391`，应上移 |
| `.input` / 表单字段组 | `base.css` | 含 focus 圈与禁用态 |
| `.empty` / `.empty-tree` / `.empty-search` | `base.css` / `book.css` | 空态容器三种变体已分好用途 |
| `.notice`（默认 warn）+ `.notice.info` | `list.css:50-54` | **只做了两档语气**（见缺口 3） |
| `.save-state .saving/.saved/.dirty/.failed` | `book.css:138-143` | 保存四态配色已定义，聚合逻辑却只在 `ChapterWorkspace.tsx:428-434` 手写一遍 |
| `.ch .dot-empty/.dot-warn/.dot-ok` | `book.css:97-100` | **三态点的类名正确，但作用域被 `.ch` 锁死**，预览/Rail/归档列表想复用就得抄一份 |
| `.chip` / `.chip.on` | `book.css:320-322` | 可点击胶囊（选中态）——注意这和静态 Pill 是两个东西 |
| `.cnt` / `.text-btn` / `.icon-btn` / `.genre-tag` / `.free-hint` / `.pill-pro` | 各 css | 都是稳定的单用途小件 |

---

## 二、缺失的（本目录补齐）

| # | 缺口 | 为什么该抽 | 文件 |
| --- | --- | --- | --- |
| 1 | **胶囊家族**：13 种实现零共享基类（连 `.pill` 这个类都没有 CSS 定义），padding 与字号在 10–12.5px 间漂移 | 已经发生的口径漂移，不是推测需求 | `Pill.tsx` |
| 2 | **StatusDot 三态点 / SaveState 保存四态**：状态语言是规范核心，但现在各屏要用就得重画一遍；保存态还在 `OutlineTree`/`Rail` 之外没有第二个使用者 | 同一对象同一套状态语言（规范 N5），且 ChapterWorkspace 已有一份要抄的实现 | `Status.tsx` |
| 3 | **Notice 语气不全**：只有 warn/info 两档；「操作成功」「不可逆阻断」都在借用别家颜色（卡片菜单危险项误用 warn 是现存例子） | 补齐四语气即可让 N6（红=不可逆）成立 | `Notice.tsx` + `uikit.css` 第 3 段 |
| 4 | **EmptyState 解剖**：每个空态手写一份说明和按钮排布，「必须有出路」的原则只能靠自觉 | 每处空态结构同构，且现在是缺失一致性最高的地方之一 | `EmptyState.tsx` + `uikit.css` 第 4 段 |
| 5 | **ConfirmGuard**：5 处 `window.confirm` 绕过 Modal 体系（原生框不可主题化、不能放盘点 chips、和自研弹窗并存在同一动作流里） | 一次替换消灭全站最大的视觉破口 | `Confirm.tsx` |
| 6 | **`dot-*` 全局化**：不需要新类，只需把 `book.css:97-100` 三行的 `.ch` 前缀去掉 | 复用而不新增词汇 | `uikit.css` 第 2 段 |
| 7 | **改动回执族**：一键覆盖类动作（胶囊/勾选/滑块松手/AI 采纳/设为当前）改完不留痕、退不回；自己敲的字又会被脚部刷屏 | 设定是 AI 写作的输入，改错不当场报错、只让后面每章越写越差；按**改动来源**分级（一键覆盖→脚部回执，手敲→失焦恢复提示），不做查看/编辑模式 | `ChangeReceipt.tsx` + `uikit.css` 第 5 段 |
| 8 | **就地展开级联选择器**：两级目录选择（大类/子类）此前没有范式，TDesign 式浮层在 overflow 容器里被裁切漂移 | 「浏览≠选中」是用户报障换来的裁决；搜索要按解读/案例命中而非只按名；就地展开是 overflow 容器里的唯一正解 | `Cascader.tsx` + `uikit.css` 第 6 段 |

配套样式集中在 [`uikit.css`](./uikit.css)，共 4 段，全是补丁性质。

---

## 三、文件清单与公开 API

```ts
// Pill.tsx
<Pill role="tag|status|count" tone="neutral|ok|warn|err|accent">文本</Pill>

// Status.tsx
<StatusDot state="unfilled|in_progress|confirmed" title="未填" />   // title 必传，这是三态点唯一的解释通道
<SaveState state="autosaving|unsaved|failed|saved" onRetry={fn} />

// Notice.tsx —— 语气词表已按 ../cross-end.html §3.2 改齐为全站统一四元组
// （与 S端 .strip、dot-ok/dot-warn、toast.err 同词；原 success/danger 作废）
<Notice tone="info|ok|warn|err" desc="副句"
        action={{ label: "去配置", onClick }} onClose={fn}>
  主句
</Notice>

// EmptyState.tsx
<EmptyState icon={P.search} title="还没有角色档案" desc="一句话说清这里会用来干什么"
            primary={{ label: "新建角色", onClick }}
            secondary={{ label: "先去写正文", onClick }} />

// ChangeReceipt.tsx —— 脚部渲染 <ChangeReceiptBar receipt={receipt}/>（回执左、主按钮右）；
// 宿主用 useEffect(() => setReceipt(null), [panel]) 统一清（四条跳转路径漏三条=死撤销），
// 保存成功后也必须清（撤销只能改内存，与库不一致）
const { record: recordChange } = useChangeReceipt(onReceiptChange);
recordChange(
  "已把吃苦指数从 8 调到 6",       // 作者视角的一句话（超长自动截断，title 看全文）
  () => { /* 值已由调用方落地 */ },
  () => setData((cur) => ({ ...cur, cost_ratio: 8 })),  // 差量回退；可 async，抛错保留回执
);
<RestoreHint show={textHint} onRestore={restore} />  // 自己敲的字：失焦后字段下轻提示

// Cascader.tsx —— 就地展开两级选择（浏览≠选中 / 搜索按解读命中 / clearable）
<Cascader
  groups={[{ name: "仙侠/修真", desc: "修行阶次…", items: [{ name: "凡人流", desc: "资质平平…", extra: "案例：《凡人修仙传》" }] }]}
  value={{ group: "仙侠/修真", item: "凡人流" }}
  onChange={(v) => patch({ theme: v.group, sub_genre: v.item ?? "" })}
  onClear={clearTheme}
  placeholder="选择题材"
/>

// Confirm.tsx —— 需要在 ClientShell 与 <Toaster/> 同层挂载一次 <ConfirmHost/>
await confirmAction({ title: "删除这个配置？", tone: "danger",
                      inventory: ["3 本书正在使用它"],
                      confirmLabel: "删除", cancelLabel: "取消" });
// 返回 true 才继续执行，彻底替代 window.confirm
```

---

## 四、采用顺序（务必走既有流程）

1. **原型先行**：把 `uikit.css` 各段贴进 `docs/design-c/prototypes/*.html` 对应原型核对视觉，改动记进 `ADJUSTMENTS.md`。
2. **CSS 收编**：并入 `src/design/base.css`；同时删掉 `book.css:97-100` 原 `.ch .dot-*` 三行（防止出现 `.spin` 那种同名双定义漂移——本项目真实踩过）。
3. **组件搬运**：六个 tsx 复制到 `src/components/ui/`；`ConfirmHost` 挂到 ClientShell（与 `Toaster` 同层、挂载一次）。
4. **调用点迁移**：
   - 胶囊按映射表逐个换 `Pill`（每屏一批次，跑 `design:check`）；
   - 5 处 `window.confirm` 换 `confirmAction`，e2e 里 settings-forms / modals 相关断言同步改。
5. 全绿标准不变：`npm run design:lint` + `npm run design:check` + `tsc --noEmit` + 相关 e2e。

## 五、迁移映射表（旧写法 → 新 API）

| 现有 | 新写法 |
| --- | --- |
| 书卡阶段徽 `.b.ok`「已归档」/ `.badge` 五变体 | `<Pill role="status" tone="ok">已归档</Pill>` |
| modnav 计数 `.cnt` `{n}/{total} 章纲` | `<Pill role="count">3/12 章纲</Pill>`（继承 `.num`） |
| 题材标签 `.genre-tag` / 导入结构标签 `.arch-tag` | `<Pill role="tag">东方玄幻</Pill>` |
| 「可后补」`.defer-tag` / AI 标 `.ai-tag` | `<Pill role="tag" tone="accent">AI</Pill>` |
| 「已自定义/已润色」 vs 「自动组装」 | `tone="warn"` ↔ `tone="ok"`（同一对语义翻面） |
| 章纲缺项 `.gap-chip`、删除盘点 `.inv-chip` | **不改**——它们是可点击的按钮，属于 `.chip` 家族；盘点 chips 在 `Confirm` 里由 `inventory` 数组接收 |
| `ChapterWorkspace.tsx:428-434` 保存四态 | `<SaveState state={…} onRetry={retry} />` |
| 5 处 `window.confirm("…确定继续吗？")` | `await confirmAction({ … })` |
| 题材面板 01 格（`GenreSettingForm.tsx` 内嵌 sel-* 实现） | `<Cascader groups={THEME_CATALOG} …/>`（第二使用者出现时搬 `src/components/ui/`） |
| 三面板脚部回执（settings/ChangeReceipt.tsx） | 搬 `src/components/ui/` 后 `import { useChangeReceipt, ChangeReceiptBar } from "@/components/ui"` |

## 六、明确不建议抽象的（省下的是真钱）

- **Button / Input 包装组件**：CSS 档位已齐全且语义清晰，包一层只会让 IDE、grep 和 `design-lint` 同时失明。类名即 API。
- **Tabs / Segmented 封装**：modnav/页签/`.seg` 三处形态差异是真的，强行统一会逼出 config 参数地狱。
- **Field 字段组件搬到 ui/**：先把 `settings/FormField.tsx` 的导出路径开放出去就够了，等第一个非设定场景真实使用再谈搬家（不为只用一次的代码做抽象）。
- **Mod 五格卡（编号+怎么填+成书去处）**：它是设定页的叙事骨架，不是通用控件——每个格的「为什么/填好后」都是业务文案，抽成组件只会把文案搬进 props 地狱（#347 实测）。
- **PointChooser 多看点勾选器**：为「AI 给多看点勾选采纳」这一个场景而生，勾选态必须由它自持（结果节点缓存在 sinks state 里，外部勾选态会渲染成点了没反应）——场景唯一、生命周期与 AI 结果绑定，泛化收益为零。
- **带浮例句的滑杆（cost-slider）**：档位语义（1 流汗破财…10 命抵江山）全是业务词汇，通用滑杆=原生 input range + accent-color 就够。

判定标准就是仓库里那条：「如果资深工程师会说这过度设计了吗？」——上面三个都会。

## 七、与规范的对照

| 规范条目 | 由谁兑现 |
| --- | --- |
| §5 状态语言总表 | `Status.tsx`（几何）＋ `Pill.tsx`（徽标形态） |
| §6.1 按钮 | 不动，沿用 base.css 现状 |
| §6.2 胶囊家族 | `Pill.tsx` ＋ `uikit.css` 第 1 段 |
| §6.4 Notice 四语气 / Empty 解剖 / ConfirmGuard | `Notice.tsx`（语气=info/ok/warn/err，跨端同词表） / `EmptyState.tsx` / `Confirm.tsx` |
| §11 门控锁定可见 | `Pill` 提供 `lock` 徽（`P.lock`），整卡降透明沿用现有 `.rail-locked` 做法 |
| §12 删除分级 L1–L4 | `Confirm.tone="danger"` + `inventory`；L4 撤销仍用现 `UndoToast`（后续可把它挪进 ui/ 泛化参数） |
| 「改了知道、改错退得回」（#347 新增口径，design-language 状态语言的动作侧补充） | `ChangeReceipt.tsx`（一键覆盖→脚部回执；手敲→`RestoreHint` 失焦提示）；布局纪律见 `uikit.css` 第 5 段注释 |
| 表单控件·封闭目录选择（新增） | `Cascader.tsx`（就地展开、浏览≠选中、搜索按解读命中） |

可视化对照与交互演示见 [`../components.html`](../components.html)。
