> 纯后端改动，无 UI 变更，免原型（依据 proposal「Design Impact」：不触界面与共享段）；
> 回归不含 design 门禁，以后端 pytest／ruff 为准。

## 1. 适配器尺寸契约

- [x] 1.1 改 `client/backend/image_assets/adapters.py` 的 `_native_size` volcengine 分支：封面 `("960x1280", 960, 1280)`、头像 `("1024x1024", 1024, 1024)`，行内注释引用端点约束（`WIDTHxHEIGHT` 写法＋面积 ≥921600 px²，2026-10-24 实测）——验证：单测断言 payload `size` 精确值
- [x] 1.2 单测钉尺寸防回退：`tests/test_image_generation.py` 断言 volcengine cover/avatar 两 kind 的 payload `size` 与资产宽高记录；另钉 aliyun/zhipu/openai/minimax 尺寸口径与改动前逐字一致——验证：`pytest tests/test_image_generation.py` 绿

## 2. 失败留痕

- [x] 2.1 `generate_images` 非 2xx 分支加一行 `event=image_call_error` 留痕（WARNING，沿用 image_gen logger）：提取响应 JSON 的 `error.code`/`message`/`param`，无 JSON 则记原文，总长截断 ≤500 字符——验证：FakeClient 返回 400 InvalidParameter 体时 caplog 断言含 `InvalidParameter`
- [x] 2.2 留痕脱敏钉：断言留痕行不含 API Key、prompt 片段或 b64 字节，且请求体不被回显——验证：同批单测断言

## 3. 回归与真机

- [ ] 3.1 后端全量 pytest 绿＋`ruff check` 显式跑绿——验证：命令实际输出结论
- [ ] 3.2 demo 栈换包真机冒烟：对「13路末班车」点封面「重试」（或新发 2 张候选），候选图 ≥1；`app.log` 出现 `event=image_call ... status=200` 且无 `image_call_error`——验证：日志行＋候选图截图
  - 2026-10-24 部分完成：出站 payload 实抓 `size: 960x1280`（其余参数不变）、`image_call_error` 留痕落行、真端点 200 出图由重放取证证实；**真机 200 出图待用户重录 Ark key 后点「重试」收官**（旧配置随 stale-WAL 重建丢失，配置骨架已重建）
- [x] 3.3 实现按仓库规矩 `openspec-archive-in-implementation-pr`：合入前 sync 本 delta＋移档 archive，随实现 PR 同批——验证：PR 内含归档移动，`openspec validate` 绿
