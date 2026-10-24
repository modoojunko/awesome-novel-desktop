# Design: 拆书/导入三档切分

## Context

拆书工具链（上传→AI 拆解→产物预览→导出 md / 产物建书）此前无任何权益门禁；MAX 售卖页已把「拆书成设定」列为卖点。四档权益体系（tier-gating）已稳定运行，拆书是最后一个游离在权益体系外的 AI 大能力。

## Goals / Non-Goals

- Goals: 拆书能力按三档收费（免费=正文导入；PRO=AI 拆书＋导出 md；MAX=产物建书）；后端真拦；入口可见＋锁定；售卖文案同步。
- Non-Goals: 不改拆书产物格式/建书幂等语义；不动「去AI味」等其它售卖面漂移（另有挂账）；不做存量任务清退。

## Decisions

- **两个 key 而非一个**：`deconstruct`（PRO：运行＋查看＋导出 md）与 `deconstruct-import`（MAX：产物建书）。导出 md 与建书是同一完成态的两个出口，分属两档，必须可分别门控。
- **门禁端点**：新建任务/续拆/重试上传/导出 → `deconstruct`；import-book → `deconstruct-import`。列表/详情/产物预览/取消/删除不设门（免费存量任务只读保留；取消是止损操作）。
- **require_ai_access 而非 require_tier_access**：拆书消费作者自持写作大模型，未配 Key 应引导配置（与 ai-generate 同类），不进 KEYLESS_GATE_KEYS。
- **旧快照 shim 按 key 分档**：`_LEGACY_IMPLICIT_FEATURES`（后端）与 `LEGACY_IMPLICIT_FEATURES`（前端）改为 {key: 最低档}；image-generate/deconstruct 按 PRO、deconstruct-import 按 MAX——max 键不给 trial/pro 放行。
- **入口口径**：与全应用一致「入口一律可见」，免费/标准用户在创建页与出口弹窗看到（PRO）/（MAX）标记，点击走对应档升级弹窗。

## Risks / Trade-offs

- [存量免费用户失去 AI 拆书入口] → 只读保留历史任务与产物预览；正文导入免费不受影响。
- [旧快照隐式放行面扩大到两个新 key] → 与 image-generate 同机制、S端 契约同批发 key 后即可退役 shim。
- [导出与预览分属两档（预览开放、导出收费）] → 预览是只读 HTML 弹窗，导出是落盘文件，产品语义即「带出去收费」。
