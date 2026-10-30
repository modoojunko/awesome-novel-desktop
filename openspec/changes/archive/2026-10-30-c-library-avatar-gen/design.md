# c-library-avatar-gen — 设计

## Context

书内头像生成＝`build_avatar_prompt()`（含风格/构图/脱敏/seed）→ ImageJob（`novel_id` 必填）→ dispatcher → `adapters.generate_images()` → `normalize_image("avatar")` → ImageAsset/Blob。库卡是账号级（无 `novel_id`），不能塞进 ImageJob；但**供应商适配器与压缩链本身与书无关**。

## Goals / Non-Goals

**Goals**：复用出图能力与产物档位；prompt 单源防书内/库卡漂移；PRO 同权；失败可读；新建即可生成。

**Non-Goals**：库内画面描述编辑、候选多图、批量生成、异步任务化、库头像调用计入用量台账。

## Decisions

**D1 同步生成，不开账号级任务表**：服务端 `await asyncio.wait_for(generate_images(...), 120s)` 后直接落库。理由：图像生成单次 10–60s，弹窗内一次性等待可接受；ImageJob 的幂等键/轮询/断点整套是书级资产体系，为库卡复制一套投入大、收益低。备选「ImageJob.novel_id 改可空 + target_type=library」——污染书域任务语义，拒绝。

**D2 prompt 单源**：把 `build_avatar_prompt` 的组装段抽为 `avatar_prompt_payload()`（字段进、payload 出）；书内读库后委托它，库卡 `build_library_avatar_prompt()` 也委托它。脱敏映射：书内＝书名＋全书角色名；库卡＝本卡名＋别名（库内跨书同名合法，不做跨卡全局替换）。版本/画风/构图/负向词/seed 派生规则完全共享。

**D3 档位门同书内**：`@ai_feature("image-generate") + require_tier_access`（PRO，KEYLESS 门：图像 Key 作者自持，不查写作模型）。与书内头像/封面生成一致，不新增售卖面。

**D4 前端「新建先落卡」**：`workingCard` 工作态——草稿点生成时先 `createLibraryCard(当前表单)` → 转编辑态 → 生成；退出未保存也已有卡（与「先保存再生成」比只多一步自动保存，代价可接受，换取创建即出图）。

**D5 失败语义**：缺配置→400 `no_image_config`（可读出口）；供应商错误→502 `image_failed`（供应商 message）；超时→502 `image_timeout`。失败不写 blobs、不 bump rev。

## Risks / Trade-offs

- [同步端点占住请求 120s] → 单用户本地应用、单次生成可接受；超时保护兜底；后续若做批量再考虑异步。
- [库卡与书内头像风格可能不一致] → 画风取默认 ink（库卡无书级画风）；需要时后续在库卡加画风选择。
- [生成消耗供应商额度] → 与书内同权同门；按钮文案「生成/重新生成」让意图明确。

## Migration Plan

无数据迁移；新端点与 UI 随版本发布。回滚＝移除按钮与端点（库头像数据无影响）。

## Open Questions

- 是否给库卡开放画风选择/画面描述编辑（v1 不做，等反馈）。
