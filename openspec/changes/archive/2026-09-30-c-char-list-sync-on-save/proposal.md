# c-char-list-sync-on-save：角色卡保存落库后同步角色树——配角改反派不再滞留旧组（#618）

## Why
用户真机反馈（09-30）：角色设定页把某人从配角改成反派并保存后，左侧分组树不动，要整页刷新才归组。根因＝人物卡逐格自动保存（`CharacterManager.flushQueue`，600ms 防抖＋串行队列）落库成功后只翻保存态、从不重取列表；左侧按 主角/配角/反派/路人 分组的树读独立的 `list` 状态。新建/删除/合并/AI 采纳路径都有 `reloadList`，唯独手写编辑这条路漏了——身份、名字、别名、一句话人设的改动都只写在卡上，树滞留旧值。

## What Changes（#618=644efe3a，squash 上 main）
- `flushQueue` 成功排空保存队列后补一次 `reloadList()`：行即时归入新类型组、行名同步，「待立」角标与组计数、搜索结果一并对齐；列表重取失败静默略过、不翻转已成功的保存态（格已落库，下次保存或重进角色页再刷）。
- 防抖窗口内的新编辑由 `finally` 重入兜底；外部 `save()` 句柄返回值语义不变；409/网络失败路径不经重取，行为不变。
- specs：character-settings「角色列表一次给全」补保存落库后列表同步的 Scenario（本 change 归档时 sync）。

## Capabilities
- character-settings：MODIFIED「角色列表一次给全」——新增 Scenario「保存落库后列表同步」，既有两个场景（打开面板只发一次请求／搜索不发请求）原样保留。

## Impact
纯前端单点改动（`CharacterManager.tsx` 9 行）＋回归测试 `CharacterManager.roleRegroup.test.tsx` 两例（配角→反派落库后归组变化并断言列表接口二次调用、改名后行名同步，走真实防抖时序）。CharacterManager 四测试文件 22 例绿＋tsc 零错误＋全量 vitest 1009 绿（余 3 红为已知存量红 `CharacterManager.adopt×3`，与 #617 前端弹窗域相关、非本改）。未跑 e2e（纯前端状态同步修复，组件测试已钉行为）；非目标＝右栏 AI 行 `onCtxChange` 的换卡级刷新粒度（编辑后不即时刷新，另一处类似滞后，本 change 不动）。评审（review-agent）：零 finding。CI 基建秒挂按先例 admin 合入。
