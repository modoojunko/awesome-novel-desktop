# tier-access 增量

## MODIFIED Requirements

### Requirement: Archive is free

- 归档动作本身 SHALL NOT 挂会员门：`POST` 归档受理、`GET /archives`、`GET /archives/{filename}` 对免费档可用。
- 本书未配置模型时归档 SHALL 即刻生效（archived、无章档），摘要降级语义不变（正文前 200 字），SHALL NOT 500。
- 本书已配置模型时，归档 SHALL 以四域提取成功为生效前置（受理→后台提取→成功收口，见 chapter-dossier）；该提取调用 SHALL NOT 挂会员门（免费档配置模型即可用），失败按章档能力的重试/逃生阀语义处理。
- The archive gate SHALL check `.md` archive files (fixes B4), degrading to a file scan without 500 when the DB is unavailable.

#### Scenario: Free archive without API key

- Given a free-tier user with no API Key and a chapter with ≥100 chars prose
- When the chapter is archived
- Then the request accepts and archives immediately (no dossier rows), the summary is the first 200 chars, and no 500 is raised

#### Scenario: Free archive with configured model

- Given a free-tier user who has configured a model
- When the chapter is archived and extraction succeeds
- Then the chapter is archived and dossier rows are produced, without any membership gate

#### Scenario: Archive list readable for free

- Given a free-tier user
- When GET /archives and GET /archives/{filename} are called
- Then both return 200
