# c-agent-page-field-truth Design

## Context

助手每轮提示词＝稳定系统前缀（身份＋书情 brief＋域收窄工具协议＋域纪律）＋动态 user 尾（页面名/聚焦/未保存/画像/页签真值/进度/书记忆）＋按需 read_*（`assistant/context.py` 三层模型）。既有判例：动态数据一律进 user 尾（c-agent-prompt-cache 前缀缓存纪律）；页签真值由服务端注入（c-agent-nav「服务端是唯一真值源」）。题材数据单源＝`resolve_genre_context`（genres/service.py，五格＋story KV 题材目录＋tagId→中文 label，全空返回 None）。设定面板身份只编码在前端 thread 键 `set:<panel>`（chatRegistry.threadKeyOf），后端仅按 `set:` 前缀分域不解析面板名。题材写路径已有 c-agent-genre-pick 的 catalog 采纳卡（前端成对写 theme/sub_genre 整包 PUT）。

## Goals / Non-Goals

**Goals:**
- 模型在 `set:genre` 线程免工具调用即知五格填空状态；在任意 `set:*` 线程知面板名；brief 题材行复活。
- 模型按需可细读五格现值（含未填点名）与简介现值。
- 作家口述可经授权卡转写进「主要看什么」（promise_note）。

**Non-Goals:**
- 不做其它面板（world/chars/arc/style/foreshadow）的字段真值注入——它们已有 read_settings 分区可按需读，边际收益低；面板名真值（B）先行铺路，后续按需逐面板接入。
- 不给 theme/sub_genre 开字段级写通道（catalog 卡是唯一题材写路，避免双写路径漂移）。
- 不动前端、不动未保存标记粒度（unsaved 仍页面级标签）。

## Decisions

1. **注入层＝user 尾 note，不进系统前缀**：五格值随作家保存变化，属动态数据——进前缀会废缓存（判例 c-agent-prompt-cache）。面板名虽准静态，但与页签真值（`ch:*` 同机制）同点注入成本为零、代码同构，一并进 note。
2. **渲染单源放 genres/service.py**：新增五格真值渲染函数（含未填点名）紧邻 `resolve_genre_context`/`build_genre_section`，note 构造与 read_settings genre 分区共用；label 解析直接复用 resolve 的产物（不二次查表）。
3. **note 构造放 assistant/context.py**：`build_genre_panel_note(root_path, novel_id)` 与 `build_book_brief_parts` 同模块同风格（async、fail-soft、预算截断）；router 只负责在 `set:genre` 线程调用并拼接。
4. **面板名映射放 router.py**：`_SET_PANEL_ZH` 与 `_THREAD_TAB_ZH` 同处——键集对齐前端 `SETTINGS_ITEMS`（chatRegistry），default/未知键回退「设定」；不共享前端词表（后端独立封闭集，parity 由测试钉）。
5. **brief 题材行修复取 `theme`/`sub_genre`**：`resolve_genre_context` 返回 None（全空）时跳过——语义是「没填就不说」，不是「说未填」（未填状态由 set:genre 字段真值承担，brief 保持 ≤300 字稳定段纪律）。
6. **read_settings 加区不加工具**：genre/intro 是「读书内设定」语义的自然延伸，共享读集已含 read_settings——零 scopes 改动、零新工具名；工具 description 同步列全六分区防模型歧义。
7. **白名单只加 promise_note**：NovelGenreIn 契约已含该字段（VARCHAR200），整卡合并路径零新逻辑；theme/sub_genre 明确排除并在 spec 钉死单一写路。

## Risks / Trade-offs

- [note 变长挤占上下文] → promise_note ≤200 是大头，整段预算截断 ~400 字符；只在 set:genre 线程注入，其他线程零增量。
- [真值与未保存草稿不一致] → 真值=落库值，未保存编辑由既有「［未保存：设定面板…］」标记兜住（模型先提醒再动）；两标记同轮并存语义互补。
- [题材目录写歧义（模型拿四问顶替选题材）] → c-agent-genre-pick 已在设定纪律钉两层「题材」分工；本改动 read_settings(genre) 的 description 明确「现值」语义、与目录工具划清界线。
- [resolve 异常打断对话] → note 构造 try/except fail-soft（与 brief 题材行同风格），失败仅丢注入段。

## Migration Plan

纯后端增量，无存储迁移、无接口变更、无前端改动；回滚＝revert 即恢复原状。

## Open Questions

（无）
