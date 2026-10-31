# 拆书题材五格齐备 — 实施任务

## 0. 前置核查（不动代码）

- [x] 0.1 读 prompts 加载器（`prompts` 包的 `load_layers`），确认 user 段占位符填充方式：多传
      `forbidden_vocab` / `battlefield_vocab` 键是否无害（`str.format` 宽松 vs 白名单校验）。验证：
      在 `client/backend` 里跑一段脚本，用现有模板 + 多余键调一次 `load_layers` 填充，断言不抛错；
      结论写进 PR 描述。若为白名单，D2 改为题材维度专用扩展 dict。
- [x] 0.2 量一次词表规模与 token：`VOCAB_PRESETS` 里 `kind in ("forbidden","battlefield")` 各多少条、
      拼成文本多少字符。验证：输出计数；若单表 >60 条，按 top N 或主题材过滤后再注入。

## 1. C 端：核心承诺回退 + 推断提示如实（可独立发布）

- [x] 1.1 `deconstruct/settings_map.py:genre_extras`：`core_promise` 缺失时回退读
      `dg.get("promise")` 并按 60 字收口；仅当回退也为空才走 `_pick_label` 推断并记 `inferred`。
      验证：单测三臂（有新键 / 只有 promise / 两者皆无），断言 `inferred` 不含 `core_promise`
      且 `core_promise` 取到 promise 前 60 字。
- [x] 1.2 同文件新增 `inferred_labels`（中文标签映射：核心承诺/承诺说明/禁写清单/代价比例/战场），
      `genre_extras` 返回值同时带上；内部 `inferred` 键保留（测试与后续逻辑仍可用）。
      验证：单测断言两列表一致同序。
- [x] 1.3 `deconstruct/apply.py:251-256` 拼提示改用 labels，文案改为
      「拆书没有给出{清单}，已按题材与主线推了起点，请去「设定 → 题材」核对」；`inferred` 为空时
      SHALL NOT 追加该 warning。验证：单测覆盖「四项全缺」「只缺两项」「零缺」三臂，断言文案无
      英文键名。
- [x] 1.4 端到端：用真实存量任务（旧产物只有 promise）重跑建书，断言新书 `core_promise` = promise
      前 60 字、提示条只报三项、文案为中文。验证：pytest 契约用例 + 真机一次（可复用 0.44.2 那本
      13路末班车 的任务，删书后重建）。**实测（0.44.3）**：`core_promise`＝「以都市夜班公交为引…解密快感。」，
      warning＝「拆书没有给出禁写清单、代价比例、战场，已按题材与主线推了起点，请去「设定 → 题材」核对」。

## 2. C 端：题材维度词表注入（契约生效的另一半）

- [x] 2.1 `deconstruct/pipeline.py` `_run_dim` 的占位符 dict 补
      `forbidden_vocab` / `battlefield_vocab`（按 `kind` 从 `VOCAB_PRESETS` 取 label，按 0.2 的
      top N 截断）。验证：单测断言题材维度的 model 输入含这两段文本；非题材维度输入与变更前逐字相同
      （快照比对）。
- [x] 2.2 `deconstruct/settings_map.py:genre_extras` 对 `forbidden` / `battlefield` 的读取兼容两种
      形态：数组（新契约）与旧的缺省（无该键）；词表外标签走 `custom_text`。
      验证：单测三臂（词表内 / 词表外 / 无该键）。
- [x] 2.3 `apply.import_book` 的题材写入分支确认不再依赖推断值（新契约下 `inferred` 应为空）；
      若模型漏字段仍按推断 + 如实提示。验证：契约用例「产物带四格 → 书侧五格等于产物值、warnings 无题材推断项」。

## 3. prompts 仓：模板契约扩字段（另仓，按 prompts 流程走）

- [x] 3.1 `prompts/deconstruct_genre.prompt` 输出契约扩为
      `genre / tags / core_promise / promise_note / forbidden / cost_ratio / battlefield /
      confidence / note`，逐字段写清限长与「必须从词表选」；保留三铁律与「只输出 JSON」。
      验证：prompts 仓自带测试/守卫（JSON 契约与模板守卫）全绿；模板里三个新占位符与 C 端注入名一致。
- [x] 3.2 manifest 版本进位与 `min_client` 判定：**计划变更**——原以为向后兼容故不 bump；实测发现新模板
      使用 `{forbidden_vocab}` / `{battlefield_vocab}` 两个占位符，旧客户端（<0.44.4）不注入 →
      `str.format` KeyError → 拆书维度直接失败。故 `min_client` **必须** bump 到 `0.44.4`（当前生产版）。
      验证：线上 `prompts/latest.json` 的 `min_client_version=0.44.4`，0.44.4 客户端正常换钥装包。
- [x] 3.3 打包 + 灰度下发（发包动作，需拍板）。验证：本机 `data/prompt-pack/` 出现新版本目录；
      跑一次真实拆书，`products_json.genre.data` 出现 9 个键。**实测**：包 `2026.10.31-1` 已发（四档
      20/69/74/82，四档 CEK 已登记 S 端、线上指针已翻）；本机 receipt 同步为 `2026.10.31-1`；
      3 章探针任务产物＝9 键，`core_promise`/`forbidden`/`cost_ratio`/`battlefield` 全部来自拆书且取自词表。

## 4. 验收与回归

- [x] 4.1 后端全量：`cd client/backend && uv run pytest -q`。验证：输出结论附 PR。**实测**：
      `2662 passed, 320 skipped in 201s`（无失败）。
- [x] 4.2 真机验收（需真实拆书任务）：新拆一本 → 题材产物 9 键齐 → 建书后设定页五格＝产物值、
      顶部提示条不出现；再拿旧任务（5 键产物）建书 → 提示条只报三项且为中文。
      验证：截图 + `products_json` 键清单 + `novel_genre` 五格取值。**实测**：探针任务九键齐；
      旧任务（13路末班车）建书提示为中文三项。
- [x] 4.3 归档前核对：`openspec validate --strict` 全绿；主 spec 两条 MODIFIED 文本与实现一致。

## 5. 归档（随实现 PR）

- [x] 5.1 delta sync 进 `openspec/specs/deconstruct-book/spec.md` 并归档本 change。
      验证：`openspec archive c-deconstruct-genre-fields --yes` 后 validate 与基线对拍无新增红。
