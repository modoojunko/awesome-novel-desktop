# c-legacy-drill-gate — 迁移兼容演练门禁：历史世代样本重放＋值映射约定

## Why

「迁移部分成功」（status=ok 但有缺口）的真实事故有两单：total_archives 整表静默丢失
（NOT NULL 无默认列，OR IGNORE 吞行）与值域升级拒收旧值的形态（CHECK 拒收判例）。
两类都属「schema 演进打破遗留库可迁性」——**事故发生在用户现场，而根因在开发期就
已引入**。现有 UP-01~UP-16 验收测试各自造库、各管一个场景，没有一个「全部历史形态
都要能迁」的总门；值域约束若拒收旧值，目前没有任何机制在合入前暴露。

治本＝把这类事故从用户现场挪到开发期：维护一份**历史世代样本登记表**（每个曾发布
形态一份可审阅的合成样本），任何 schema 变更后 CI 自动全量重放，撞到跳表/行损失/
完整判否即红。配套「值域降级映射」约定：谁加值域约束，谁在同一笔 PR 声明遗留值怎么
降（映射表＋保守默认），引擎运行期零临场决策；未声明映射的拒收不得静默降级。

## What Changes

- **样本登记表**（`tests/legacy_samples.py`）：登记每个曾发布的历史世代库形态
  （合成构造，可审阅、可执行），样本带 key/文件名/出处（哪次事故或哪个世代）。
  登记表**只增不减**——删样本即红（测试执法）；迁移事故判例 MUST 入册新样本。
- **重放门禁**（`tests/test_legacy_replay_gate.py`）：CI 每次全量重放登记表——
  逐样本 `run_migration` 进当前 schema 新库，断言完整达成（零整表跳过、逐表
  rows_missing=0、源书全在场）且源三件套零接触。任何 schema 变更打破遗留可迁性
  → CI 红，把「部分成功」拦在合入前。
- **值域降级映射约定**（`migration/value_mappings.py`）：登记表
  `{(表, 列): {精确映射, 保守默认}}` 单源；引擎（本 change 只立约定与查询 API，
  降级回迁执行在 c-carry-degrade-remigrate）按表执行，**未声明的拒收 MUST NOT
  降级**（宁报缺口）。贡献规范写死在模块 docstring：加值域约束的 PR MUST 同笔
  声明映射＋保守默认，方向宁低勿高（`writing→draft` 而非 `done`）；无映射不落笔。
- 初始映射登记表为空是诚实的：当前用户表尚无值域约束；门禁与约定先于下一笔
  约束变更就位。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `db-generation`：「升级演练升格（version-chain）」——演练 SHALL 维护历史世代
  样本登记表并全量重放（任一跳表/行损失/完整判否即红），登记表只增不减；值域
  约束的引入 SHALL 同笔声明值域降级映射与保守默认，未声明映射的拒收 MUST NOT
  静默降级。

## Impact

- 新增 `client/backend/migration/value_mappings.py`、
  `client/backend/tests/legacy_samples.py`、
  `client/backend/tests/test_legacy_replay_gate.py`；不改任何运行时行为
  （门禁纯 dev/CI 侧，映射查询 API 尚无运行时消费方）。
- 后端 CI（pytest）自动承载门禁，无新增 workflow。
- 后续：`c-carry-degrade-remigrate` 消费映射表落降级回迁＋内容级差异清单。
