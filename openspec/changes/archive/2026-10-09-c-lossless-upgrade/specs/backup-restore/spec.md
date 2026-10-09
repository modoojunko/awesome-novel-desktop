# backup-restore（delta）

## MODIFIED Requirements

### Requirement: 旧库留档与升级演练

新版本启动 SHALL 按库文件版本治理处理存量数据（**语义单源在 db-generation 能力**，本条只引用不另立口径）：本版库不存在则空库启动并将旧版本库、旧命名库（`novel.db`）与历史 `.legacy-*` 文件列为迁入候选（源文件只读，永不自动改名或删除）；「升级即整库留档重置」与「代内补列」旧机制均已退役。任何 schema 破坏性版本的发布验收 MUST 包含 version-chain 全链演练（db-generation 口径）：seed 旧版本库→装新版（源文件逐字节不变＋空库＋候选检出断言）→**带回**（含密钥转接与预置题材源行胜出，计数与等价对拍）→迁后新格式导出→导入 roundtrip 全绿；loginless-export 阶段（免登导出→包内无配置块）同门执行。带回的用户入口与呈现（告知卡四步、稍后带、不完整提醒）以 db-generation 的「带回告知卡」requirement 为准。

#### Scenario: 升级后旧数据可救

- **WHEN** 用户升级后删除新库（极端救援）
- **THEN** 旧版本库文件原样保留，重新启动可再走带回找回；或以旧库机器上的免登导出包在新库导入 roundtrip 全绿
- **AND** 任何历史文件全程未被新版本触碰

#### Scenario: 演练留档断言

- **WHEN** 旧形态库（含旧卷纲字段）装入本版启动
- **THEN** 空库以新 schema 启动且旧文件字节不变，候选端点检出该文件（不再产生自动改名留档）

#### Scenario: 已声明退役差异不留档

- **WHEN** 历史留档机制（archive_if_legacy 三件套改名）被移除
- **THEN** 同版本损坏库以 `.corrupt-<stamp>` 隔离件形式保留并只读可见（隔离件不进迁入候选，成因不明需人工判定）；历史上已存在的 `.legacy-*` 文件全部纳入迁入候选枚举
