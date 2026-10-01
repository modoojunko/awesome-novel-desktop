# Design：c-zhuque-mark-band

## D1. 聚合算法（唯一新逻辑，纯前端）

`zhuqueMarks.ts` 装饰构建前先做**带分组**：

```
bands = []
for (k, seg) in segments（数组序，后端契约保证 paragraph_index 连续 0..N-1）:
  if bands 非空 且 末带.label == seg.label:
    末带.append(seg)          # 数组相邻即同带——与渲染位置消费同轨，单一真相源
  else:
    bands.append([seg])
```

- **分组键＝数组邻接**（评审 P3-5 采纳）：与插件 `state.doc.forEach` 位置消费 `segs[k]` 同一真相源，契约漂移不会双轨静默错位。
- **连续性前提锚点**（评审 P3-1 采纳）：`align_segments` 逐段 `enumerate` 输出（构造性保证）＋ spec zhuque-detection「paragraph_index 按非空段顺序 0 起编号」条款＋ `tests/test_zhuque.py:238/280` 双测试钉。空段天然不在 segments（`split_paragraphs` strip 谓词），不打断聚合。
- label 0（人写）同样成带，但渲染分支直接静默——语义统一，代码不分叉。
- 单段带自然退化为现状形态（一段一底色一章）。

## D2. 渲染分支（decorations 构建改动）

现状 doc 遍历**原样保留**（评审 P2-1 采纳：不做「按 bands 遍历」——doc 位置只有遍历知道）；分组产出两个查询结构供遍历消费：

- `tailOfBand: Set<number>`（各带末位的 paragraph_index）——`tailOfBand.has(seg.paragraph_index)` 决定挂不挂章；
- `seg.label` 决定底色与章语气。

| 带 label | 底色（node decoration，逐段） | 章（widget decoration） |
|---|---|---|
| 1（AI） | `p.zq-err` 每段挂 | **带尾段**一个 `.zq-mark.m-err`，文本「AI」 |
| 2（疑似） | `p.zq-warn` 每段挂 | **带尾段**一个 `.zq-mark.m-warn`，文本「疑似」 |
| 0（人写） | 不挂 | 不挂（现状灰章分支删除） |

- **悬停＝段落级 `title` 属性**（评审 P1-3 采纳，弃 pointer-events 方案）：node decoration attrs 挂 `title: "疑似 62%"` 到带内每个着色段——零 CSS 变更、无 caret 截获/拖选回退、带内每段都可查（不只章上）。`.zq-mark` 的 `pointer-events: none` 保持不动。
- `markWidget` 签名收窄：`text`（判定词）替换现「label 前缀＋常驻百分数」拼串；`title` 不再走 widget。
- **stale＝维持现状语义**（评审 P1-1 拍板）：现状 stale 分支只挂 `zq-stale` 单类、段落无底色（`book.css:1929` 复合选择器永不命中＝死 CSS），置灰只发生在章上。带化后同构：带内段挂 `zq-stale`（无底色）、带尾章 `.stale` 灰变体、人写带 stale 下同样零渲染。`book.css:1929` 死选择器同批删除＋ADJUSTMENTS 登记。
- 章 `contenteditable=false`＋`ignoreSelection` 保持纯观察，撤销历史/导出不沾——带化不改变这些性质。

## D3. 不动项与边界

- 后端/契约/对齐制零改动；`position`/上游字段从未透出，前端不依赖。
- 底色 CSS（`book.css:1927-1928` 荧光笔式）零改动；**本次 CSS 唯一变更是删除 1929 死选择器**（清理性质，无视觉变化）。
- 带不跨章（装饰作用域天然单文档）；结果条、右栏检测行、开关、缓存存续全部不动。

## D4. 测试改造点

- `zhuqueWorkbench.test.tsx` 四处旧视觉钉改写：33「人写只灰章」→无章无底色；38/39 章 3→带数、文本「AI 86%」→「AI」；47 stale 3 章→非人写带数（SEGS 三段三带全保留判定但人写带静默→2 章）。新增：连续 4 疑似段带尾单章、悬停 title 含百分数、人写带零渲染、stale 下人写带零渲染（P3-1）。
- **e2e**（评审 P1-2 修正）：`client/frontend/e2e/zhuque.spec.ts:36-38` 钉了 `.editor p.zq-warn`/`.zq-mark` 首个可见——带化后底色逐段保留＋带尾章存在，预计仍绿但**必须隔离栈实跑核对**，用例注释补带语义说明；不基于「无钉」假设跳过。
- 越界守卫 `if (!seg) return`（段数少于 segments 时）现状无回归钉，带化后仍依赖它——补一例（评审总评缺口 2）。
- 后端两根廉价钉（评审 P3-1 采纳）：`test_zhuque.py` 容错层用例显式断言 `paragraph_index == [0,1,2,3]`；空 `seg_labels` → `segment_mismatch` 用例。防前端带算法的连续性前提被未来后端改动无声打破。
- 仓库门禁：`npx tsc --noEmit && npm run build`（评审 P2-2 采纳）。
- design:lint 不查此类变更、design:check parity 不含 workbench 屏（评审已核）——无自动兜底，靠 ADJUSTMENTS 登记＋真机验收。
