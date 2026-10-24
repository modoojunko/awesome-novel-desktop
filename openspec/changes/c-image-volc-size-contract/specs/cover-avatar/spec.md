## ADDED Requirements

### Requirement: 供应商尺寸契约与失败留痕

发往火山方舟图像端点的请求 `size` MUST 是 `宽x高` 像素写法，MUST NOT 使用比例字符串（如 `3:4`、`1:1`）；所选尺寸 MUST 满足端点的面积下限（≥ 921600 px²）：封面 MUST 为 3:4 竖版的 `960x1280`，头像 MUST 为 `1024x1024`。其他供应商沿用各自合法尺寸口径，本契约不改变其取值。供应商返回 4xx/5xx 时，系统 SHALL 在日志中留痕供应商错误体的 `code`、`message`、`param` 字段（单行、总长截断 ≤500 字符）；留痕 MUST NOT 记录 API Key、prompt 正文、图片字节或完整请求体。

#### Scenario: 火山封面按像素尺寸出图

- **WHEN** 使用火山 provider 发起封面生成调用
- **THEN** 请求 payload 的 `size` MUST 为 `960x1280`，端点不再因 size 返回 400 InvalidParameter

#### Scenario: 火山头像按像素尺寸出图

- **WHEN** 使用火山 provider 发起角色头像生成调用
- **THEN** 请求 payload 的 `size` MUST 为 `1024x1024`

#### Scenario: 供应商 400 报文可观测

- **WHEN** 供应商对图像调用返回 400（如 size 非法）
- **THEN** 日志 SHALL 出现一行含供应商 `error.code` 与 `message`（如 `InvalidParameter`）的留痕，且不含 Key、prompt 正文或图片字节

#### Scenario: 其他供应商尺寸不受影响

- **WHEN** 使用 aliyun/zhipu/openai/minimax provider 发起生成
- **THEN** 请求中的尺寸口径 MUST 与本次改动前一致
