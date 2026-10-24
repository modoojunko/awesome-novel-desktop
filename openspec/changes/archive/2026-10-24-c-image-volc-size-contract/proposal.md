## Why

火山方舟图像端点拒收适配器发出的 `size: "3:4"`/`"1:1"` 比例字符串（HTTP 400 `InvalidParameter`：必须是 `WIDTHxHEIGHT` 或受支持的尺寸档位，且图像面积 ≥ 921600 px²），导致火山链路的封面与头像生成**全量失败**——火山是封面生成的默认供应商路径，2026-10-24 本地实测实锤（原始报文重放取证，详见 design）。这是「真机六供应商」验收抓到的第一个真 bug，修复前火山用户无法生成任何图像。

## What Changes

- 适配器给火山（volcengine）发的 `size` 从比例字符串改为像素写法，并满足面积下限 921600 px²：
  - 封面：`"3:4"` → `"960x1280"`（保持 3:4 竖版构图，面积 1228800，已对真实端点验证 200 出图）
  - 头像：`"1:1"` → `"1024x1024"`（面积 1048576）
- 供应商调用失败（4xx/5xx）时把供应商返回的错误体（`error.code`/`message`/`param`，截断 ≤500 字符）落一行日志，消除本次「只记 `status=400 result=invalid`、真实 InvalidParameter 报文零留痕、只能靠重放取证」的观测盲区。
- 候选拴派发方式不变：`n` 恒为 1、候选由 `generation.py` 逐张派发（seed 区分），本次不动 `n`/`seed`/`watermark`/`response_format`（均已实测被端点接受）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cover-avatar`: 新增一条「供应商尺寸契约与失败留痕」Requirement（delta 用 ADDED 形式落 specs/cover-avatar/spec.md）。注意：本 change 叠在仍活跃的 `c-image-generation`（同 capability，含「供应商适配与错误分类」Requirement）之上，后者尚未归档进主 spec，故本 delta 不引用、不修改其 Requirement，归档顺序无关。

## Impact

- 代码：仅 `client/backend/image_assets/adapters.py`（`_native_size` 火山分支、`generate_images` 失败日志一行）与 `client/backend/tests/test_image_generation.py`（钉尺寸值与留痕行为）。
- 不涉及前端、提示词仓、DB schema、权益门控。
- Design Impact：纯后端契约与日志修复，**无用户可见界面改动**（UI 上的失败文案「供应商返回错误（HTTP 400）」维持现口径）；不触碰两端共享段，免原型。
- 风险：火山是封面默认供应商路径，修复后封面/头像才能真实出图；其他供应商（dashscope `1728*2368`、zhipu/openai 像素写法）格式本就合法，不在本次范围。
