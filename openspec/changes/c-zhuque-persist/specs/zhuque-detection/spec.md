## REMOVED Requirements

### Requirement: 不落库与负载护栏

**移除原因**：落库拍板翻转（c-zhuque-persist，2026-10-01）——检测结论为作者资产，随章持久化并由备份完整迁移；「仅内存存续/备份不含检测数据」契约由「结果落库与负载护栏」替代（负载护栏条款原样并入）。

## ADDED Requirements

### Requirement: 结果落库与负载护栏

- 检测成功 SHALL 将结果落库：新表 `zhuque_results` 以 chapter_id 为主键（FK CASCADE，删章级联删），字段含 `prose_hash`（送检指纹）、`result`（完整响应 JSON）、`checked_at`（服务端落库时间）；同章重检 SHALL 覆盖旧档（upsert，不累积历史）。
- 端点 SHALL 提供按章读取存档：无存档返回「未存储」语义（200 `{stored: false}`），有存档返回 `{stored: true, prose_hash, result, checked_at}`；读取 SHALL NOT 触发任何检测或额度消耗。
- 检测执行护栏不变：单次送检正文字符上限（默认 30000）超限返回 422 与可读提示（SHALL NOT 静默截断）；同一作者同一章节在途请求拒绝（409）；前端切章/重复点击可取消。
- 备份与导入 SHALL 完整迁移检测数据：书级/整库备份按章写入检测结果（每章一文件，无存档不写）；导入按章 ref 重映射落库，坏 JSON SHALL 跳过并记 warning，SHALL NOT 因检测数据失败中断整包导入。

#### Scenario: 检测结果落库并可读回

- Given 作者对第 3 章检测成功
- When 读取该章存档
- Then 返回 stored=true、prose_hash 等于检测响应指纹、result 与响应一致、checked_at 非空

#### Scenario: 重检覆盖旧档

- Given 第 3 章已有存档
- When 作者修改正文后重检成功
- Then 存档被新结果与新旧指纹覆盖（仍一行，checked_at 更新）

#### Scenario: 重启后恢复展示

- Given 作者检测过第 3 章并重启应用
- When 重新打开第 3 章且正文指纹与存档一致
- Then 结果条与正文标注按存档恢复（含检测时间）；指纹不一致则整体置灰＋「重检」出口，不按旧指纹着色

#### Scenario: 删章级联清理

- Given 第 3 章已有存档
- When 该章被删除
- Then 存档行随之删除，无悬空引用

#### Scenario: 备份导出导入完整迁移

- Given 书内两章有存档、一章无存档
- When 导出书级备份再导入
- Then 两章存档按新章 id 完整恢复（含 checked_at），无存档章不受影响；损坏的存档文件跳过并记 warning，导入不中断

#### Scenario: 超长章明确拒绝

- Given 正文超过 30000 字
- When 发起检测
- Then 返回 422 与「正文超出单次检测上限」提示，未调用上游、未消耗额度

## MODIFIED Requirements

### Requirement: C端本地后端唯一执行端点（前端零直连）

- 朱雀检测 SHALL 只由 C端本地后端执行：`POST /api/novels/{project_id}/chapters/{chapter_ref}/zhuque-check`；前端 SHALL NOT 直连腾讯 EdgeOne 网关、SHALL NOT 持有 Key 明文。将来若迁移 S端统一代理，只替换该端点实现，前端契约不变。
- 落盘责任在**前端调用方**：前端 SHALL 在发起检测前触发并等待本章自动保存链 flush 完成（含防抖窗口内未落盘改动；沿用既有 flush 先例），落盘失败 SHALL 明确报错且不发起检测（SHALL NOT 按盘上旧文送检白耗额度）；后端端点只读落盘正文原样送检，SHALL NOT 触发任何章写入。
- 端点读取落盘正文后调用 EdgeOne 网关文本检测（`POST {base}/v1/providers/zhuque-text/classify`，Bearer Key），base_url 走环境变量可覆写（默认真实网关）供测试桩替换。请求体 `text` SHALL 为**规范化管道输出**（换行归一 → 非空段切分 → 各段 trim → `\n` join，含 NBSP 归一）；`prose_hash` SHALL 即对该文本的 sha256（哈希对象=请求体文本，可对请求体复算）；422 上限对同一文本计量。
- 响应 SHALL 为：`{ok, prose_hash, summary: {human_ratio, suspect_ratio, ai_ratio, softmax_confidence}, segments: [{paragraph_index, label, confidence}], usage_tokens, checked_at}`；`label` 取值 0=人工、1=AI、2=疑似；`paragraph_index` 为非空段序（见切分条款）；`checked_at` 为服务端落库时间（ISO 8601）。
- 端点对章数据 SHALL 只读（仅读正文，落库写 `zhuque_results` 旁表除外），SHALL NOT 调用任何章写接口；检测行为 SHALL NOT 触发章内容变更。

#### Scenario: 检测成功返回结构化结果

- Given 本章有 6 个非空段落、Key 有效、编辑器改动已 flush
- When 前端发起检测
- Then 返回 ok=true、prose_hash 等于请求体文本的 sha256、segments 含 6 条段落级 label+confidence、summary 三占比合计约 1（浮点容差断言）、checked_at 非空

#### Scenario: 空正文拒绝检测

- Given 本章正文为空或全部段落剔除后无有效内容（只有空行/空白行）
- When 发起检测
- Then 返回 400 与可读提示（先写正文），不调用上游网关
