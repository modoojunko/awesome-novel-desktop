# c-og-badge-archived-confirm · Design

## Context

后端章 `status` 单列生命周期 outline→draft→confirmed→archived；归档在 `archive/dossier.py` 收口时覆写为 `archived`，`confirmed` 不复存在（章纲确认事实另有 `outline_status`/`confirmed_at` 列，但前端计数不读它们）。前端 `useOutline.deriveOutlineStatus` 从树 meta 的 `status` 派生三态，`confirmedCount` 因此对归档章恒为零。评审（前端/后端/架构师三路）已逐点实勘：消费方全量、409 内部调用方、并发窗口、备份 round-trip、parity 机制——结论沉淀于本文件与 proposal，实现不再重开论证。

## Goals / Non-Goals

**Goals:**
- 全归档书的「写作 N/N 章纲」徽标语义正确（归档＝章纲已定稿）。
- 堵住 confirm×archived 数据腐化洞（不可逆的 total_archives 虚高）。
- e2e 夹具与真实后端口径一致（消灭反向说谎的桩）。
- 与 c-og-confirm-gates 的同位改动零冲突合流。

**Non-Goals:**
- 不改后端状态机（不保留 confirmed、不做 outline_status 归一、不迁移数据）。
- 不做 OgPane 门禁 UX（归 c-og-confirm-gates）。
- 不闭并发 TOCTOU 窗口与 versions.py restore 同族洞（跟进票）。

## Decisions

1. **投影放在前端派生函数，不放后端**。`deriveOutlineStatus` 是徽标/树 dot/删除盘点三面的共同上游，单点修＝三面全修；改 computed 只修徽标会让树上归档章仍黄点、三面劈叉。备选「后端树接口归一 outline_status」否决：前端不读该列，无效代码；「归档不覆写 status」否决：`status=="archived"` 是树 archived 标志（volumes/service.py:58）、frontier、unconfirm 409、unarchive 记账、`resolve_prev_ending` 的承重墙。

2. **判据用 `meta.status === "archived"`，置于 chapterData 判定之前，不引入 `outline_status`/`archived` 布尔**。分支顺序 load-bearing：真归档章的 chapterData 带 `outline.summary`（走 chapterData 分支会回落 in_progress，徽标 4/4 跳 3/4）；preview 的 chapterDetail 甚至无 outline 字段（会落 unfilled）。`archived` 布尔是可选字段（旧桩可缺省）；`outline_status` 是同源派生列（prose 非空即 in_progress），与前端三态（outline.summary 口径）不同源，混入会打架——树契约**有吐** outline_status（volumes/service.py:57），不读它是「只认单一事实源」的决策，不是「契约不吐」。

3. **409 守卫逐字复制 c-og-confirm-gates（bc0a4380）的 hunk**，含注释与文案「本章已归档，恢复编辑后再确认章纲」，并同样把 `chapter_repo` import 上移。两侧同文同位→git 自动归并，先合后合都零冲突；该分支 proposal 明文认领此洞，PR 描述注明去重。守卫位置在 `load_chapter`/`tier_or_gate` 之前：免费档 `tier_bypass` 直接 valid，放 tier 后守卫永远到不了；PRO 档会先吃 gate 的 400 拿错错误码。

4. **测试钉是本修唯一的硬回归门禁**。parity 是活体对拍（pixelmatch 阈值 0.2%≈2592px）且不进 CI、design-parity-book 不在 design:check；徽标级 diff <0.04% 永远不会红——桩必须同批改的理由是夹具诚实性，不是防红灯。故 vitest 徽标文本钉（全归档树→「4/4 章纲」）必须落，pytest 须含「PRO 档 409 而非 400」的排序钉（免费档用例证明不了守卫先于 gate）。

5. **原型四处判定同批对齐**（book.html 徽标计数/dot/删除盘点/firstPending），种子数据（c2=已归档＋已确认）下新旧规则像素零差，design:check 不受影响；ADJUSTMENTS.md 登记一处条目。原型与实现规则不同步会让 parity 夹具语义漂移，即使像素永远撞不到阈值。

## Risks / Trade-offs

- **与 c-og-confirm-gates 的合流顺序**：任一顺序都可自动归并；若对方先合，本分支 rebase 后守卫 hunk 成 no-op，测试照跑（对方未写 confirm×archived 测试，本包 pytest 四例仍是净新增，无撞名——已实勘其 bc0a4380/38ec90e8）。
- **投影的字面失真**：未手点确认就归档的章也会计入「已确认」计数。这是单列生命周期下唯一无损的有损投影（后端不保留归档前确认态）；c-og-confirm-gates 落地「归档双硬门」后字面为真，代码注释标明该时点。
- **残余 TOCTOU**：confirm 与归档 job 并发在途的毫秒级窗口守卫挡不住（同 session 重读因 `expire_on_commit=False`+WAL 无效，条件写 CAS 是唯一真解但动全书写入口）。单用户桌面应用、两动作分属不同 UI 流，联合概率可忽略——记档不防。
- **409 的前端体验**：api.ts 透传 detail 上 toast（「本章已归档，恢复编辑后再确认章纲」），恢复编辑入口在相邻正文页签——动线可用；OgPane 按钮对归档章仍可点（能点但注定 409），正式禁用随 c-og-confirm-gates。
