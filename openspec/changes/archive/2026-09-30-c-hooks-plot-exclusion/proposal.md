# c-hooks-plot-exclusion：伏笔判据排除剧情走向——只登记未解承诺（#615）

## Why
用户真机反馈（09-29）：伏笔登记「什么都识别出来当伏笔了」，手删了多条。根因＝hooks 提示词（archive/reconcile.py `_collect_prompts`）只有正向判据（"明确的悬念，指向后文揭示"）＋氛围/场景/角色状态排除——进行中的冲突、行动、因果紧接的下一步（去了哪里/和谁交手/下一步打算/危机升级）都会被模型当「悬念」登记。

## What Changes（#615=887135fd，squash 上 main=238f4085）
- 判据三段收紧（e2e 桩匹配短语「对既有伏笔的兑现与推进」逐字保留，reconcile.spec.ts:58 依赖）：
  ① 正向定义改「未解承诺」——读者被明确引去期待一件尚未发生/尚未揭示的事（谜团、异常、警告、约定、来历不明之物）；自检＝后文永不回收读者会觉得被辜负，才算伏笔；
  ② 剧情走向排除：正在发生的冲突/行动/事件本身、因果紧接的下一步，再重要也只是剧情推进；
  ③ 当场提出当场解答（问完即答≠伏笔）与章末悬念断点（只为吸引读下一章）显式排除。
- specs：archive-reconcile「收尾行生命周期」真伏笔判据补剧情走向排除条款＋新 Scenario「剧情走向不登记为新埋」（随 #615 实现直接同步，无待归档 delta）

## Capabilities
（skip_specs: true——spec 已随 #615 直接同步 main：archive-reconcile 一 capability，validate --strict valid；无待归档 delta）

## Impact
单点提示词改动（reconcile.py hooks 段）＋单测 4 短语＋spec 条款。模型在环 A/B（演示栈用户书《我在夜晚打吸血鬼》绑定 deepseek-v4-flash）：纯行动无钩子样本旧判据出 2 条假伏笔（「黑衣人组织的追捕」「尸体上待发现的线索」），新判据 0 条；带真钩子样本（徽章与上月猎人相同）两版都正确登记，无误杀。tests/test_reconcile.py 30 绿＋全量 pytest 1708 绿＋test_prompt_layering 过。已知权衡：判据对边缘轻伏笔（背景带过、作者暗中呼应）偏严可能漏登——提案制下作者可右栏「登记新伏笔」手补，宁缺勿滥为既定方向。评审（review-agent）：零 finding。CI 基建秒挂按先例 admin 合入；演示栈 client-backend 已换包并特征串自证（「未解承诺」「剧情走向不是伏笔」双命中）。
