## 1. 原型先行（硬性流程）

- [ ] 1.1 `docs/design-c/prototypes/genre-signup.html`：口味胶囊交互 JS 改新行为——点选只填 02 起点句（textarea）+ 单颗高亮；再点同颗取消（还原/只清高亮同口径）；不再渲染 03/04/05 联动；toast 文案同步；`GENRES` 数据补起点句字段。验证：打开原型点「逆袭打脸」只有 02 变、再点还原。
- [ ] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 新增 `## c-genre-flavor-promise-only（2026-10-08）` 小节：登记行为收窄 + toggle、胶囊 title 文案、原型 01 格老 IA 存量漂移注明不修。验证：小节落盘。

## 2. 实现

- [ ] 2.1 `client/frontend/src/components/novel/settings/GenreSettingForm.tsx`：重写 `applyFlavor`——只写 `core_promise`+`promise_note`；`flavorBeforeRef` 存应用时 02 值；toggle（未改→还原+回执；已改→只清 `flavorKey`）；切换＝新起点覆盖 02；回执文案「已按「X」给出「主要看什么」一句起点：「<全句>」，可撤销」。胶囊 `title` 改「给「主要看什么」一句起点，可改；再点一次取消」。验证：`npx vitest run src/__tests__/GenreSettingForm.test.tsx` 绿。
- [ ] 2.2 `client/frontend/src/lib/genreVocab.ts`：头注释「`GENRE_FLAVORS`：01 口味胶囊的预置联动（选中后预填 02-06）」改为「02 起点胶囊（只填示例句+短标签，可取消），不落库、不计入判据」。验证：grep 无「预填 02-06」残留。

## 3. 测试

- [ ] 3.1 `src/__tests__/GenreSettingForm.test.tsx`：L76 用例改为「只填 02」断言（02 出现起点句+标签；03 胶囊不亮、04 无浮例句、05 不亮）；L602 回执用例改为新文案（断言含「一句起点」、不含「吃苦指数」；undo 还原 02、cost 不动）；新增「再点取消（未改→还原+回执）」「改过后取消（只清高亮不动字）」「切换（B 覆盖 A）」三用例。验证：vitest 全绿。
- [ ] 3.2 `client/frontend/e2e/settings-forms.spec.ts` ①a：点「comeback」后断言翻转——`forbidden:no-deus-ex-machina` / `battlefield:resources` **不再** `on`、`.cost-val` 为「—」；后端直查 `battlefield` 改 `toEqual([])`（`core_promise`/`forbidden_list` 含自定义项/`cost_ratio`=6 手拖值不变）。验证：本地或 CI e2e 绿。
- [ ] 3.3 同文件 ①b「长回执」：点胶囊后回执断言改含「一句起点」（新最长回执载体），截断/脚部高度断言保留。验证：CI e2e 绿。

## 4. 门禁与交付

- [ ] 4.1 `openspec validate --change c-genre-flavor-promise-only --strict` 通过。验证：命令退出 0。
- [ ] 4.2 前端门禁：`npm run design:lint` + `npm run design:check`（预期零像素差——无 CSS 改动）+ `tsc --noEmit` + vitest 全量。验证：全绿。
- [ ] 4.3 提交（原型+ADJUSTMENTS+实现+测试+change 四件套同批）→ push → 开 PR（实现 PR，归档另起）。验证：PR 建立、CI 全绿。
