## 1. 原型先行（设计门禁前置）

- [x] 1.1 按 drafts 设计稿 v12 改 `docs/design-c/prototypes/` model-config 屏：双页签行、朱雀页签两态、添加按钮随页签隐藏；ADJUSTMENTS.md 登记新词映射（.cfg-tabs/.zg-flow/.zq-toggle-row 等）与「添加按钮随页签」偏差
- [x] 1.2 工作台屏原型补：右栏检测行四态（锁定/引导/运行/就绪＋开关关不渲染）、e-head 右侧裸排结果条三态、正文段标注示意、stale 过期态示意（设计稿十态未含，按状态语言总表出）；ADJUSTMENTS.md 登记（标注挂 .editor 作用域、结果条让位规则、demo 类 zq-new/.pill-new→实装 zq-guide/zq-maxlk＋.pill-warn 映射、「去检查」→「去配置」文案偏差）
- [x] 1.3 跑 `npm run design:check` 确认原型基线更新后全绿（像素差 <0.2%）

## 2. 后端：隔离与配置端点

- [x] 2.1 P0 隔离：`ai_client.py` 通用选取（get_ai_client_for_user / get_ai_client）与 `ai_state.py` user_has_ai_key 加 `vendor != "zhuque"` 过滤（`require_ai_access` 的 Key 前置检查不过滤——朱雀-only MAX 须能到达检测端点）；`api_configs` 通用列表/批量状态查询（get_user_api_configs / get_batch_status）加同过滤（朱雀卡不进大模型页签）；绑定侧防注入（备份导入自动挂接跳过 zhuque、get_ai_client_for_novel 拒绝 zhuque）；pytest：仅配朱雀 Key 时生成动作按「未配置大模型」处理、列表无朱雀卡
- [x] 2.2 新建 `client/backend/zhuque/` 模块：`client.py`（httpx AsyncClient 直连 classify，ZHUQUE_API_BASE 可覆写，Timeout(connect=10, read=90, write=30)）、`router.py`（config GET/PUT/DELETE + test，test 响应沿用 connection 全部状态枚举（含 unknown）并持久化 last_test_status）、`segmentation.py`（换行归一＋非空段切分＋规范化 sha256 指纹）；密钥存 api_configs（vendor="zhuque"＋vendor_display_name、固定 name/base_url；upsert 查重键 (user_id,name)、IntegrityError 回退更新、空串 Key=未提供守卫复用既有口径、作者大模型配置撞固定名返回 409（active/deleted 一律 409，复活仅限 vendor=zhuque 行））
- [x] 2.3 `POST /api/novels/{pid}/chapters/{ref}/zhuque-check`：读落盘正文原样送检（落盘由前端 flush 保证，见 4.1）；调 classify 并按上游 order 对齐本地非空段（数量不符→502「检测结果与段落不一致」）；段落切分收口（paragraph_index+label+confidence）、prose_hash、错误映射（400 空正文或全空白/401 Key 无效/404/422 超 30000 字/429 限流或额度/502 上游 5xx 与错配/503 zhuque_not_configured/504 超时网络）；挂 get_current_user + require_ai_access；同章在途重复请求服务端拒绝（409 zhuque_check_in_progress，in-flight registry，结束/异常释放）；usage_tokens 记 token_log（operation="zhuque-check"、model="zhuque"，三个用量汇总查询排除该 operation）
- [x] 2.4 pytest：配置 upsert（软删复活 409 回归、并发双保存幂等、撞名 409、空串保 Key）；切分/指纹 golden（连续空行、全空白行、首尾空白段、单段、6 段标准样本，前后端同环）；端点错误映射表（含 503 需先播种任一写作 Key、上游分段错配 502、同章并发拒绝 409、软删大模型行撞名 409）、三占比合计容差断言；先播种 User 行再断言 token_log（FK 约束）；monkeypatch classify 桩；全量 pytest 绿

## 3. 前端：配置页双页签与开关

