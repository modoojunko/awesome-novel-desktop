## ADDED Requirements

### Requirement: 配置域不分套餐权益（门禁落使用口）

- 朱雀配置域端点（`GET/PUT/DELETE /api/v1/zhuque/config`、`POST /api/v1/zhuque/test`）SHALL 只要求登录：**SHALL NOT 挂套餐权益门**——档位门与「已配写作大模型 Key」判据都不得挂（2026-10-08 拍板：配置不分套餐权益，权益门禁落使用口）。
- 朱雀的 `ai-detect` 权益门禁 SHALL 落在使用口：工作台检测行（前端 `useFeature("ai-detect")` 快照锁定，见 zhuque-workbench）与检测端点（后端会员＋档位真门，见 zhuque-detection）。
- 判据分流 SHALL 由门控层单源承载（`auth_local/deps.py`：`require_ai_access`＝会员＋档位＋写作模型 Key；`require_tier_access`＝会员＋档位，键自持端点用）；业务层 SHALL NOT 内联会员/档位/Key 判断。
- 端点 key 标注守卫 SHALL 认可两种门（挂 key 而未挂任一门的端点仍判死标注）。

#### Scenario: 任意档位都能配置（含免费）

- **GIVEN** 免费或标准档作者（快照无 `ai-detect`）进入模型配置页朱雀页签
- **WHEN** 作者粘贴 Key 并保存（或点「测试连接」、或删除 Key）
- **THEN** 配置动作成功完成，SHALL NOT 返回 403/503；同一作者的工作台检测行仍呈档位锁定态（权益门禁在使用口，不在配置）

#### Scenario: 只配朱雀、未配写作大模型

- **GIVEN** PRO（或试用）作者从未配置任何写作大模型 Key（无 `api_configs` 行、无旧字段、无 config.json 兜底 Key）
- **WHEN** 作者在朱雀页签点「保存并测试」
- **THEN** 保存与连接测试照常完成（响应含掩码 Key 与本次测试结果），SHALL NOT 返回 503「AI 服务未配置 — 请先在设置中填写 API Key」
