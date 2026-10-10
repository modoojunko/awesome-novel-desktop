# c-carry-degrade-remigrate — 降级回迁＋部分迁移态呈现＋缺口清单

## Why

「迁移部分成功」的用户面处置目前只有半套：结果卡能实名报缺口、能重迁，但——
① 被值域约束拒收的行（旧状态值等）重迁也进不去，只能永远「缺一行」；
② 点过「先这样」后，书架下次**自动重弹完整告知卡**，长得像从没迁过（误导，
也是客诉源）——「搬运不完整必须提示用户」条款钉了持续提醒行，但候选载荷没有
「部分迁移态」字段，前端无从分辨；
③ 缺口只报行数/表名，作家看不出「我到底少了什么」。

拍板（2026-10-10）：降级回迁＋差异清单＋三态呈现一个 change 一次收。

## What Changes

- **降级回迁**（引擎 5.2 步）：存在性核对后，对仍有行损失的表按值域映射登记表
  （c-legacy-drill-gate 落的 `migration/value_mappings.py`）改写声明列后重插缺行，
  重算 `rows_missing`、notes 实名降级明细；未声明映射的拒收行不降级、如实报缺口。
- **部分迁移态**：候选载荷增独立字段 `carried_partial`（有完成记录、status ok、
  完整性未达标；指纹对拍与完成态同源）。书架对部分迁移态 **不再自动重弹完整告知
  卡**，由既有持续提醒行承接（含「迁移」出口＋「本版不再提醒」）。
- **缺口清单**：免登只读端点 `GET /backup/db-migration/gaps` 返回「旧版有、这版
  没有」的实名清单（书名＋字数／配置名，按在场判定，无密钥材料，WAL 源走暂存）；
  结果卡不完整变体内嵌展示。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `db-generation`：ADDED「值域降级回迁（值域映射表驱动）」与「部分迁移态呈现与
  缺口清单」两个 requirement（引擎 5.2 步／候选载荷新字段与弹卡仲裁／gaps 端点
  ／结果卡清单）。既有「完整性判定」「搬运不完整必须提示用户」语义不动——降级
  发生在完整性计算之前，救回即无缺口；提醒行义务本就存在。

## Impact

- 后端：`migration/engine.py`（5.2 降级回迁）、`migration/router.py`
  （`carried_partial`＋`/gaps` 端点）；前端：`useLegacyDb.ts`/`carryStore.ts`
  （类型）、`NovelListPage.tsx`（弹卡仲裁＋常驻行）、`CarryDialog.tsx`
  （结果卡缺口清单）。
- 分支叠在 `fix/carry-modal-reshow`（#812）上——`carried_partial` 与双形态指纹
  同循环；#812 合后 retarget main。
- 回归：降级保行 e2e（CHECK 拒收→映射→落库＋notes）、未声明不降级、partial
  不重弹整卡、缺口清单实名＋密钥红线。
