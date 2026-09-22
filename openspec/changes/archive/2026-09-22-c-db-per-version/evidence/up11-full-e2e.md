# 全量 e2e 回归证据（c-db-per-version）

会话私有栈（project=`dbver`，容器 `dbver-*`，端口 18100/18101/18190，数据目录＝本 worktree
的 `.docker-data/client`，镜像 `--build` 自本分支并自证：

```
$ docker exec dbver-client-backend grep -c pre_rename_generation migration/engine.py   → 1
$ docker exec dbver-client-backend grep -c book_count_target_after migration/engine.py → 2
$ docker exec dbver-client-backend python -c "import os;print(os.environ['CLIENT_VERSION'])" → 0.25
```

命令：

```bash
E2E_BASE_URL=http://localhost:18101 UP11_DATA_DIR=$PWD/.docker-data/client npx playwright test
```

## 结果：168 passed / 4 failed / 17 skipped（189 用例，8.7 分钟）

```
✓  14  e2e/db-version-upgrade.spec.ts  UP-11 换安装目录：无候选时「从备份包恢复」恒在且可达 (964ms)
✓  15  e2e/db-version-upgrade.spec.ts  UP-11 同机升级：遗留库进候选 → 一次确认带回 → 真后端计数落库 (2.6s)
...
168 passed
```

## 4 条失败＝**存量**（已用基线 commit 对照证伪「本次引入」）

`settings-forms.spec.ts:251`（题材五格面板）＋ `volume-plan.spec.ts` ×3 —— 在**基线 commit
`dfceb17d` 自建的第二套隔离栈**（project=`basever`，端口 18200/18201/18290）上**同样 4 failed /
14 passed**，与本次改动无关（隔离环境差异；两者都不依赖本 change 触及的库文件命名/找回链路）。

parity `list.empty`：本次 1.463% vs 基线 1.449%（阈值 0.2%）——同为存量红（字体光栅漂移），
本次新增约 0.014%。

## 说明

- 首次全量跑（未修 spec 卫生前）另有 16 条 ENOENT：harness 硬编码
  `<cwd>/../../.docker-data/client/config.json`，隔离栈需把数据目录放该处并播种 `{}`——已按
  隔离配方处理（这是 worktree 跑 C端 e2e 的已知坑，非本 change 引入）。
- 首次全量跑中 UP-11 自身的 1 条失败＝**用例卫生问题**（种子 id 固定，`INSERT OR IGNORE`
  在「同库已被上一次跑写过」时插入 0 本 → 结果页如实报 0）；已改为每轮唯一 id，本轮全量通过。
