# Design: s-device-registry-dedupe

## 决策点

### D1 为什么是「撞约束回落更新」而不是 PostgREST `resolution=merge-duplicates` 原子 upsert

merge-duplicates 编译为 `INSERT … ON CONFLICT (user_id, fingerprint) DO UPDATE`，**硬依赖**生产库真有该唯一约束——而生产表是带外手工维护（无迁移链），约束存在性当时未留证。若缺失，merge-duplicates 会让每次注册插入直接报错，登录全炸。回落方案（普通插入＋捕获 23505→update）在约束缺失时退化为旧行为，两种世界都不比现状差。合入后探针实测约束存在，回落即成为该约束下的正确语义（原先竞态输家 500）。

### D2 SQL 仓冲突路径的 rollback 副作用

SQLite 侧撞 `uq_user_fingerprint` 后 `rollback()` 会连带丢弃同请求先前的未提交变更——authorize 流程里只有惰性密码升级（可重试优化，下次登录重做），无数据损失，注释已声明。不引入 SAVEPOINT（本仓实测先例：ai-client 记账判定不可行）。

### D3 容器身份为什么选「挂载宿主身份」而不是「config.json 落盘缓存」

#430 曾有意「身份不落盘」（防磁盘镜像克隆带出源机旧身份）。挂载宿主 `/etc/machine-id` 垫片让容器继承宿主硬件身份，与该决策同向而非相悖；数据目录持久化身份（容器重建存续）会重新引入克隆风险。垫片文件缺失时 Docker 造出同名目录，`_identity_linux` 的 `read_text` 抛 `IsADirectoryError`（OSError 子类）被既有 catch 静默降级——无需改 C端 代码。

### D4 幻影行清理为什么走网关 REST 而非控制台 SQL

行级 DELETE/POST 网关（PostgREST）完全覆盖；只有 DDL（补约束）和杀连接必须控制台 SQL——本次探针证实约束已在，两项都免了。清理口径「每用户保留最新一行」：真机行的 `last_active_at` 随每次登录刷新恒为最新，幻影行在 #430 后不可能再被更新；副作用（30 天未登录的真机行被删）自愈于下次浏览器重新授权，ops 文档已注明。

## 降级矩阵

| 场景 | 行为 |
|---|---|
| 约束存在＋无竞态 | 查到→更新 / 查不到→插入（与旧一致） |
| 约束存在＋竞态输家 | 23505→回落更新（旧：500） |
| 约束缺失＋竞态 | 插入成功→重复行（旧：相同，不更差） |
| 非约束 DB 错误 | 上抛（旧：相同） |
| 垫片文件缺失 | 目录挂载→OSError→回落 hostname（旧：相同） |
