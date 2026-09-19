## 0. 原型先行

- [ ] 0.1 `backup-restore.html` 增屏 8「找回向导」五步+清理 ConfirmGuard（复用 .bk-*/.pct/.pill 全家族零新档位；多代选择/幂等标记/部分成功/全部失败全场景）；`list.html` 空态注脚「这台电脑上有旧版作品 · 找回我的书」。验证：浏览器过全场景＋ADJUSTMENTS 登记三条（含 v3 首启静默口径推翻）

## 1. PR0：代数基础与状态机

- [ ] 1.1 `schema_version.py`（SCHEMA_VERSION=1/DB_FILENAME 单源）＋`config.py` DATABASE_URL 版本化。验证：import 冒烟＋现有库（novel.db）被识别为第 0 代候选
- [ ] 1.2 `db_lifecycle.py`：首启状态机四态（current/additive/tolerant+审计键/breaking 隔离 .corrupt）＋校验升级梯（ro 失败→副本 checkpoint 再验）；`classify_drift` 扩 tolerant；`legacy_archive.py` 函数迁入后删除。验证：pytest 四态+tolerant 新分支+「同代 additive 后退旧 build 不再清库」回归用例
- [ ] 1.3 `main.py` lifespan 头段接 db_lifecycle；110-399 历史 ALTER/UPDATE 段删除收编 ADDITIVE_COLUMNS；`config.json→User` 段保留。验证：全量 pytest 绿（ALTER 段删除后存量库路径全兼容）
- [ ] 1.4 `tests/conftest.py` 测试库版本化＋指纹戳配方改造。验证：全量 pytest 绿
- [ ] 1.5 **现状无缝验证**：本机 novel.db（第 0 代）+新代码首启→书架不空、候选检出、无自动改名。验证：隔离栈实测+留档

## 2. PR1：迁入引擎

- [ ] 2.1 候选扫描（novel-v{k}/novel.db/.legacy-*；**排除 -wal/-shm/.bak**；book_count>0；只读体检+世代探测）。验证：pytest——-wal 不进候选（现行 bug 回归钉死）；空库剔除
- [ ] 2.2 引擎六步+第 0 步预检（暂存副本/源零接触含不做 checkpoint/FK OFF/列交集+整表跳过预告/app_meta 不搬/计数对拍/报告 v:1 preview-result 同构）。验证：pytest——幂等重跑零重复行；中断恢复；源文件字节+mtime 不变；FK 违规行报告不静默吞
- [ ] 2.3 世代门禁：前 ADR 世代候选不进行迁，引导资产包通道。验证：pytest——yaml 世代特征库被门禁拦截并返回引导
- [ ] 2.4 免登端点（candidates/preview/start/status/dismiss）+job_runner 加 migration 单飞；dismiss/完成键绑候选身份指纹（path+mtime+size）。验证：pytest——免登矩阵+「回滚编辑后再升级提示重开」用例
- [ ] 2.5 `migration/converters/` 逐代文件+registry+CI 连续性断言（首个跳：第 0 代→v1）。验证：CI 断言跑通；缺跳注入测试红

## 3. PR2：向导与演练

- [ ] 3.1 `useLegacyDb`+`LegacyMigrateBar`（「保留旧文件，不再提醒」+设置行双徽标态）+`LegacyMigrateModal` 五步（发现/多代选择/预览《（旧版）》后缀+缺列预告+幂等标记默认不勾/locked 进度/结果 hero+部分成功+全部失败回滚声明）。验证：vitest 全流+各分支
- [ ] 3.2 书架空态开口行+唯一自动弹条件（空&&候选&&未 dismiss&&本会话未弹）；设置「找回」入口。验证：vitest+e2e
- [ ] 3.3 清理 ConfirmGuard（L2 盘点+不可逆声明+「先备份一份」出口；部分失败不出入口；不输文件名）。验证：vitest 三态
- [ ] 3.4 upgrade_drill 增 gen-bump（源逐字节不变/空库/候选/迁入对拍/迁后 roundtrip）+loginless-export 阶段。验证：drill 全绿留输出
- [ ] 3.5 全量门禁：pytest/vitest/tsc/design:lint/check/全量 e2e（隔离栈）。验证：全绿留输出