- [x] 3.1 `lib/prefs.ts` 扩展 `zhuqueShow`（默认 true）；`lib/features.ts` 登记 `"ai-detect": { memberOnly: true }`（注释：MAX 专属、试用不含，快照单源，快照缺失一律未授权）
- [x] 3.2 `ApiKeyConfigPage.tsx` 双页签改造：`?tab=zhuque` 深链（`?add` 组合强制大模型页签）、添加按钮随页签隐藏；朱雀面板独立组件（不串 useApiConfigs）：介绍条、Key 配置卡（保存并测试/掩码/更换/删除/开关）、横向三步卡、隐私警示条；CSS 词入 model-config.css（.cfg-tabs/.zg-flow/.zq-toggle-row，开关用现役 .switch-btn）；前端回归大模型页签列表无朱雀卡（配合 2.1 后端过滤）
- [x] 3.3 vitest：页签切换与添加按钮显隐、add 组合优先级、开关写 prefs、保存并测试的成功/401 两态、429 中性文案、非会员保存配置不被拦；`npm run design:lint` 绿

## 4. 前端：检测编排 hook

- [ ] 4.1 `useZhuqueCheck(projectId, chapterRef)`：**挂路由边界之上（App 级 context 或模块级单例，跨 /config 路由存活）**；status/result/proseHash/stale；AbortController 挂切章与重复点击；(chapterRef, proseHash) 内存缓存；发起检测前 await 本章 store.flush()（chapter-rewrite 先例，flush 失败报错不送检）；重启不恢复（不进 localStorage/DB）
- [ ] 4.2 vitest：在途取消、缓存命中不重发、指纹不符转 stale

## 5. 前端：右栏检测行

- [ ] 5.1 `AiWriterAssistant.tsx` 扩展：AiCapabilityRow 支持 guide 变体（虚线）、maxlk 锁定变体（保持可点走升级出口，不用 disabled）＋行内徽章插槽（MAX 专属 .pill-warn）、runningHint 自定义文案；`AiAssistPanel.tsx` prose 页签末行按四态分发（useFeature("ai-detect") 锁定＋MAX 专属章→统一升级出口；未配 Key→navigate /config?tab=zhuque（就绪/引导分流读 GET /api/v1/zhuque/config 的 configured）；运行中（running 态并入 runningKey 使整卡其余行禁用）；就绪；开关关=不渲染＋副行「朱雀检测已关闭」；entitlementDegraded 降级文案变体「权益状态确认中」）；免费档整卡锁定调和（行级变体仅卡 ready 时生效）；检测运行期整卡其余行禁用为既有行为
- [ ] 5.2 vitest＋e2e：四态渲染与点击路由（锁定不给请求、引导跳页签、快照降级一律锁定）；共享组件回归 ai-assist 相关既有用例全绿

## 6. 前端：标题区结果条

- [ ] 6.1 `ChapterWorkspace.tsx` e-head 挂结果条（裸排 .zq-hd：占比条＋三数字＋概率参考小字＋清除标注/重检；检测中转圈；失败红字＋按错误族出口（去配置/重试/关闭））；与既有控件冲突时结果条优先、其余换行；窄屏堆叠
- [ ] 6.2 vitest：三态渲染、清除标注=结果与标注一并退场、stale 灰化＋「正文已修改，结果可能过期」＋重检可点、开关关隐藏/拨回开恢复（会话内缓存）、空正文「先写正文」不可用引导、已归档章保持可发起

## 7. 前端：正文标注 Decorations

- [ ] 7.1 TipTap 扩展 `zhuque-marks`：node decoration（zq-warn/zq-err 段底色）＋widget decoration（行尾 .zq-mark 置信度章，contenteditable=false）；paragraph_index→PM 节点映射（doc.content.forEach 同口径）
- [ ] 7.2 失效链：tr.docChanged→重算指纹≠proseHash→装饰转置灰＋结果条 stale；重检后恢复；标注不进撤销历史/自动保存文本
- [ ] 7.3 vitest＋e2e：标注着色与章渲染、编辑后变灰、下载/预览导出与未检测逐字节一致

## 8. 收尾门禁与换包

- [ ] 8.1 e2e 锚点清单落位（data-testid）：检测行 rail-zhuque-check、结果条 zhuque-head-strip、清除标注 zq-clear、重检 zq-rerun、配置页签 cfg-tab-llm/cfg-tab-zhuque、Key 输入/保存 zhuque-key-input/zhuque-key-save、显示开关 zhuque-show-toggle、stale 提示 zhuque-stale
- [ ] 8.2 全门禁：双端 tsc/vue-tsc、vitest、pytest、e2e（新增 config-page 用例：页签/添加按钮显隐/深链；workbench 用例：行四态/结果条/标注/stale）、design:lint + design:check + design-cross
- [ ] 8.3 演示栈重建换包（独立 compose 项目），真机走通 10 态设计稿口径；抓 bundle 特征串自证为本构建
