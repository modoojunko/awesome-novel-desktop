# Proposal: c-update-staging-channel

## Why

用户口径（2026-10-26）：C端 每次发版直接推生产，用户先于开发者测到新包——0.37→0.38、0.38→0.39 两轮更新链事故全是「发版后才暴露」。要一条灰度通道：发版先进灰度，本机提前跑**完整更新链**（检测→下载→重启更新，不是只装个包），验收过再推进生产，让「发版即事故」变成「灰度拦住」。

## What Changes

心智模型：同一生产托管、**一份安装包实物、两个指路牌**——`download/v<VER>/` 实物目录（两渠道共用）、`download/staging/latest.json` 灰度指针（发版自动写）、`download/latest.json` 生产指针（只在晋升时推进）。

- **发版落灰度**：tag 流水线的 latest.json 部署与校验从 `download/latest.json` 改为 `download/staging/latest.json`；安装包/notes.html/版本化路径/prune/GitHub Release 全部不动。
- **晋升作业**：新建 workflow_dispatch 形态的 `client-update-promote.yml`（expected_version 对拍＋dry_run 预演）：拉灰度清单**原始字节**（不重序列化不重签，Ed25519 签名随字节走）→ 守护闸（清单合法、双平台域名可信、auto_enabled=true 必带签名、**灰度版本严格新于生产现网**防倒挂）→ 部署到 `download/latest.json` → 轮询回读比对。
- **本地渠道开关**：客户端支持数据目录下可选覆盖文件 `update-channel.yaml`（只读不写；不建＝生产行为完全不变）：`channel: staging`／`channel: prod`／`update_url: <清单地址>`；容错解析（BOM/智能引号/坏文件 fail-soft）；优先级覆盖文件 > env > 烘焙；检测载荷与手动检查响应带 `channel` 字段，手动检查提示非生产渠道附后缀。0.40 过渡期用既有 env 覆盖法（runbook 记载）。
- **runbook**：`docs/ops/client-release-staging.md`——发版三步、验收操作、晋升三步、逃生口（新 tag 重走；紧急停发仍走 resign 总闸）。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `installer-release`：「安装包国内分发」改写——latest.json 转存落点为灰度路径，生产指针改由晋升作业推进、保持唯一线上事实源语义；新增「灰度晋升（staging → 生产）」要求。
- `client-auto-update`：新增「灰度渠道本地覆盖」要求——覆盖文件形态与容错解析、优先级、信任域/派生地址跟随、`channel` 露出与前端后缀提示。

## Impact

- 流水线：`.github/workflows/client-package.yml`（release job 三处路径与注释）、`.github/workflows/client-update-promote.yml`（新建）。
- 后端：`client/backend/update_channel.py`（新建）、`client/backend/update_check.py`（`_candidate_urls` 委托＋载荷/refresh 加 `channel`）。
- 前端：`client/frontend/src/components/AcctMenu.tsx`（toast 渠道后缀）。
- 测试：`client/backend/tests/test_update_channel.py`（新建）、`test_update_check.py`（接线新例＋形状断言同批更新）、`client/frontend/src/__tests__/AcctMenu.test.tsx`（新例）。
- 文档：`docs/ops/client-release-staging.md`（新建）。
- 不动：签名链与密钥、安装执行链（#945/#946 面零交集）、lab 渠道（其 `auto_enabled` 重复键问题单独挂账不夹带）、prune（只删 `download/v<VER>/`，天然不碰灰度清单）。

## Design Impact

- 受影响端：仅 C端。
- 受影响面：账号菜单「检查更新」toast 文案（非生产渠道附〔灰度渠道〕/〔自定义渠道〕后缀）——无新组件、无布局变化、不触两端共享段；toast 非原型 parity 场景项，免原型先行（本判定即登记）。
- 文案遵循 §13：后缀为状态说明非补救语句，既有 toast 三分支动词口径不变。

## 非目标

- 不做按用户比例/多渠道分层灰度——只有 prod/staging 两渠道，staging 只服务本机验收。
- 不新增 UI 设置面——文件即开关。
- 不改签名链、安装执行链、数据迁移链。
