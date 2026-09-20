## Context

storyline 皮肤（`book.css` storyline 皮肤段）为卷/章页引入两条归零规则：

```css
.wb .view.on.three-col .col-panel { padding: 0; background: var(--surface); }
.wb .view.on.three-col .panel { max-width: none; }
```

选择器命中书内**所有**三栏视图（含 settings-v）。卷/章域随后以 `.e-pad(18px 22px 24px)`＋头部 `e-head(16px 22px 13px)` 逐段补回；其余面板无补偿 → 2026-09-20 普查实测 8 处缺陷（设定页 8 面板衬垫 0、写作空态衬垫 0 且版心 924、章页签 操作/文风/角色关系衬垫 0、章纲/提示词版心靠字段 670 兜底、设定 22/伏笔 16 与章纲 48 不一致）。原型真值：book.html `.col-panel{padding:28px clamp(20px,4vw,48px) 60px}`＋`.panel{max-width:660px}`＋`.og-pane/.prompt-pane{padding:26px clamp(20px,4vw,48px) 60px}`；storyline `.e-pad{18px 22px 24px}`；genre-signup `.col-panel{padding:26px clamp(20px,3.5vw,44px) 30px}`。

## Goals / Non-Goals

**Goals:**

- 节奏单源：一套变量定义内容衬垫与版心；8 处缺陷一次修复；新增面板自动继承。
- 不动正常处：卷视图 `.e-pad`、正文阅读区 `.editor(680 居中)`、预览页、书架。

**Non-Goals:**

- 不重设设计与原型文件（本次为追平原型既有口径）；不改 tsx 结构（仅 class 复用与 CSS）。
- 不统一设定域与编辑域两套节奏值（book.html 26/clamp/60 vs storyline 18/22/24 各有原型出处）——两值均为单源变量，域内一致即达标；値を合并留待设计侧裁决。

## Decisions

1. **变量定义**（`.wb .view.on.three-col`）：
   ```css
   --col-pad-t: 26px; --col-pad-x: clamp(20px, 4vw, 48px); --col-pad-b: 60px;
   --col-pad-editor: 18px 22px 24px;
   --col-measure: 76ch;
   ```
2. **删除归零对**（1355-1356）：`.col-panel { padding: 0 }` 保留（通栏条依赖它），但**所有内容型面板**改为单源衬垫；`.panel { max-width: none }` 改为「默认 660 ＋显式豁免」：
   ```css
   .wb .view.on.three-col .vol-shell .panel { max-width: none; }   /* 卷壳豁免（76ch 字段自带） */
   ```
   （`sub-fill`/settings-v 1180 的豁免已有既有规则。）
3. **应用点**：
   - `.wb .view.on.three-col .settings-pane, .style-pane, .relations-pane, .actions-pane, .hooks-wrap { padding: var(--col-pad-t) var(--col-pad-x) var(--col-pad-b); }`
   - `.settings-v .panel { padding: var(--col-pad-t) var(--col-pad-x) var(--col-pad-b); }`
   - `.settings-v .panel > .panel-head, .settings-v .panel > .panel-foot { margin-inline: calc(-1 * var(--col-pad-x)); padding-inline: var(--col-pad-x); }`（通栏条出血＋文字对齐）
   - `.e-pad { padding: var(--col-pad-editor); }`（值不变，纳入单源）
   - 内容型 pane 的直接子行（文风表单行/操作卡片等）`max-width: var(--col-measure)`（修复 838px 铺满）。
4. **面板版心**：写作空态 `.panel` 恢复 660（依赖删除归零）；og-pane/prompt-pane 内 `.panel` 同回 660；设定域 1180 不动。
5. **验证回路**：复用普查脚本（建临时书→逐面板实测衬垫与内容 x/最右）作为修复证据；e2e 回归加断言（workbench-features 或新用例：设定面板内容距栏左 ≥40px、章/操作卡 ≤76ch）。

## Risks / Trade-offs

- **子选择器命中不准**：文风/操作行的 DOM 层次需实测收敛（首版跑普查脚本迭代）。
- **sub-fill 双栏分隔线会随衬垫内缩**（此前贴栏）——更贴近原型列衬垫口径，登记 ADJUSTMENTS。
- **e2e 位置断言**：现有 e2e 对 workbench 多为行为断言；layout 变化若有坐标断言（#445 曾用 Y 坐标相等断言页签条）需复跑全量确认。
