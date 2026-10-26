# Tasks: c-update-staging-channel

## 1. 双端影响判定

- [x] 1.1 唯一用户可见面＝AcctMenu「检查更新」toast 文案后缀（非生产渠道）；无新组件、不触共享段、toast 非原型 parity 场景项，免原型先行（proposal Design Impact 已登记）。验证：本任务即判定记录。

## 2. 后端

- [x] 2.1 新模块 `client/backend/update_channel.py`：灰度清单地址常量（主/兜底）、覆盖文件容错解析（utf-8-sig、剥值两侧空白与全角引号、坏文件/空文件/未知值 fail-soft 回生产＋warning）、`override_candidates()`（staging/prod/update_url 三形态，channel 优先）、`channel_name()`（prod/staging/custom）。验证：`test_update_channel.py` 解析矩阵全绿。
- [x] 2.2 `update_check.py` 接线：`_candidate_urls()` 改委托（覆盖文件 > env > 烘焙；信任域与派生地址自动跟随）、GET 载荷与 refresh 响应加 `channel` 键（两条返回路径 shape 一致）。验证：`test_update_check.py` 新例＋既有形状全等断言同批更新，全绿。

## 3. 前端

- [x] 3.1 `AcctMenu.tsx`：`UpdateRefresh` 增 `channel?: string`；「检查更新」toast 在非生产渠道附〔灰度渠道〕/〔自定义渠道〕后缀（发现新版与已是最新两分支都带）。验证：`AcctMenu.test.tsx` 新例（staging 后缀/custom 后缀/prod 无后缀）。

## 4. 流水线

- [x] 4.1 `client-package.yml` release job：latest.json 部署与内容校验路径改 `download/staging/latest.json`；步骤注释与成功 echo 同步（灰度先行、生产指针由晋升作业推进、打印灰度清单 URL）；prune 注释补「灰度清单不在清理范围」。
- [x] 4.2 新建 `.github/workflows/client-update-promote.yml`：workflow_dispatch（`expected_version` 可选对拍、`dry_run` 预演）；守护闸（JSON 合法、version 形如版本串、platforms win/mac 域名可信白名单、auto_enabled=true 必带顶层签名、灰度版本严格新于生产现网——生产缺失/不可解析视为无现网）；字节原样部署（不重序列化不重签）＋轮询回读内容比对；复用 `schema_version` 版本比较单源。

## 5. 文档

- [x] 5.1 `docs/ops/client-release-staging.md`：心智模型（一份实物两个指针）、发版三步、本地验收操作（yaml 模板＋两平台数据目录路径＋0.40 env 过渡法＋「检查更新」绕节流＋toast 后缀确认）、晋升三步（dry_run→真晋升）、逃生口（新 tag 重走；resign 总闸紧急停发/回指旧版）。

## 6. 收尾

- [x] 6.1 门禁：后端 pytest（test_update_channel＋test_update_check）＋ruff check；前端 vitest＋`tsc`；`openspec validate c-update-staging-channel`。验证：命令 0 红。
- [x] 6.2 PR；合入后真机验收＝下一版 tag 落灰度→本机（env 法或 yaml 文件）跑完整更新链升上该版→改用 yaml 文件复验→晋升 dry_run→真晋升→生产 latest.json 指该版。验证：用户侧验收记录。
