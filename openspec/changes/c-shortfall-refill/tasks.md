# c-shortfall-refill 任务

> 真立项件：全部未勾，等 #843 合入后进入 apply。

## 1. 前置与原型

- [ ] 1.1 依赖确认：#843（c-scene-density）已合 main（`plot_count_hint`/`word_target_floor`/done word_check 三件就位），本分支 rebase 最新 main
- [ ] 1.2 原型先行：完成卡「补足字数」动作位（既有卡式＋warn 语气）出一版原型或按完成卡既有布局自查，登记 ADJUSTMENTS；受影响屏＝正文生成完成卡（单端 C、不触共享段）
- [ ] 1.3 apply 定形：读 `write/router.py` /write 通道与 `auxiliary` 现状，二选一（/write append 模式 vs /refill 端点）——判据＝恒定层组装与 SSE 阶段流可原样复用；结论写回 design Decision 1

## 2. 续写补足

- [ ] 2.1 续写指令行组装（append 口径：从尾接写、落点或下限先到即停、已写正文不重述）＋治理自查（无逐场配额；与收尾行 <8 公共串，扩一枚钉子）
- [ ] 2.2 续写端点：append 落库走既有保存链＋分段归一；独立计量 `write_chapter_refill` 族；双门控照生成
- [ ] 2.3 两轮封顶收口：第三轮起动作位换成「重新生成整章」引导（复用既有重生成出口）
- [ ] 2.4 前端完成卡动作位＋进行中阶段呈现；达标/仍不足/两轮收口三态

## 3. 写链遥测

- [ ] 3.1 TokenLog 加列：target/actual/below_limit/finish_reason（生成与补足两路都记）
- [ ] 3.2 档位命中现算：生成留痕时按 plot_count_hint(目标) 与实发条数记 hit 布尔（同源函数即判据）
- [ ] 3.3 聚合可查性验证：截断桶（finish_reason=length）与自愿短写桶（stop）可分离计数；命中率报表 SQL/查询口记录进本条

## 4. 回归

- [ ] 4.1 后端：pytest 全量（续写三态、免费档零调用、append 不毁稿、遥测落列、<8 治理钉）实际输出结论追加本条下
- [ ] 4.2 前端：vitest（动作位三态渲染、点击发出 append 请求体）＋`tsc --noEmit`；`design:lint` exit 0 实际结论
- [ ] 4.3 真栈实测（5274 独立环境纪律）：一章故意写短触发补足闭环；一本 6000 字档观察截断桶是否出数——结论回写 c-scene-density tasks 5.6 对应观察项（两仓 change 数据互认）
