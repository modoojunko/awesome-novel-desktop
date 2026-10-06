# design — c-api-config-vendor-defaults

## Context

动机见 proposal.md。现状约束：

- 创建表单（`ApiConfigForm`）只有名称/供应商/Base URL/API Key/接口格式五格，**无模型字段**；`CreateApiConfigBody` 与 `create_api_config` 均不接受 `models`（更新链路才有）。
- 供应商常量族住前端 `ProviderIcon.tsx`（`VENDORS`/`VENDOR_FORMAT_LOCK`/`FORMAT_PLACEHOLDER`/`VENDOR_LABELS`）；后端另有 `connection.py` 的 `VENDOR_MODEL_CANDIDATES`（探针兜底候选，现仅 deepseek 三个实测 id）。
- 旧拍板「URL 不预填」（2026-09-06）被本 change 的 2026-10-05 拍板反转。
- 与 `c-api-config-save-gate` 的探针 id 序列（配置已选模型 > 列表首个 > vendor 候选首个）协同：预填模型名后「配置已选模型」恒有值，消掉「探针 id 是猜的」误拦面。

## Goals / Non-Goals

**Goals:**

- 选已知供应商后用户只填 Key 一步到位；预填值有据（实测/官方文档）、可改、不被劫持。
- 预填模型名一路通到落库与保存门禁探针。

**Non-Goals:**

- 不做 URL 自动「纠正/改写」用户输入（只在选供应商时刻填默认值）。
- 不动朱雀面板（独立端点、无用户可填 URL）；不回填已存配置。
- 不改「测试连接」/保存门禁判据（分别在 `c-ai-availability-fixes`、`c-api-config-save-gate`）。

## Decisions

1. **登记表住前端单源**（`ProviderIcon.tsx` 或新 `vendorDefaults.ts`），键＝vendor×api_format，值＝base_url＋默认模型＋备选候选。备选「放 docs/contracts JSON 双端消费」——后端无消费点，过度设计，否。
2. **覆盖规则＝「空或仍为预填值才覆盖」**：切供应商/切格式时只填「用户没手改」的字段。备选「切供应商即全量覆盖」——会吃掉用户已粘的地址（含内测用户边改边试的修正过程），否。
3. **create 负载补 `models`**（`schemas.py`/`service.create_api_config`），模型名称落 `models` 首项；保存门禁探针自动吃到「配置已选模型」。
4. **登记数据纪律＝有据才登记**（沿候选册「没有把握就留空」纪律）：DeepSeek 首批全量——`https://api.deepseek.com`＋默认 `deepseek-v4-pro`（内测用户在用档）、备选 `deepseek-v4-flash`/`deepseek-v4-flash-vision-exp`；DeepSeek×anthropic 无实测端点（实测 404），该组合留空。其余供应商按官方文档核对后登记（GLM×anthropic 的 `https://open.bigmodel.cn/api/anthropic` 仓内已有实测记载；模型 id 一律实测/查文档后填，禁编造）。后端 `VENDOR_MODEL_CANDIDATES` 同批补齐对齐（探针兜底职责不变）。
5. **编辑态不预填**：编辑弹层供应商锁定（`.vfix`）、值是已存值，预填只服务创建流。

## Risks / Trade-offs

- [厂商官方地址/模型 id 漂移或登错] → 表可更新且字段用户可改；错误登记比裸填更易被发现（保存门禁当场报）；首批只放有据值。
- [默认档选 `deepseek-v4-pro`（非最便宜的 flash）] → 取内测用户在用档为默认，备选留在表里；用户可改，成本自担（BYOK）。
- [预填让「探针 id 被拒焊死保存」的缺口收窄但未全消（无登记值的供应商仍可能缺 id）] → 由 `VENDOR_MODEL_CANDIDATES` 补齐（tasks 2.2）与 save-gate 判败点名所试 id 承接。

## Migration Plan

无存量数据影响（只改创建表单与 create 负载）；create 增加 `models` 为加键兼容。回滚＝还原提交。

## Open Questions

（无）
