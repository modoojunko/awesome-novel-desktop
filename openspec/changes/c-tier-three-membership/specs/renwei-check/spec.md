## REMOVED Requirements

### Requirement: 本地人味检测引擎与端点

**Reason**: 2026-11-25 拍板人味检测与逐行修改指引归 MAX；原条款要求端点“只挂登录、SHALL NOT 挂档位门、无任何 Key 与档位前置”，与 MAX 专属冲突。

**Migration**: 由 ADDED「人味检测与逐行修改指引（MAX）」承接：检测引擎不变，端点/工具挂 `human-taste`（MAX），标准/PRO 显示锁定与升级出口。

### Requirement: 右栏检测区入口行

**Reason**: 原条款要求人味检测行标注「本地 · 免费」且无档位门；新会员模型为 MAX 专属。

**Migration**: 由 ADDED「右栏检测区入口行（MAX）」承接：入口仍可见，标注改为「MAX 专属」，标准/PRO 点击走 MAX 升级出口。

## ADDED Requirements

### Requirement: 人味检测与逐行修改指引（MAX）

- 人味检测引擎与端点 `POST /api/novels/{project_id}/chapters/{chapter_ref}/renwei-check` SHALL 保留本地确定性检测（19 项指标、人味率、findings、标到行与改法）；SHALL NOT 上传正文、SHALL NOT 调用模型、SHALL NOT 记入模型账。
- 端点 SHALL 挂 `human-taste`（MAX 起）；标准（免费）/PRO 调用 SHALL 返回 `feature_required` 与 `tier_required=max`，不返回检测结果。
- 助理 `read_prose_checks` SHALL 挂 `human-taste`（MAX）：MAX 用户可让助手现算人味并读取逐行改法；PRO 用户同一请求走 MAX 升级出口。
- 旧权益快照不含 `human-taste` 时，未过期 MAX SHALL 隐式放行；PRO/标准（免费）/过期 SHALL 锁定。
- 短章不足 1,500 字 SHALL 继续出「打不了分」语义（仅可定位 findings 与不计分项），SHALL NOT 给出可信度不足的分数。

#### Scenario: 标准（免费）/PRO 调用被拒

- **WHEN** 标准（免费）或 PRO 用户点「人味检测」/让助手读检测
- **THEN** 返回 `feature_required`/`tier_required=max`，显示 MAX 升级出口，不执行检测

#### Scenario: MAX 正常检测

- **WHEN** MAX 用户点「人味检测」
- **THEN** 返回人味率、逐行 findings 与改法；不调用模型、不上传正文、不记账

#### Scenario: 旧快照隐式放行

- **WHEN** 未过期 MAX 用户的完整旧快照缺少 `human-taste`
- **THEN** 检测端点与 `read_prose_checks` 按 MAX 隐式放行；PRO/标准（免费）/过期仍锁定

### Requirement: 右栏检测区入口行（MAX）

- 正文页签右栏检测区 SHALL 在「朱雀 AI 检测」行之下提供「人味检测」行：标注「MAX 专属」（不再写「本地 · 免费」），无配置态、无 Key 前置。
- 入口行 SHALL 对标准（免费）/PRO 可见但锁定：点击走 MAX 升级出口（说明开通后能做什么），SHALL NOT 以报错打断。
- 入口行与朱雀行 SHALL 相互独立：人味检测不读写朱雀存档与额度，朱雀状态（含检测中/过期）SHALL NOT 阻塞人味检测。
- 标准（免费）/PRO 的锁定态 SHALL NOT 阻断正文编辑、版本、归档等其他功能。

#### Scenario: PRO 看到锁定行

- **WHEN** PRO 用户打开正文页签右栏检测区
- **THEN** 人味检测行显示「MAX 专属」锁定态，点击走 MAX 升级出口；朱雀行按 PRO 正常可用

#### Scenario: MAX 可使用

- **WHEN** MAX 用户点人味检测行
- **THEN** 进入检测流程并返回逐行改法；与朱雀状态互不影响
