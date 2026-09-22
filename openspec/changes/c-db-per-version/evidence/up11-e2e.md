# UP-11 版本升级 e2e 证据（c-db-per-version）

命令（会话私有栈，project=dbver，端口 18100/18101，数据目录＝worktree 的 `.docker-data/client`）：

```bash
CLIENT_DATA_DIR=$PWD/.docker-data/client CLIENT_HOST_PORT=18100 CLIENT_WEB_HOST_PORT=18101 \
  docker compose -p dbver -f docker-compose.yml -f /tmp/up11-compose.override.yml \
  up -d --build client-backend client-frontend
E2E_BASE_URL=http://localhost:18101 UP11_DATA_DIR=$PWD/.docker-data/client \
  npx playwright test e2e/db-version-upgrade.spec.ts
```

镜像自证（容器里跑的是本分支代码）：`docker exec dbver-client-backend grep -c pre_rename_generation migration/engine.py` → 1；
`grep -c book_count_target_after migration/engine.py` → 2；`CLIENT_VERSION=0.25`。

## 结果：2 passed

```
✓ 换安装目录：无候选时「从备份包恢复」恒在且可达 (0.6s)
✓ 同机升级：遗留库进候选 → 一次确认带回 → 真后端计数落库 (2.6s)
```

两条用例的判据：

1. **换安装目录**（便携式布局下候选扫描看不到旧库）：空态呈「从备份包恢复」且可点开
   `RestoreModal`（标题「恢复备份」）；「把上一版的作品带过来」此时不出现。
2. **同机升级全链**：播种遗留代数名 `novel-v1.db`（2 本书）→ 空态报「这台电脑上有旧版作品（2 本）」
   → 点出口行 → 向导**单候选自动预演（一次确认）** → 点主按钮 → 结果页「已带回 2 本书」→
   直接读宿主侧 `novel-v0.25.db`（sqlite）核对两本书确实落库 → 源库 `mtime/size` 不变。

## 全量 e2e 回归（同一隔离栈）

见 `up11-full-e2e.md`（全量 189 用例摘要 ＋ 与基线 commit `dfceb17d` 的对照）。
