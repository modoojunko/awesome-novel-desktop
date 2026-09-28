# c-reconcile-truncation：收尾真机修复两连（#564＋#572）

## Why
c-chapter-dossier（#557）合入当日真机首跑暴露两处收尾缺陷：
① 伏笔登记 parse 失败——输出断在半句 evidence，实锤 max_tokens=600 截断（hooks/lore 要求 planted/resolved 各几条带证据句，600 必截）；
② 重试成功后旧失败行永久挂列表（重试产出新 pending 承接，failed 行无清除路径）；
③ 二次报障「重试无反应」＝演示栈镜像未更（并行会话 14:23 重建后自带修复）＋AI 后台跑 1-2 分钟轮询窗口——判定口径：错误文案无「疑似截断」即旧代码行。

## What Changes（#564=bdb6df0b）
- 收尾 chat max_tokens 600→1600（与四域提取同预算）
- 解析失败且输出末尾无 `}` → 错误行追加「输出疑似被输出预算截断」诊断
- 回归测试：预算值＋截断文案断言

## What Changes（#572=1bc94030，用户批准的两件）
- lore prompt 注入本书专名册（roster_text(known_names)）＋「已登记角色背景不进世界要素（归角色卡）」——根治邵青梧/阿蓟等角色背景被当新世界要素提案（真机实锤：lore 只带世界设定排重、没带名册）
- 重跑成功 _upsert_pending 后清同章同类 failed 行——旧失败行使命已尽，不再永久挂列表
- 回归测试×2（名册进 lore 不进 hooks＋旧 failed 清除）

## Capabilities
（skip_specs: true——纯修复，行为语义在既有 archive-reconcile/chapter-dossier spec 框架内，零 delta）

## Impact
client/backend/archive/reconcile.py＋tests/test_reconcile.py；pytest 1697 绿。
