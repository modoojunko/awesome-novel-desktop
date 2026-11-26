## Context

现状（见 proposal.md - Why）：节奏页签把「展示预填」当配置展示（`VolumePacingPane` 的 `shown = config ?? prefill`），后端已返回 `source` 但前端未消费；注入侧实际解析是 `volumes.pacing.resolve_config`（卷列 → 书级默认 → 无），与预填链（上一卷 → 书默认 → 题材映射 → 兜底）不是同一条。两者不一致时（之前某一卷有定制、书级默认另一套、本卷未保存），页面显示一套、拆章用另一套，且拆章 `beat_context` 返回空时没有任何信号。

评审发现的关键约束（已核对代码）：
- `next_chapter_anchor` 的 `next_no` 是全书号，`beat_of` 的章号是卷内号；多卷书直接错位（第 2 卷第 1 章会被当成第 41 章）。
- `book_pacing_default` 只返回 `{preset, steps_len}`，不是完整配置；`resolve_config` 的书默认分支会用 `build_config(..., ch1_extra_on=(volume_no==1))` 补齐步表与开篇开关。纯函数若只收两个参数会丢这两样。
- `drawSession.loadDraw` 只 `JSON.parse`，不校验版本；章节抽卡载荷目前也没有 `pacing`。设计里的「bump 版本」必须真的校验。
- 基线 `chapter-plan-ai` spec 仍写「未排段 SHALL NOT 追加拍位」，而代码/本 change 是「已配即注入」；必须在本 change 修正，否则 spec 自相矛盾。
- 右栏节奏 AI 动作目前用 `config ?? prefill` 取配置并写回；书默认与上一卷预填并存时会把上一卷写成本卷配置。

## Goals / Non-Goals

**Goals:**
- 页签查看态一眼回答：这套节奏从哪来、拆章/正文会不会照它走（还要看章数目标）、没存/读不出时怎么办。
- 页签、右栏、拆章预告、注入链用同一个 `effective` 口径，消除「显示一套、实际一套」。
- 拆章入口出卡前给出正面确认（本章将走第 K 步＋任务句）或中性缺失提示，且不拦人；多卷书按卷内章号推导。
- 保存节奏后旧批次不会被当前拍位文案/角标错误标注，缓存版本真正生效。
- 修正基线 spec 的「已排/未排」口径，明确 `planned` 只影响体检与派生徽章。

**Non-Goals:**
- 不改 `resolve_config` / `beat_context` 的注入优先级与素材内容，不自动保存预填，不改「未配置=提示词逐字同升级前」的承诺。
- 不做每章 toast/红点/强制引导，不做 AI「缺节奏检测」，不新增 AI 调用或提示词模板，不发提示词包。
- 不改拍位公式（含 `step_idx` 可能大于步表长度的既有行为）、不改 ghost/配额口径、不改 `planned` 的业务含义。
- 不把提示加到剧情抽卡/推演/正文各自入口（页签为唯一权威状态面，拆章是流水线首个消费者）。

## Decisions

### D1. `effective` 由后端单源解析；纯函数必须补齐完整配置
在 `volumes/pacing.py` 抽 `effective_of(config, book_default, volume_no) -> tuple[dict | None, str | None]`：
- `config` 可解析 → 原样返回归一配置，source=`volume`；
- 否则 `book_default` 非空 → `build_config(preset, steps_len, ch1_extra_on=(int(volume_no) == 1))`，source=`book`（补齐步表、开篇开关、planned=false，形状与卷列配置一致）；
- 都空 → `(None, None)`。

`resolve_config` 改为读完卷行/书默认后调用该函数；GET 用已读到的 `config/book_default/vol.volume_no` 调用，不新增查询。**禁止**把书默认裸对象 `{preset, steps_len}` 直接当 `effective`（前端编辑态会 `shown.steps.map` 崩，第 1 章开篇状态也会错）。

`prefill`/`source` 保持既有语义：卷列有配置时 `prefill=config`、`source=volume`；卷列无配置时才返回预填链。`plan.steps_len/n` 改用 `effective ?? prefill`。新增 `config_present`（卷列非空）与 `config_invalid`（非空但归一失败）区分「没存」与「读不出」。

### D2. 页签、编辑基线、右栏统一取 `effective ?? prefill`
- `shown = effective ?? prefill`，`baseline = effective ?? prefill`（两者同源；否则书默认+上一卷预填时零改动也 dirty，点保存会把书默认固化掉）。
- 段表/体量/剧情安排按 `shown` 的每段章数推导。
- `VolumeAssistPanel` 的排段/调套路/润说明读取与写回基线同样改 `effective ?? prefill`；书默认+上一卷预填时排段用书默认，避免一次排段把上一卷写成本卷。
- `planned` tag 取 `data.config?.planned`（书默认/预填一律未排），不用 `shown.planned`。

