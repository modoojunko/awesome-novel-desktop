# Tasks: c-battlefield-custom-input

## 1. 影响判定

- [x] 1.1 考古定罪：非回归（#347 建页起 05 即无手填口，设计原型有「＋自定义」）；数据链路已留位（`custom_text` 恰一非空＋`battlefieldTextMax` 闲置）。验证：`git log -S`（cap-add／自定义／战场全历史）＋后端模型实勘。

## 2. 前端

- [x] 2.1 `GenreSettingForm.tsx`：`customBattlefield` state＋`addCustomBattlefield`（同名落预设勾选／重复提示／上限共用 battlefieldMax）＋05 格 `cap-add` 输入框（maxLength=battlefieldTextMax）。验证：tsc 0 错。
- [x] 2.2 `GenreSettingForm.test.tsx`：补「回车自定义 → 可移除胶囊；同名落预设勾选不重复」用例。验证：定向 vitest 38/38。
- [x] 2.3 评审整改（PR #974 内）：词汇引用样输入（`kind:slug` 前缀）拒收守卫 `VOCAB_REF_RE`（拒收不清输入）——后端按前缀落 vocab 引用，手造 id＝FK 违例 500；save 契约用例补自定义文本项＋拒收断言；spec 补 bullet＋「词汇引用样输入拒收」scenario。

## 3. 规格

- [x] 3.1 `specs/intro-genre-settings/spec.md` delta：ADDED 05 手填口径 requirement（3 scenario）。

## 4. 收尾

- [x] 4.1 本地门禁：vitest 全量 1893 绿＋tsc＋design:lint＋openspec validate。
- [ ] 4.2 推送＋PR＋CI 绿；同 PR sync delta＋归档（openspec-archive-in-implementation-pr）。
