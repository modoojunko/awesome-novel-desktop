## MODIFIED Requirements

### Requirement: 结果落库与负载护栏

- 检测成功 SHALL 将结果落库：新表 `zhuque_results` 以 chapter_id 为主键（FK CASCADE，删章级联删），字段含 `prose_hash`（送检指纹）、`result`（完整响应 JSON）、`checked_at`（服务端落库时间）；同章重检 SHALL 覆盖旧档（upsert，不累积历史）。
- 端点 SHALL 提供按章读取存档：无存档返回「未存储」语义（200 `{stored: false}`），有存档返回 `{stored: true, prose_hash, result, checked_at}`；读取 SHALL NOT 触发任何检测或额度消耗。
- 端点 SHALL 提供按章删除存档：`DELETE .../zhuque-result` 经章属主校验后删除该章存档行，幂等（无存档同样返回成功）；删除 SHALL NOT 触发任何检测或额度消耗。
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

#### Scenario: 清除标注连存档删除

- Given 第 3 章已有存档
- When 前端「清除标注」触发 DELETE 存档
- Then 存档行被删除，重启应用后该章不再恢复任何标注或结果条；对无存档章重复 DELETE 仍成功（幂等）

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
