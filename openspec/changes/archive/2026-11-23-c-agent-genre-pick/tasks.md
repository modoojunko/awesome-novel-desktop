## 1. 后端工具

- [x] 1.1 `tools_settings.py` 新增 `read_genre_catalog`（read）：按 `genres.theme_catalog.THEMES` 输出大类/子类解读与案例——验证：单测含全部大类、无裸 JSON
- [x] 1.2 新增 `settings_genre_pick`（card）：`theme`/`sub_genre`/`note`，按目录校验（未知回人话可选清单），出 `stype=genre, field=catalog, value={theme,sub_genre,note}` 卡、不写库——验证：合法/非法/只选大类三例
- [x] 1.3 `scopes.py`：两工具进 `set:` 域；设定纪律补「选/定/判断题材→读目录→出卡，四格另有工具」——验证：`test_page_scopes` 域声明通过
- [x] 1.4 `router.genre_prime_hint`：设定域窄意图首步读目录（显式 hint 优先/域外不触发）——验证：prime 命中与守卫单测

## 2. 前端卡面与写回

- [x] 2.1 `CardBody`：`stype/field` 设定卡按字段中文名渲染；`field=catalog` 渲染 题材/子类/理由；对象 `{value,note}` 拆两行，禁裸 `value`——验证：卡面单测无 `value` 字样
- [x] 2.2 `dockWriteBack`：`catalog` 写回 `theme`/`sub_genre`（GET 当前 genre→整包 PUT 保留其它字段），回执人话——验证：单测 PUT body 三键
- [x] 2.3 `Aui2Dock` 采纳链复用（`isSettingsField` 已覆盖 stype/field/value）——验证：现有采纳测试仍绿

## 3. 门禁

- [x] 3.1 后端定向＋全量 pytest、ruff；前端 tsc/vitest/coverage/build；`openspec validate --strict`；design:lint 本改动零违规
- [x] 3.2 合前 `review-agent` 审 diff，findings 修完再合。证据：No findings；补了目录读取后的下一步提示
- [ ] 3.3 建 PR，CI 双绿 squash 合 main，清 worktree/分支

## 4. 发版（0.49.0 已发，修复走补丁）

- [ ] 4.1 合入后打 `v0.49.1` annotated tag（release notes 写清题材选择修复），跑打包/灰度验收
- [ ] 4.2 本地装机走查：问「根据标题帮我选定题材」→ 出题材卡（题材/子类/理由）→ 采纳 → 01 题材落库
