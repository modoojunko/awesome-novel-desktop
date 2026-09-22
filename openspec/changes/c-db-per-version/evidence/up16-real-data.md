# UP-16 真数据演练证据（c-db-per-version）

命令：`python scripts/up16_real_data_drill.py --work /private/tmp/up16 --version 0.25`

## 运行输出

```
拷入：/Users/modoojunko/Desktop/coding/ai-novel/.docker-data/client/novel-v1.db → /private/tmp/up16/data/novel-v1.db（34906112 bytes）
拷入：/Users/modoojunko/Desktop/coding/ai-novel/client/backend/data/novel.db → /private/tmp/up16/data/novel.db（544768 bytes）
首启：novel-v0.25.db 建库，novels=0（空库）
候选：[{"filename": "novel-v1.db", "kind": "legacy", "version": null, "legacy_generation": 1, "book_count": 1213, "recommended": true, "unreadable": false}]
带回 novel-v1.db：source=1213 migrated=1213 tables=38 skipped=[] fk=0
未列入候选的拷贝 novel.db：precheck → ok=False reason=pre_rename_generation
目标库最终计数：{"novels": 1213, "volumes": 498, "chapters": 518, "characters": 61, "novel_hooks": 118, "app_meta": 2}
搬后 roundtrip：导出 爱小说-备份-2026-09-22.zip 1063380 bytes（免登整库口径）；包内作品段 128 == 活书数 128（库内总行 1213，含 e2e 软删残书）；属主分布 top3=[('modoojunko', 50), ('e2e_rc_1789993331448_027af055', 2), ('e2e_ai_1789921162610_2be55dc3', 1)]
源不变 novel-v1.db：True
源不变 novel.db：True
```

## 源三件套 sha256/mtime_ns/size（运行后逐项复测相等）

| 源 | 文件 | sha256(前16) | mtime_ns | size |
| --- | --- | --- | --- | --- |
| /Users/modoojunko/Desktop/coding/ai-novel/.docker-data/client/novel-v1.db | novel-v1.db | 15dd757581509a91 | 1789995214350045000 | 34906112 |
| /Users/modoojunko/Desktop/coding/ai-novel/.docker-data/client/novel-v1.db | novel-v1.db-wal | 1b0d9ce0847fab33 | 1790036117994265021 | 4181832 |
| /Users/modoojunko/Desktop/coding/ai-novel/.docker-data/client/novel-v1.db | novel-v1.db-shm | ecd07f85fd19a67a | 1790037538301375943 | 32768 |
| /Users/modoojunko/Desktop/coding/ai-novel/client/backend/data/novel.db | novel.db | e6d22641ecc18911 | 1789734521742033876 | 544768 |
| /Users/modoojunko/Desktop/coding/ai-novel/client/backend/data/novel.db | novel.db-wal | e3b0c44298fc1c14 | 1789914822991683486 | 0 |
| /Users/modoojunko/Desktop/coding/ai-novel/client/backend/data/novel.db | novel.db-shm | fd4c9fda9cd3f9ae | 1790037543323005936 | 32768 |
