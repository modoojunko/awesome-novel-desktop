# Tasks: c-chapter-seam-check

## 1. 后端（client/backend/write/ai_check.py）

- [x] 1.1 `CHECK_KINDS["chapter_seam"]`：五类断点（开场断裂/态度跳变/道具断环/同拍重复/认知矛盾），每条须给证据（本章原句＋对照素材点）
- [x] 1.2 `_material` chapter_seam 分支：上章结尾原文（ctx.previous_tail）＋前文回顾＋`_story_state_block(ctx.story_state)`；首章/无正文给「（无…）」占位
- [x] 1.3 复用既有门控（ai-generate）与计费（ai_check_chapter_seam）；产物不落库

## 2. 前端

- [x] 2.1 `lib/aiCheck.ts`：AiCheckKind 联合＋CHECK_TITLE「章际衔接检查」
- [x] 2.2 `AiAssistPanel.tsx` 正文页签新增动作行（生成中/无正文禁用，testid=rail-seam-check 走 onAiCheck 既有弹窗链）

## 3. 测试

- [x] 3.1 `tests/test_ai_assist_checks.py` 新增 `test_chapter_seam_material_carries_prev_tail`：造 ch-2 断言【上章结尾（原文）】块＋ch-1 末段进素材（坑：Chapter.ref 不跨项目唯一，查询须按 project 过滤；_UIDS 全局字典批量跑会串——用测试自身 nid）
- [x] 3.2 受影响套件 14/14 绿；全量 2245 passed＋16 存量失败（15 既有＋#828 的 test_ai_flavor_scan 1，与本 change 无关）

## 4. 配套与生效

- [x] 4.1 提示词仓 ai_check 元数据六→七类（cb202c7；模板正文零改动）
- [x] 4.2 5274 重建（烘 feature 分支）＋容器验证 CHECK_KINDS 含 chapter_seam
- [ ] 4.3 PR 合入 main 后，正式包用户随下个提示词包/C端发版获得

## 5. 验收（真机/演示栈）

- [ ] 5.1 正文页签点「章际衔接检查」：衔接好的章返回空数组；构造断点（改开头/删状态行）返回带证据 findings
- [ ] 5.2 首章（无上章）检查不误报（素材占位＋空数组）
