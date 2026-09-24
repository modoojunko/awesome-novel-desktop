## 1. 双端影响判定

- [x] 1.1 双端影响判定：纯 C端 后端（迁移端点/卷纲校验/AI 端点错误码），无用户可见界面改动——Design Impact「不适用」，无需原型先行

## 2. 迁移端点白名单与参数化

- [x] 2.1 `start`/`preview` 入参先过 `validate_candidate_filename`，不合法返回 400 可读文案——diff 贴进 change 目录
- [x] 2.2 `engine.py` ATTACH 路径做 SQL 字面量转义（双写 `'`）——diff 贴进 change 目录
- [x] 2.3 单测：start 对 `../x.db`/子目录/含引号名返回 400 且无文件系统副作用——`pytest tests -k migration` 绿

## 3. 卷纲退役键补 plot_nodes

- [x] 3.1 `_retired_reject` 元组补 `plot_nodes`——diff 贴进 change 目录
- [x] 3.2 单测：PUT 携带 plot_nodes → 422 且文案含字段名；不含退役键照常 200——`pytest tests -k retired` 绿

## 4. 非法卷引用 400

- [x] 4.1 抽 `_vol_no` 助手（解析失败抛 400），三处调用点替换——diff 贴进 change 目录
- [x] 4.2 单测：非法 vol_ref → 400；合法引用行为不变——`pytest tests -k ai_plan` 绿

## 5. 回归

- [x] 5.1 `pytest client/backend/tests`（全量）输出结论贴进 change 目录
- [x] 5.2 `ruff check client/backend` 输出结论贴进 change 目录
- [x] 5.3 本 change 无前端改动，design:lint / design:check / tsc / vitest 不适用（判定依据见 1.1）
