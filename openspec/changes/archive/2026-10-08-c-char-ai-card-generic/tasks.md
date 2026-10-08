# c-char-ai-card-generic — Tasks

## 1. 原型先行（C端）

- [x] 1.1 `docs/design-c/prototypes/character-settings.html`：右栏 AI 卡在配角/反派上下文加首行「一键立卡」（沿用 ra-step 行组件与既有三态，不新增形态）；角色卡主区加一行 info 提示文案（纯文本不可点）。对照 §13 口径自查：按钮词为动词、无内部术语。验证：原型渲染截图与文案贴入 change 目录
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记两处新增（右栏行、卡区提示行）及理由。验证：登记条目可逐条对上 1.1 的改动

## 2. 提示词仓 companion（awesome-novel-prompts，前置合入）

- [x] 2.1 新增 `prompts/settings_characters_card.prompt`：system/user 分层，`{role}` 占位（配角/反派），剧情定位口径按角色改写，格位口径/认知六层框架/铁律与主角版同源自足；纳管注释按 sync.py 规范（触发行写 `characters_ai.py` 新分派处）。验证：仓内分层闸门（`<<system>>/<<user>>` 标记检查）通过
- [x] 2.2 manifest.json 登记新模板＋跑 sync.py 重生成 README；主角模板 `settings_characters_bootstrap.prompt` 字节不动（git diff 自证）。验证：sync 零漂移、git diff 仅新增文件与 manifest/README 两行
- [x] 2.3 提示词仓提交合入 main，并确认 C端 dev 能加载到新模板（dev 源指向或重发布 pack）。验证：`load_layers("settings_characters_card")` 在 C端 环境返回非空 system/user

## 3. 后端

- [x] 3.1 `client/backend/settings/characters_ai.py`：bootstrap 端点内按 `ch.role` 分派模板——配角/反派走 `settings_characters_card`（注入 role），无卡/主角走现行模板；配角/反派分支的简介未填 400 文案与 `_parse_json` 失败措辞改「立卡」。验证：单测覆盖三种角色分派，主角路径渲染结果与改动前逐字节一致（不变量断言）
- [x] 3.2 后端单测补：只补空格基准（已填格进 skipped）、`settings-ai-fields` 门控不变、usage operation 沿用 `settings_char_bootstrap`。验证：`pytest client/backend/tests -k characters` 全绿

## 4. 前端

- [x] 4.1 `charactersApi.ts`：bootstrapDraft 类型/注释补配角语义说明。验证：tsc 无错
- [x] 4.2 `AiWriterAssistant.tsx` CharsAiRail：`role ∈ {配角, 反派} && personaGap+dossierGap+cogGap > 0` 时插入首行「一键立卡」（`data-aiact="cardDraft"`，desc 明示当前角色与只补空格）；卡满退场；路人不渲染。验证：vitest 行门控三态（出/退/路人）用例绿
- [x] 4.3 `CharacterManager.tsx`：runAi 增 `cardDraft` key（同 aiBusy 锁、同缓存重开语义）；弹窗 label「AI 拟稿 · 为「名」立卡（采纳才写入）」；cardDraft 采纳走 adoptBootstrap 有卡分支且永不触发建卡。验证：vitest 采纳单格写入＋409 rev 同步用例绿
- [x] 4.4 角色卡主区提示行：配角/反派卡名称与人设皆空时显示一行指向右栏的提示文案（按 1.1 原型落码，纯文本不可点）。验证：vitest 快照/存在性断言绿

## 5. e2e

- [x] 5.1 角色页 spec 补钉子：配角空卡出「一键立卡」行→桩 AI 出稿→采纳只补空格（已填格不动）；卡满退场；路人无行。验证：隔离栈 e2e 该 spec 全绿
- [x] 5.2 主角「从简介立主角」既有断言零改动跑通（回归哨兵）。验证：既有角色相关 spec 全绿，无断言 diff

## 6. 回归

- [x] 6.1 门禁实跑：`npm run design:lint`、`npm run design:check`（像素差 <0.2%）、`tsc --noEmit`、后端 pytest、前端 vitest。验证：全绿，结论回填本任务
  结论：design:lint 净；design:check 7/8（唯一红＝书架屏 quota 2.693%，已知存量光栅漂移、A/B 定罪在案，非本改触面）；`tsc --noEmit` 净；pytest 全量 2086 passed 1 skipped；vitest 全量 1274 passed；e2e settings-forms 15 passed（新钉子＋主角链零改动；1 例「预览只读」为无关定位器歧义偶发，单跑复验绿）
- [x] 6.2 共享段判定复核：本改仅 C端 设定域业务层（ra-step 行复用、无令牌/组件词汇/状态语言变更），不触两端共享段，免 design-cross——依据 proposal Design Impact 判定。验证：判定结论回填
  结论：实改面＝CharacterManager/AiWriterAssistant（业务层 props/行数据）＋charactersApi 注释＋后端 characters_ai.py，零 base.css/共享类触碰；S端 无涉及，design-cross 免跑
- [ ] 6.3 真机冒烟：配角空卡一键立卡全链（出稿→采纳→撤销重改）＋主角链各一遍。验证：截图/结论贴 change 目录（待发版前随真机批次；本地隔离栈已全链实测 5.1）
