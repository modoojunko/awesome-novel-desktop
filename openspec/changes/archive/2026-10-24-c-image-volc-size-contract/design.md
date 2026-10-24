## Context

`client/backend/image_assets/adapters.py` 的 `_native_size("volcengine", kind)` 给封面返回 `("3:4", 768, 1024)`、头像返回 `("1:1", 1024, 1024)`，`_openai_ish_payload` 直接把该字符串作为 `size` 发给 Ark `images/generations`。2026-10-24 对真实端点重放取证（用户自己的配置与 Key）：

- `size: "3:4"` → 400 `InvalidParameter`：`must be 'WIDTHxHEIGHT' or a supported size preset`
- `size: "768x1024"` → 仍 400：`image area must be at least 921600 pixels`
- `size: "960x1280"`（3:4，面积 1228800）→ **200**，b64 正常返回；`n=1`、`seed`、`watermark=false`、`response_format=b64_json` 均被接受

候选派发在 `generation.py` 逐张循环、每次恒 `n=1`（seed 区分候选），故 `n` 无需改动。日志现状：`adapters.py:407` 的 `image_call` 只记 status 与归类后的 kind，供应商 4xx 报文原文被丢弃。

## Goals / Non-Goals

**Goals:**
- 火山封面对真实端点恢复 200 出图（含 2 张候选路径——同一 payload、逐张派发）
- 火山头像同批修复（`1:1` 同为比例字符串，必挂）
- 供应商 4xx/5xx 报文可观测，下次档位漂移可直接从 app.log 定诊

**Non-Goals:**
- 不改 UI 失败文案（维持「供应商返回错误（HTTP 400）」口径）
- 不改 `n`/`seed`/`watermark`/`response_format` 口径，不动 prompt 拼接
- 不做跨供应商尺寸校验层——其他供应商（dashscope `1728*2368`、zhipu/openai/minimax）口径本就合法，真机六供应商逐家过时再补

## Decisions

1. **取值写死在 `_native_size` volcengine 分支**：封面 `("960x1280", 960, 1280)`、头像 `("1024x1024", 1024, 1024)`。元组宽高同时喂资产宽高记录，一处改动全链一致。备选：发预设档位 `"1K"`——否，preset 不控制比例，竖版封面构图会漂；`"768x1024"`——否，面积低于下限。960x1280 是实测 200 的最小合规 3:4。
2. **不引入面积下限校验器**：供应商档位属外部契约，写死取值＋行内注释引用端点约束（≥921600 px²）即可；将来端点改规则时靠新增的报文留痕第一时间看到，不为单点加抽象。
3. **留痕挂在 `generate_images` 非 2xx 分支**（`_classify_payload` 旁）：从响应 JSON 提取 `error.code`/`error.message`/`error.param`（无 JSON 则记原文截断），一行 `event=image_call_error`，总长截断 500 字符，级别 WARNING；沿用现有 image_gen logger 落 app.log。脱敏红线沿用主 spec：只记响应体，MUST NOT 回显请求体/Key/prompt/图片字节。
4. **回归钉法**：单测钉 volcengine 两种 kind 的 payload `size` 精确值（防回退到比例字符串）＋钉留痕行包含 `InvalidParameter` 且不含 Key/prompt 片段。

## Risks / Trade-offs

- [火山端点将来调整面积下限/格式] → 留痕报文可直接定诊，改 `_native_size` 两行即可
- [960x1280 与上传规范化目标 768×1024 不同] → 上传规范化只作用于用户上传；生成资产按适配器返回宽高记录，互不干扰
- [其他供应商可能存在同类暗坑但未实测] → 非本 change 范围；留痕能力对全供应商生效，逐家真机验收时兜底

## Migration Plan

无 DB/配置迁移，部署即生效；存量失败任务走现有「重试」入口即按新尺寸重发。

## Open Questions

（无）