### D3. 来源行用常态文字，四态；承诺区分「已保存」与「会照它走」
- 来源行（`.vc-fine` / 既有 `.none` 语汇，不新增胶囊）：
  - `本卷设置 · 拆章会照它走`
  - `全书默认 · 拆章会照它走`
  - `题材默认 · 还没存到这一卷` / `之前某一卷的设置 · 还没存到这一卷`
  - `本卷设置读不出来 · 请重新保存`（有书默认时加「暂时按全书默认」）
- 承诺成立条件＝`effective` 非空 **且** `chapter_target > 0`。目标未设时写「已保存；填上本卷章数目标后，拆章、剧情、推演、正文才会照它走」；底部不再说「都照这张表来」。
- 出口：`effective` 空且为预填 → 主按钮「保存到这一卷」（PUT 预填，`planned=false`）；`effective_source=book` → 次级「改为本卷设置」（PUT 生效的书默认）；`volume` 无 CTA。`config_invalid` → 「编辑节奏」修复入口。
- 未配置是合法常态，不用 warn/err 徽标（S-R3）；`config_invalid` 与过期批属真实异常，允许 warn。
- `planned` 与「会照它走」相互独立：tooltip/旁注写明「未排只表示还没让 AI 排段，不影响拆章/正文按套路走」。spec 的基线口径同步修正（见 D7）。

### D4. 拍位预告走锚点，按卷内章号，与注入共用 `beat_context`
- `next_chapter_anchor` 已持有卷内 `ch_no = _next_chapter_no(...)`；拍位用 `ch_no` 推导，`next_no` 只留在标题/行号。
- 给 `beat_context` 加可选关键字参数 `config`（已解析配置），锚点先 `resolve_config` 一次再传入，避免重复解析；仍复用同一函数生成 `task`/`step_task`/`ch1_extra`，与素材/角标同源。
- 锚点增量字段：
  - `pacing_effective`：`config is not None`；
  - `pacing_preview`：`{step_idx, step_name, step_task, ch1_extra}`，无拍位 null；
  - `pacing_reason`：无配置 → null；有配置且 target≤0 → `no_target`；有配置且 ch_no>target → `out_of_target`；有配置但 beat 仍空 → `unknown`；否则 null；
  - `pacing_fingerprint`：见 D5。
- 三方向态五态渲染（确认＋任务句 tooltip/第二行；未存；无目标；超目标；兜底）。提示在锚点返回后即可见（忙碌态与三方向态都渲染）。「去节奏页签」接 `onGoPacing`：关弹窗、导航到正在拆的那一卷、切「节奏」页签；忙碌中点击按既有取消语义弃批（不承诺退款），请求未发出则不产生调用。
- 客户端三字段 optional：缺字段/旧后端按「未知」处理，不误报缺节奏；只有 `pacing_effective === false` 才出缺失提示。
- 预览只读：不调模型、不记账、不落库、不进 `warnings`、不进拆章素材/提示词。`pacing_preview`/`reason` 字符串不得出现在捕获的 prompt 中（回归断言）。

### D5. 会话指纹与缓存版本必须真的生效
- 服务端提供 `pacing_fingerprint`（对 `step_idx/step_name/step_task/ch1_extra/是否有生效节奏` 做稳定哈希）；锚点与 `ai-directions` 同源返回，同一章同一配置下相等。
- 会话载荷持久化 `pacingFingerprint`；内存批与 localStorage 恢复都比对当前锚点指纹。不一致（含从无到有、从有到无、只改任务句、改第 1 章额外交代、目标清空）→ 保留旧批可见但标「节奏或章数目标变了——这批是之前出的，重抽才会按当前设置」，抑制「本章将走…」与旧拍位角标；「重抽」不继承旧批的 exclude（旧批是旧拍位产物），走 `freshRedraw`/清空。
- 章节抽卡使用独立版本键（如 `cp-draw:v2:{pid}:{volRef}`）或在 `useChapterPlan` 恢复处显式校验 `v === 2`；旧载荷丢弃。**不改** `loadDraw` 的全局语义、**不动**卷抽卡 `v:1`。
- 指纹一致时既有「误关重开原样恢复、不重复计量」不变。

