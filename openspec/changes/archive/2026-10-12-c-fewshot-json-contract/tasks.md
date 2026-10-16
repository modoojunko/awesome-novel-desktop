# c-fewshot-json-contract — 任务

无界面改动（判定依据：proposal Impact——纯后端提示词契约＋测试，不触任何屏/弹层/共享段），
免原型先行，design 门禁不适用。

## 1. 提示词仓：模板修复＋守卫（sibling 私有仓，commit 互引 c-fewshot-json-contract）

- [x] 1.1 改 `prompts/style_fewshot_mine.prompt`：system 段（`<<system>>` 内）补输出契约
      一句——只输出 JSON 对象 `{"lines": ["原句1", ...]}`，lines 收 1–3 条原文摘录、
      不输出任何解释文字（含「json」字样）；user 段不动。验证：`python3 sync.py lint` 过；
      python 手跑 `load_layers("style_fewshot_mine")` 目检 system 段含契约、注释头未混入
- [x] 1.2 新增 `tests/test_json_contract.py`：例外名单（`ASSETS` 六件 ∪ 成品文本三件
      `write_chapter`/`polish_text`/`prompt_crafting`，注明豁免理由）之外的全部模板，
      `load(name)` 剥注释后断言含「json」（大小写不敏感）并指名失败模板；倒置默认
      （名单外全查）。验证：守卫自证——临时删掉 style_fewshot_mine 的 json 字样跑 A/B，
      守卫红→还原绿
- [x] 1.3 `python3 sync.py all` 重生成 manifest（sha256/bytes 随 1.1 漂移，勿手改）；
      venv（≥3.10）跑 `python3 -m pytest tests/ -q` 全绿

## 2. C端：fewshot-mine 行为钉（零生产代码变更）

- [x] 2.1 新增 backend 测试：桩化 `_judge_chat` 捕获实发 system＋prompt，断言
      （a）含「json」字样（b）模板声明 lines 键输出契约（c）桩返回 `{"lines":[...]}` 时
      端点解析出例句列表；无归档章 400 文案原样保留；缺模板源时按 conftest 缺源转跳纪律
      skip。验证：`pytest` 该文件绿＋有源态非 skip
- [x] 2.2 C端 backend 全量 pytest 无新增红（基线见最近合入 main 的跑数）

## 3. 双仓合入与发包（修复落地的必要链，不与 1/2 合并）

- [x] 3.1 C端 PR：本 change 工件＋2 的测试钉；提示词仓 PR：1 的模板＋守卫；两侧
      commit message 互引 `c-fewshot-json-contract`
- [ ] 3.2 提示词仓 `publish.py` 四步发新包：① build＋上传 v{N}（latest.json 暂不翻）
      ② S端 登记 CEK ③ verify＋真机 smoke（下载→验签→换钥→解密）④ 翻 latest.json；
      与 v0.31 起挂账的提示词包重发同批清（注意 Actions 配额停摆，发布走本机凭据）
- [ ] 3.3 测试同学复验：DeepSeek 配置下点「例句提炼」出 1–3 条例句、无 400/502

## 4. 收尾

- [x] 4.1 `openspec validate c-fewshot-json-contract --specs` 绿；归档另起 PR
      （归档前逐 bullet 双向对拍，防并行回灌）

## 回归

- 提示词仓：`python3 sync.py lint` ＋ `python3 -m pytest tests/ -q`（含新守卫）——
  **实际结论（2026-10-11，wt awesome-novel-prompts-wt-fewshot）**：lint 通过；
  52 passed, 1 skipped（守卫 A/B：抽干 json 字样→红并指名 style_fewshot_mine→还原绿）
- C端：`cd client/backend && python -m pytest -q` 全量——**实际结论（同日，wt
  ai-novel-wt-fewshot-json，PROMPT_PACK_DEV_DIR 指提示词仓 wt）**：2278 passed,
  1 skipped（唯一 skip＝test_packaging_win_signing 本机无 pwsh，CI 上真跑，与本批无关）；
  新文件 ruff check 过；缺源态复跑＝2 skip＋1 passed（无归档 400 钉不依赖模板源），
  缺源转跳纪律符合预期
- design 门禁（design:lint / design:check / tsc --noEmit / design-cross）不适用：
  无界面改动、不触共享段（proposal「Impact」判定）；C端 仅增 backend 测试文件，
  前端零触碰
