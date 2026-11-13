# c-theme-catalog-36 · Tasks

## 1. 目录扩容（三份同源）

- [x] 1.1 后端 `genres/theme_catalog.py`：追加 15 大类（女频 9/男频 5/中性 1，含 desc＋子类文案），存量 21 类零改动
- [x] 1.2 `vendor_sdk/novel_deconstruct_sdk/theme_catalog.py`：同批镜像（THEME_NAMES 逐字一致）
- [x] 1.3 前端 `lib/themeCatalog.ts`：追加同序 `t()` 块（对拍正则同格式）
- [x] 1.4 `test_shared_constants_parity.py` + `test_vendor_sdk_parity.py` 全绿

## 2. 拆书词表根修

- [x] 2.1 `deconstruct/pipeline.py::_genre_vocab_names`：注入源从 DB `genres` 表切到 `theme_catalog` 大类名（词表＝落位校验同源）
- [x] 2.2 相关后端测试绿（genre 维度注入断言如存则同步）

## 3. 回归与验收

- [x] 3.1 后端全量测试（重点：intro-genre / knowledge-base / deconstruct 面）
- [x] 3.2 前端 vitest（题材面板/星图读目录处）
- [ ] 3.3 验收：拆书批量产条目按新目录落位 ——**随 328 本蒸馏主波收尾单独执行**（主波 2 天级，不随本 PR；重判＋搬目录＋撞句清理一并做）
