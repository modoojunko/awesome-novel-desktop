# c-hooks-plot-exclusion 任务（回填执行记录）

- [x] 1. 实勘定位：hooks 提示词缺剧情走向负向判据；e2e 桩承重短语（「对既有伏笔的兑现与推进」）与单测 5 短语摸清
- [x] 2. 判据三段收紧（未解承诺＋自检／剧情走向排除／问完即答＋章末断点排除）；桩短语逐字保留
- [x] 3. 模型在环 A/B（演示栈真实绑定模型）：纯行动样本旧 2 假→新 0；真钩子样本双版正确，无误杀
- [x] 4. specs：archive-reconcile 补排除条款＋新 Scenario（随实现 PR 同步）；单测钉 4 新短语
- [x] 5. 门禁：test_reconcile 30 绿＋全量 pytest 1708 绿＋prompt_layering 过＋spec validate --strict valid
- [x] 6. review-agent 评审零 finding（桩兼容／单一产出源／预算／测试面逐项核过）
- [x] 7. PR #615 admin squash 合入 main（238f4085）；演示栈 client-backend 换包＋特征串自证
