## 1. 原型先行（硬性流程）

- [x] 1.1 `docs/design-c/prototypes/genre-signup.html`：口味胶囊交互 JS 改新行为——点选只填 02 起点句（textarea）+ 单颗高亮；再点同颗取消（还原/只清高亮同口径）；不再渲染 03/04/05 联动；toast 文案同步；`GENRES` 数据补起点句字段。二轮追加：作者内容（非起点原句）不覆盖＋提示。验证：打开原型点「逆袭打脸」只有 02 变、再点还原、手写句后点胶囊不动。
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 新增 `## c-genre-flavor-promise-only（2026-10-08）` 小节：登记行为收窄 + toggle、胶囊 title 文案、原型 01 格老 IA 存量漂移注明不修；二轮补充「作者内容不覆盖」。验证：小节落盘。

## 2. 实现

- [x] 2.1 `client/frontend/src/components/novel/settings/GenreSettingForm.tsx`：重写 `applyFlavor`——只写 `core_promise`+`promise_note`；`flavorBeforeRef` 存应用时 02 值；toggle（未改→还原+回执；已改→只清 `flavorKey`）；切换＝新起点覆盖 02；回执文案「已按「X」给出「主要看什么」一句起点：「<全句>」，可撤销」。胶囊 `title` 改「给「主要看什么」一句起点，可改；再点一次取消」。二轮追加：应用/切换前置守卫——02 非空且非任一颗起点原句 → 不覆盖＋`toast.info` 出路。验证：`npx vitest run src/__tests__/GenreSettingForm.test.tsx` 绿。
- [x] 2.2 `client/frontend/src/lib/genreVocab.ts`：头注释「`GENRE_FLAVORS`：01 口味胶囊的预置联动（选中后预填 02-06）」改为「02 起点胶囊（只填示例句+短标签，可取消），不落库、不计入判据」；`GenreFlavor` 删除 forbidden/costRatio/battlefield 死字段。验证：grep 无「预填 02-06」残留、`tsc --noEmit` 绿。

## 3. 测试

- [x] 3.1 `src/__tests__/GenreSettingForm.test.tsx`：起点用例改造（只填 02 断言、回执全句断言）＋新增「取消（未改→还原+回执）」「改过后取消（只清高亮不动字）」「切换（B 覆盖 A）」用例；二轮追加：既有内容用例 initial 改起点原句（否则被新守卫拒绝）、新增「作者已写内容不覆盖+提示」用例。验证：vitest 单文件 35 例绿。
- [x] 3.2 `client/frontend/e2e/settings-forms.spec.ts` ①a：点「comeback」后断言翻转——`forbidden:no-deus-ex-machina` / `battlefield:resources` **不再** `on`、`.cost-val` 为「—」；fill 作者句后点另一颗胶囊断言内容不动（二轮）；后端直查 `battlefield` 改 `toEqual([])`（`core_promise`/`forbidden_list` 含自定义项/`cost_ratio`=6 手拖值不变）。验证：隔离栈实跑绿。
- [x] 3.3 同文件 ①b「长回执」：点胶囊后回执断言改含「一句起点」（新最长回执载体），截断/脚部高度断言保留。验证：隔离栈实跑绿。

## 4. 门禁与交付

- [x] 4.1 `openspec validate c-genre-flavor-promise-only --strict` 通过。验证：命令退出 0。
- [x] 4.2 前端门禁：`npm run design:lint` + `tsc --noEmit` + vitest 全量（无 CSS 改动，design:check 像素零差）。验证：全绿。
- [x] 4.3 二轮改动复跑隔离栈 e2e（settings-forms.spec.ts）后 push 同一 PR；评审整改（ref 随 undo 恢复）后 rebase 到 main 并**再复跑一轮**（rebase 后构建 15/15 绿，bundle 特征串自证）。验证：远端 head 前进、CI 绿。
