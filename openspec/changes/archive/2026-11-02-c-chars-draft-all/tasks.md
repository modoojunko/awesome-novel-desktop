# c-chars-draft-all — tasks

## 1. 提示词仓

- [x] 1.1 新增 `prompts/settings_characters_from_settings.prompt`（system/user 分层、JSON 契约、新拟名禁令全量、配角/反派定位口径、路人只档案）
- [x] 1.2 `sync.py` CURATED 登记＋`sync.py all/lint`；`tests/test_charname_ban.py` 纳入新模板
- [x] 1.3 `pytest tests/` 绿（119 passed / 1 skipped）
- [ ] 1.4 发布新提示词包版本（`publish.py build/verify/cek`→上传→注册 CEK→冒烟→翻 latest；additive，不 bump min_client）

## 2. 后端

- [x] 2.1 `POST /settings/ai/characters/draft-all`：带卡只补空格；无卡校验 role；preview 不调 AI
- [x] 2.2 已确认设定只取 genre/synopsis/world/story-arc；四项全未确认 400；名册排除本卡
- [x] 2.3 新模板渲染（`<<...>>` 顺序替换）＋返回 role/name/aliases/persona/cells/skipped/prompt/sources
- [x] 2.4 路人只收 dossier cell；已有名字/别名/人设不覆盖；空稿/超时记账
- [x] 2.5 单测：预览只读已确认项、未确认 400、有卡只补空格、路人、无卡带 role、空稿、超时

## 3. 前端

- [x] 3.1 `charactersApi.draftAllPreview/draftAll`＋`DraftAllResult`
- [x] 3.2 `CharacterManager`：`draftAll` action（preview→generate→adopt）、无卡角色 chips、缓存、token 迟到守卫
- [x] 3.3 采纳：有卡服务端 rev 记账＋409 跳过；无卡 create(role)＋逐格 PATCH
- [x] 3.4 `CharsAiRail`：只留 bootstrap/draftAll/check；空格/无卡/路人/未确认/空书门控；`SettingsView` 传 hasCards/confirmedAny
- [x] 3.5 单测：rail 矩阵、有卡只补空格、无卡切角色建卡、缓存、迟到丢弃、rev/409；删除一键立卡旧测

## 4. 规格与验收

- [x] 4.1 本 change delta（REMOVE 四能力/一键立卡；ADD 起草角色/能力契约；MODIFY 新拟名禁令）
- [ ] 4.2 `openspec validate` 绿；实现 PR 内 sync＋归档
- [x] 4.3 前端 `npm run coverage` exit 0（2133 passed/171 files）；`tsc --noEmit` 0 error
- [ ] 4.4 本地真栈走查：有卡补空格 / 无卡新建配角/反派 / 路人 / 未确认置灰 / 旧包 prompts_missing 四态卡
