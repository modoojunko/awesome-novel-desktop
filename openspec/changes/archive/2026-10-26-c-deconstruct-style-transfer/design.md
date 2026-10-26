## Context

拆书管线产出 10 维产物，其中「写作文风」（style）经 `settings_map.style_body` 投影进新书文风 KV（三区＋3 条 ≤60 字短例句），「写作技法」（techniques）经 `technique_lines` 并入文风 rules/craft——但建书弹窗默认不勾技法，且例句形态对模型几乎没有模仿价值。正文提示词（write_chapter 模板＋`chapter_writer.build_system_prompt`）把文风三区/例句/禁用词拼进 system 恒定层 `style_block`，而模板「人味写法」节首明文「笔法打架取更有人味的写法」，34 条缺省笔法与现代口语网文腔强绑定，压制书级文风。提示词模板住 prompts 仓（纳管注释由 sync.py 生成，发布走本机 publish.py 打包四档 bin；C端 frozen 态只读已装包，dev 态经 PROMPT_PACK_DEV_DIR 直挂）。

## Goals / Non-Goals

**Goals:**
- 让拆书的原书文风以「成段可模仿样本」形态进入正文 system 恒定层。
- 让写作技法默认随建书进入文风页（并入 rules/craft），用户零额外操作。
- 笔法冲突裁决从「人味至上」反转为「本书文风优先」，AI 指纹底线不退。

**Non-Goals:**
- 不改例句提炼（fewshot-mine）流程及其 3 条 UI 上限。
- 不做量化基线自动蒸馏、不做「灌入已有书」出口。
- 补缝（seam_refill）、AI 体检等轻量路径不注入示范段（省 token，非目标场景）。

## Decisions

- **新键 `style_samples` 而非扩容 `few_shot_examples`**：后者被例句提炼流程（后端 [:3] 截断）、前端 3 条 UI、多处钉子测试深度耦合；新键语义干净（成段示范 vs 短句例句），互不挤占。cap 6 条×500 字（_VALUE_MAX 兜底截长），与 ≤200 字成段产物留足余量。
- **拆书例句全部改投 style_samples**：避免同一批例句双键重复注入；旧任务产物中的短例句照常收进（短但无害，兼容不发版也能用）。
- **保存 payload 仅非空时携带 style_samples**：开书向导 scenario 钉了「payload 仅三区＋例句」，存量书保存流程键集不变，测试与真实流量零扰动。
- **建书默认勾用新标志 `book` 而非复用 `setting`**：`setting` 语义是「进设定页」，techniques 并非独立设定页维度；新标志不污染语义，「（默认不勾）」文案条件同步。后端 IMPORT_ITEM_KEYS 已含 techniques，零后端改动。
- **注入上限取前 3 条**：3×400 字 ≈ 1.2K 字进 system 恒定层，逐章一致保缓存；取前不轮换，保逐字节一致。
- **优先级反转只动人味写法节首与裁决口径**：反AI结构红线七家族、输出契约、素材优先兜底全部不动——朱雀人味率的护城河是红线与输出契约，不是「打架取人味」这句仲裁语；措辞仍保「本节所有规则跟本书文风一起只为一个目的服务：成品像人写的」。
- **prompts 仓与 C端同批双 PR**：模板占位符零增删（示范段作为 style_block 代码拼装的一部分），新旧包/新旧后端任意组合兼容（旧后端把长例截 300 落旧键，无害）；发新包（本机 publish.py，min_client 不 bump）在 C端合入后执行。

## Risks / Trade-offs

- **人味率波动**：优先级反转后，文风非空的书成稿会更贴书级文风、可能拉高某些 AI 指纹——真机验收须跑一次人味检测对比；兜底是红线与输出契约绝对。
- **token 成本**：system 层每章 +约 1.2K 字（示范段）＋并入技法后 rules/craft 变长（上限 100/50 条兜底）；恒定层可被供应商缓存吸收。
- **拆卡成本**：quote 从 ≤60 字扩到 ≤200 字，逐章拆卡 token 微增；style 归并输入（excerpts）变长，由 seg_range 分批既有机制吸收。
- **spec 钉子测试**：prose-writing 主 spec 钉了人味写法节首措辞的测试需随模板同批更新（见 tasks）。

## Open Questions

- 无（发布版本号 2026.10.26-1 为占位，发包时按当日定）。