### D6. 文案定稿（全用作家语汇）
- 预告：`本章将走：第 2 步 · 用金手指解决`（任务句放 tooltip/第二行）。
- 缺失：`这一卷还没存节奏——拆章不会照套路走（可选）`＋`去节奏页签`。
- 无目标：`本卷还没填章数目标，这一章先不按套路分步（不影响拆章）`。
- 超目标：`本章已超出本卷章数目标，不再按套路分步（不影响拆章）`。
- 兜底：`这一章暂时算不出第几步（不影响拆章）`。
- 过期批：`节奏或章数目标变了——这批是之前出的，重抽才会按当前设置`＋`重抽`。
- 读不出：`本卷设置读不出来 · 请重新保存`。
- 来源建议行：`之前某一卷的设置（5 章）还没存到这一卷`（不写死「上一卷」）。
- 语气：常态未配置＝info；「未设章数目标」只保留既有体量行的一条 warn，来源行用 info 说明、不重复警告；`config_invalid`/过期批＝warn；禁止 err；按钮均为动词。

### D7. 基线 spec 口径修正
`chapter-plan-ai` 的「拆章素材包与输出契约」改为「已配节奏的卷（卷列已保存且可解析、或书级默认生效）即追加拍位注记；未配节奏不追加；`planned` 不参与判定」；场景「已配卷拍位进素材」去掉「并排段」，新增「未排段仍注入」与「书默认生效也注入」。这是让 spec 追上代码现状，不是改注入行为。

## Risks / Trade-offs

- [P0：用 `next_no` 推导，多卷书系统性错位] → 固定用卷内 `ch_no`；补第 2 卷第 1 章、ghost 空洞两条测试，断言 preview == `beat_context` == 出卡角标。
- [`effective` 不是完整配置导致前端编辑崩/开篇开关丢] → `effective_of` 用 `build_config` 补齐，并与 `resolve_config` 做逐字段 equality 测试（vol1/vol2、仅书默认、仅卷列）。
- [无章数目标仍承诺「照它走」] → 承诺加 `target>0` 条件；页签第三态文案；锚点 `no_target` 同口径。
- [主展示切 effective 后，编辑零改动被判脏] → `baseline` 与 `shown` 同源；补 book+prev、vol2 两条零改动测试。
- [旧 mock/旧后端缺字段被当成 false] → TS optional；UI 只在 `=== false` 时提示；补旧形状锚点测试。
- [指纹只覆盖步号/步名，漏任务句/开篇交代] → 指纹覆盖 `step_task`/`ch1_extra`/effective；补「只改任务句」「改额外交代」两条过期测试。
- [缓存版本 bump 实际不校验] → 章节独立 key/显式 `v===2`；补 v1 丢弃测试；不动卷抽卡 v1。
- [过期批重抽继承旧 exclude] → 走 fresh 重抽/清空；补请求体断言。
- [提示在出卡调用已发出后才可见，退出会弃掉已计费批] → 明示「按既有取消语义弃批、不承诺退款」；若在请求发出前点击则不产生调用；这是非阻断的代价，登记为已知限制。
- [书默认+上一卷预填时右栏排段写错] → 右栏统一 `effective ?? prefill`；补组件/接口测试。
- [A/B 断言只查子串，证明不了「素材逐字不变」] → 固定夹具 golden 快照 + 精确计数 + `mat` 键集合 + prompt 捕获中不得出现 preview 字段 + preview/beat_context 矩阵 equality + 仅书默认也注入 + 锚点不产生 token log。
- [配置非法读不出被说成没存] → `config_present`/`config_invalid` + 读不出文案；补坏 JSON/未知 preset/`{}`/`[]` 测试。
- [step_idx 可能大于步表长度（破案套路 12 章/5 步）] → 既有公式不改；preview 如实暴露；pin 测试登记为已知限制。
- [ghost 空洞下卷内号与配额口径不同] → 拍位按卷内号、配额按主线；pin 测试，不改行为。
- [锚点在手动开卡/自检补锚也会调用，多算 preview] → 只多一次轻量解析，可接受；后续可缓存。
- [提示词仓 `chapter_selfcheck.prompt` 注释「已排卷才有」与代码不符] → 本 change 不动提示词仓（避免无行为收益的 pack 发包），在 change 登记已知限制，留给独立提示词变更。
- [TOCTOU：预览后配置被另一标签页改动] → 出卡角标/指纹以生成时为准；过期批规则覆盖；不追求跨标签页强一致。
- [既有 bool 归一接受字符串 `"false"` 为 True] → 本 change 不改归一语义（会动存量行为），登记为已知限制；脏值测试只钉「坏 JSON/未知 preset 按未配置回退」。

## Migration Plan

- 无数据迁移：接口只加字段，旧客户端忽略；老卷/老书 `effective` 为空时行为与提示词逐字同升级前。
- 回滚：回退前后端代码即可；`effective` 等字段纯读，无落库副作用；章节抽卡缓存换版本键后旧载荷自然丢弃，无需清理。
- 提示词包：不发布（素材零改动）。

## Open Questions

- 来源行放摘要之上还是体量行之下、任务句用 tooltip 还是第二行，留原型阶段按 880×760 视口实测决定（不影响接口与状态机）。
