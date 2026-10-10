# c-legacy-drill-gate — tasks

## 1. 样本登记表（tests/legacy_samples.py）

- [x] 1.1 登记表结构与样本协议：key（只增不减的身份键）／filename／origin（世代或事故判例出处）／build（合成构造，可含边车）
- [x] 1.2 首批样本四份：gen0（novel.db 第 0 代）／遗留代数名（novel-v3.db）／带 -wal/-shm 边车的 semver 库（novel-v0.24.db，强杀形态）／缺列形态（源库落后于当前 schema 的列交集面）

## 2. 重放门禁（tests/test_legacy_replay_gate.py）

- [x] 2.1 逐样本 run_migration 进当前 schema 新库：断言完整达成（零整表跳过、逐表 rows_missing=0、book_count_present==source）
- [x] 2.2 源三件套零接触断言（重放本身不得污染样本）
- [x] 2.3 登记表只增不减断言（冻结基线键集；删样本即红）

## 3. 值域降级映射约定（migration/value_mappings.py）

- [x] 3.1 登记表单源 `{(表,列): {map, default}}`＋查询 API（精确命中→映射值；未命中→保守默认；无条目→None＝禁降级）
- [x] 3.2 贡献规范写死模块 docstring（同笔声明／宁低勿高／无映射不落笔／事故判例入册样本表）
- [x] 3.3 查询 API 单测（初始空表语义：一切未声明＝禁降级，门禁现行口径不被预写映射放宽）

## 4. 门禁执法验证

- [x] 4.1 牙齿自证：临时给目标 schema 加值域约束拒收样本历史值 → 门禁必红（回退后复绿，证据记录在 PR）
- [ ] 4.2 CI 绿（push 后看 run）

## 5. 收尾

- [x] 5.1 openspec validate 通过
- [ ] 5.2 真机无感（纯 dev/CI 侧，无运行时行为变化）
