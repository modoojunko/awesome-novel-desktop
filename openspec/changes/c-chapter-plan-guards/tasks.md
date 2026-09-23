## 1. 原型先行（C端 用户可见改动）

- [x] 1.1 对照卷下拆章原型（`docs/design-c/drafts/ai-novel-c端-卷下拆章.html`）核对保存钮禁用态与回执文案的像素增量，在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记——登记项贴进 change 目录
- [x] 1.2 文案按 design-language.html §13 口径自查（「已保存」/「已排上」为动词回执、无内部术语）——自查结论贴进 change 目录

## 2. 回改保存保全既有内容（P0）

- [x] 2.1 `saveEdit` 改为「GET 章全量 → 合并五段 → 全量 PUT」（沿 `useOutline.saveChapter` 同路）——diff 贴进 change 目录
- [x] 2.2 `__tests__/chapterPlan.test.tsx` 契约断言改口径（缺字段按空写 → 发出全量含未编辑字段）——diff 贴进 change 目录
- [x] 2.3 反向验证：在改动前的实现上跑新断言应红（证明断言能抓住清空行为）——红→绿记录贴进 change 目录
- [x] 2.4 后端回归：`pytest client/backend/tests` 全量绿（写语义未变，验证无连带）

## 3. 读卡失败不得脏草稿可保存（P1）

- [x] 3.1 `openEdit` 失败路径清空 draft、置失败态；保存钮按「装载成功」门控——diff 贴进 change 目录
- [x] 3.2 单测：读卡失败后保存钮禁用且不产生 PUT；重试成功后回显可保存——vitest 绿

## 4. 竞态守卫

- [x] 4.1 进场锚 catch 改比 `anchorTokenRef.current`；`openManual/openAi/openEdit` 统一重置 `entry`——diff 贴进 change 目录
- [x] 4.2 `runSelfcheck` 加 token 守卫与按钮 busy——diff 贴进 change 目录
- [x] 4.3 单测：换卷开卡不残留上一卷进场；进场失败呈现兜底文案；自检晚到响应被丢弃——vitest 绿

## 5. 保存回执分流

- [x] 5.1 `adopt` 返回动作标识（adopt/edit），handler 回执分流（「已排上」/「已保存」）——diff + 截图路径贴进 change 目录
- [x] 5.2 单测：回改保存回执不含「已排上」；排上回执不变——vitest 绿

## 6. 搬运冲突识别（与 c-db-version-hardening 协调）

- [x] 6.1 `LegacyMigrateModal` 的发起失败分支改按 HTTP 409 判定（不再靠文案子串），409 时 attach 轮询或明示「已有任务在跑」——diff 贴进 change 目录
- [x] 6.2 单测：409 响应进入轮询/明示态；非 409 走普通错误态——vitest 绿

## 7. 回归

- [x] 7.1 `npm run design:lint`、`npm run design:check`（C端）输出结论贴进 change 目录
- [x] 7.2 `tsc --noEmit`（C端）输出结论贴进 change 目录
- [x] 7.3 `npx vitest run`（全量）输出结论贴进 change 目录
- [x] 7.4 定向 e2e（拆章手写/回改/排上/自检、搬运发起）在隔离 docker 栈通过——结论与截图路径贴进 change 目录
