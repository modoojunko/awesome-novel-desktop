# Tasks：c-zhuque-mark-band

## 1. 前端：带分组与渲染

- [x] 1.1 `zhuqueMarks.ts` 新增带分组（数组相邻同 label 聚合；产出 `tailOfBand` 集合＋label 查询，doc 遍历原样保留按位置消费）
- [x] 1.2 decorations 按带渲染：底色逐段挂（warn/err 现状 CSS）、章只在带尾；`markWidget` 改判定词文本；人写章分支删除；带内着色段 node decoration 挂 `title="判定 百分数"`（悬停置信度；`.zq-mark` pointer-events 不动）
- [x] 1.3 stale＝现状语义：带内段挂 `zq-stale`（无底色）、带尾章 `.stale` 变体、人写带零渲染；删除 `book.css:1929` 死选择器（`.zq-stale.zq-warn/.zq-err`）

## 2. 测试与设计纪律

- [x] 2.1 `zhuqueWorkbench.test.tsx` 四处旧视觉钉改写＋新增：连续 4 疑似段带尾单章、悬停 title 含百分数、人写带零渲染、stale 人写带零渲染、段数少于 segments 越界守卫
- [x] 2.2 后端防回归钉两根（`test_zhuque.py`）：容错层用例显式断言 `paragraph_index` 连续；空 `seg_labels` → `segment_mismatch`
- [x] 2.3 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记三处视觉语义变更（带尾单章/人写静默/置信度悬停）＋原型 book.html 标注示意同步＋`book.css` 1929 删除登记
- [x] 2.4 vitest 全绿＋`npx tsc --noEmit && npm run build`

## 3. 验收

- [x] 3.1 `openspec validate c-zhuque-mark-band --strict` 过
- [ ] 3.2 隔离栈跑 `e2e/zhuque.spec.ts`（36-38 断言按带语义核对，必要时修订＋注释）；真机：第 3 章检测——黄/红底色带连续、带尾单章、人写段干净、悬停见百分数、编辑后整带置灰＋重检恢复、带尾行尾点击/拖选无截获
- [ ] 3.3 流程注记：建议与 `c-zhuque-seg-align` 同批归档（live zhuque-detection spec 与已合 f333c1de 的矛盾系 seg-align 未 sync 债，勿让本 change 先归档加深错位）
