## 1. 双端影响判定（原型先行豁免依据）

- [x] 1.1 判定：C端 触用户可见界面，原型已完成并归位 docs/design-c/prototypes/backup-restore.html（v6/v7）+ spec + ADJUSTMENTS——UI 实现以原型为基线、偏差按登记簿执行；S端 零涉及；共享段不触碰。验证=本条勾选

## 2. PR0 旧库留档机制（无 UI 依赖，先行）

- [x] 2.1 `app_meta` 表（key/value）+ `models/__init__` 注册 + 启动期 schema 自动指纹（sha256 全表列签名排序 [:16]）写入 app_meta；验证=新旧库双 fixture 单测（指纹匹配零动作/不匹配触发留档）
- [x] 2.2 lifespan 最前插入留档逻辑：指纹不匹配 → `novel.db` 三件套改名 `novel.legacy-{时间戳}.db(/-wal/-shm)` → create_all 全新库；留档只增不删；验证=旧库 fixture 启动后断言留档三件套存在+新库空且结构正确
- [x] 2.3 `GET /api/backup/legacy-db/status`（裸 sqlite3 只读 URI 查 book_count，异常→null 不 500）；验证=pytest 断言响应形状
- [x] 2.4 容器内全量 pytest；验证=绿

## 3. PR1 导出端 + 壳层桥

- [x] 3.1 资产包格式 v1 导出重构：`_dump_book_into(zf, prefix, project)`（单书/批量共用）；project.yaml（format_version=1 契约头）取代 project.json；archives/manifest.yaml（title/summary/archived_at）；产物中文命名（爱小说-备份-日期.zip / 爱小说-备份-配置-日期.zip / 《书名》-作品包-日期.zip，RFC 5987 + 书名清洗）；验证=pytest 导出结构断言（布局/键集合/中文名）
- [x] 3.2 配置包导出：config.yaml（user 子集+api_configs，`decrypt_api_key` 明文）+ `GET /export/config/preview` 掩码端点；验证=pytest 掩码与内容断言
- [x] 3.3 壳层桥：`pywebview_app.py` 加 NativeBridge（pick_folder/pick_save_file/pick_open_file 三方法白名单，5.x/6.x 返回归一 str|None）；验证=dev 模式冒烟 + 打包冒烟
- [x] 3.4 导出任务化：`POST /backup/export/start {target_dir, include_config, kind}` + `GET /backup/export/status`（阶段 probe→assets→config→finalize，写盘字节真进度，`.zip.part`+os.replace 原子替换，单飞 409，磁盘错误分码 fail-fast）；GET 下载端点保留为无壳回退；验证=pytest start/status 状态机断言
- [x] 3.5 前端备份弹窗接线：设置「备份与恢复」行 + BackupModal 四步（选位置=调桥/确认勾选/进度轮询/完成回显+警示文案）；UpdateNotice「先备份」跳设置；验证=vue-tsc + 本地 vitest + playwright 相关 spec

## 4. PR2 导入端 + roundtrip（**当前待做**——PR0/PR1 已合入 main #305/#307）

- [ ] 4.1 `chapters/store.py` 抽 `apply_chapter_data(row, data)`（save_chapter 429-446 行纯函数化，行为零变化，独立 commit 先验）；验证=全量 pytest 绿（重构 commit）
- [ ] 4.2 `backup/` 导入模块：parse（收路径，壳层桥传递；形态探测 backup.yaml/单书 v1/v0 双读；zip slip 白名单；分块预览）；persist（token staging manifest 幂等重入；逐书单事务：settings 直写 ProjectSetting/volumes 四子表/chapters 走 apply_chapter_data/versions 原文/prompts/archives；同名书《（备份）》递增；同名配置跳过；智能挂回双向幂等；恢复限额豁免依赖）；config/parse+persist（掩码预览+重加密落库）；验证=pytest
- [ ] 4.3 roundtrip 测试底座：造富项目（HTTP 正规链路 8 资产全字段+特殊字符正文）→导出→导入→八层断言（元数据白名单逐字段/设定深比/卷纲剥 chapters/章全字段/快照字节级/提示词/归档 manifest/幂等再导出）；坏包矩阵（截断/zip slip/v99/双缺元数据/单章损坏跳过/空包）；v0 fixture 降级断言；验证=全绿
- [ ] 4.4 无壳回退：multipart 收路径外文件的回退分支（dev 浏览器模式）；验证=pytest 覆盖

## 5. PR3 前端恢复 + e2e（依赖 PR2）

- [ ] 5.1 恢复弹窗双槽位（pick_open_file 桥选文件/无壳 input 回退）+ 预览分块（作品块书清单+配置块掩码+块级勾选+同名 warn）+ 分段进度 + 完成摘要（成功主叙事/挂回 pill/部分成功混合态）；书架「导入」对 .zip 误投的结构化拒收文案（backup_package 422 出口）；验证=本地 vitest+tsc
- [ ] 5.2 e2e：导出双包 happy path/双槽位恢复/部分成功/包过新 422/书卡单书导出；验证=playwright 绿
- [ ] 5.3 docker compose build 重建本地容器给用户验看（截图对照原型 v6）；验证=用户确认

## 6. 回归与发布（依赖 PR2/PR3）

- [ ] 6.1 全量门禁结论记录：容器内 pytest / vitest+tsc / playwright / design:lint（存量口径）；验证=写入本条
- [ ] 6.2 残余 grep 验收：新增代码无内部术语上屏、无 slug 上屏、无 token_log/model-history 随包代码路径；验证=清单
- [ ] 6.3 全链演练（发版验收门禁）：旧版造富库→导双包另存→覆盖装新版（留档断言）→设置导入→八层 roundtrip 全绿→token_log 零新增；验证=演练记录附 PR
- [ ] 6.4 归档走 PR（--admin 纯文档）；验证=specs 含 backup-restore capability
