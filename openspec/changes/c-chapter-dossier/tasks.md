# c-chapter-dossier 任务清单

## 1. 立项期前置（开发前完成）

- [ ] 1.1 提取质量 baseline 评测：3-5 本样章跑四域提取（临时脚本挂真模板），人工标采纳率/驳回原因，形成上线对比基线
- [ ] 1.2 原型先行：docs/design-c/prototypes 工作台稿加「章档」页签（四域行/待确认/进度/失败/逃生阀/未提取态），ADJUSTMENTS.md 登记偏差

## 2. 数据层

- [x] 2.1 models/chapter.py 四张章子表（字段照 design D2）＋chapters.dossier_stale 列（server_default）＋models/__init__.py 注册
- [x] 2.2 chapter_dossier_jobs 表（state/per_domain/error/prose_hash，章唯一）
- [x] 2.3 chapters/store.py：assemble/拆装加 dossier 键（presence-gate）＋_CHILD_ATTRS/_child_replace_plan 接四子表
- [x] 2.4 backup/importer.py dossier 拆装补接；roundtrip e2e 断言四域形状（含 accepted/pending/证据句）
- [x] 2.5 frontier.py revert_to_chapter 清理清单扩四子表删除（返回计数，照 stale_marked 先例）

## 3. 归档流水线（后端）

- [x] 3.1 archive/router.py 受理化：受理返回 {accepted, model_ready}；哈希记录；ghost 409；模型未就绪同步走 finalize
- [x] 3.2 archive/dossier.py（新）：每章键控单飞＋跨章信号量＋job 状态落库＋启动 sweep（extracting 无线程→failed(interrupted)）
- [x] 3.3 finalize_archive 单源收口函数（四域行+archives+hooks mentioned+status/计数同事务）；摘要调用搬进 job、失败降级不变
- [x] 3.4 部分成功口径落地：每域二值终态、重试只跑 failed 域、跳过提取走 finalize（skipped 态）
- [x] 3.5 存量迁移：reconcile set_changes/relations pending 行物化进子表；char_states pending 置 rejected；run 端点 kind 白名单收缩 hooks/lore（退役 kind 400＋提示）
- [x] 3.6 pytest：受理/成功收口/失败重试/跳过/重启 sweep/哈希漂移/ghost/幂等重受理

## 4. 提取链（后端）

- [x] 4.1 prompts/chapter_archive_extract.prompt（<<system>>/<<user>> 分层，system 零占位符）；过 tests/test_prompt_layering.py
- [x] 4.2 提取服务：一次调用 json_mode max_tokens=1600；输入组装（正文≤6000/世界摘要/上章累计/cast/名册）；解析二值纪律（解析失败=failed、缺键=空数组）
- [x] 4.3 后处理：证据句宽松校验（不匹配保留+标 unverified）、别名映射、名册外标 unregistered、每域截 6 条+clamp
- [x] 4.4 记账：archive_extract 四域分 operation＋fail 强制记账
- [x] 4.5 pytest：模板分层/解析矩阵/证据校验不重试/名册三态/上限截断/首章无基线

## 5. 采纳与端点（后端）

- [x] 5.1 dossier 端点族：单章 GET（rows+extraction+progress+stale）、PATCH 采纳/驳回/恢复、DELETE 已采纳行、POST 补提取、GET preview 累计预览
- [x] 5.2 采纳 rowcount 竞态校验（409「章档已重新提取」）；重归档覆盖警示所需行数进单章 GET
- [x] 5.3 pytest：批量/逐条采纳、删除退出消费、恢复、竞态 409、重归档整体覆盖+audit 留痕

## 6. 消费链（后端）

- [x] 6.1 build_story_state_upto 查询单源（过滤主线∧archived∧非 stale、四域折叠去重、章近优先截断）
- [x] 6.2 _story_state_block 单源渲染（定位句+四小节+防泄底规则行）；material_markdown 与 to_prompt 同位注入；空块逐字回归
- [x] 6.3 validate_polished_prompt 条件锚（有状态块须保留段标题）
- [x] 6.4 prompt-sources 第七来源＋缺口标注（缺 N 条未确认/上一章未归档）
- [x] 6.5 pytest：合并去重四形态/unarchive 不消费/stale 跳过+块头注记/预算硬闸/golden 两路逐字一致

## 7. 重写级联（后端）

- [x] 7.1 rewrite 事务内：源章行删＋下游 dossier_stale 置位（返回计数）
- [x] 7.2 重归档成功清 dossier_stale；保存/归档清除语义对齐 stale 先例
- [x] 7.3 pytest：级联跨卷/ghost 排除/unarchive 保留不消费/重归档清 stale

## 8. 前端

- [ ] 8.1 useChapterData：archiveJob 受理态＋事件真置位派发＋锁定信号＋服务端恢复
- [ ] 8.2 ChapterWorkspace：章档页签接入（数组+徽标+条件挂载）；归档进度分步 UI（操作页签归档卡原位+页签顶部）；软锁（编辑器/归档/取消归档禁用）
- [ ] 8.3 失败/逃生阀/模型未配置三分文案：重试、跳过提取（confirm+代价）、model_ready 提示+配置入口
- [ ] 8.4 DossierPane：ProposalRow 共用行组件、证据展开、批量采纳（按域+全章）、已采纳删除、未提取/未归档横幅、双向指路
- [ ] 8.5 dossierApi.ts＋preview 累计预览（服务端聚合直读）
- [ ] 8.6 stale 呈现：树 tag-stale 角标（useWorkbench 字段）＋页签横幅重提动作
- [ ] 8.7 Rail.tsx 三入口收敛＋操作页签 lead 改向；ArchiveModal 覆盖警示；免费档配 key 引导（设定页入口可达）＋文案统一「生成是 PRO、整理全档」
- [ ] 8.8 vitest：useChapterData 受理态/事件、DossierPane 行为、软锁、进度恢复

## 9. e2e 与收尾

- [ ] 9.1 提取提速桩（env 缩短轮询/注入瞬时完成）进 e2e 基建
- [ ] 9.2 四条主链改写：reconcile.spec（两类+时序）、modals-pr5（两段式断言）、free-writing-flow（同步置位路径=无模型放行）、chapter-rewrite（级联角标）
- [ ] 9.3 新 e2e：章档页签全流程（归档→进度→软锁→采纳→下章消费来源行→重写级联→重归档覆盖警示）
- [ ] 9.4 全量门禁：pytest/vitest/e2e＋design:lint+design:check（原型先行已做）＋tsc
- [ ] 9.5 docker 镜像重建（前端 dist bake）＋产物特征串核对；隔离栈验证（独立 project 名/端口/数据目录）
- [ ] 9.6 真机验证：组装 token 复测（2943→预期 ≤4200）、提取成功率抽检、openapi 契约
