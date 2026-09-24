## Context

批内防撞现成（拆卷 SPINE_SIM_LIMIT 相似复核／拆章轴互斥＋同质复核），批间无机制；抽卡状态在 useVolumePlan/useChapterPlan（均挂壳层），close 本就不清批次，但 open/openAi 恒重置重抽。exclude 属会话期用品（不落库），由前端随请求携带。

## Goals / Non-Goals

**Goals:** 重抽带 exclude（提示词中性禁令＋服务端同轴相似对拍）；误关/刷新恢复同批（不重复生成）；排上/成卷即清；从头再来逃生口。
**Non-Goals:** 排除清单落库；历史批回看 UI；D20 人物引入。

## Decisions

1. **exclude 走请求体，服务端不存**：`exclude: list[{axis≤20, line≤40}] ≤9 条`；每次重抽由前端把上一批并入。备选「服务端按会话存」被否：出卡本就不落库，加存储破坏契约。
2. **禁令块拼进素材串**：`_exclude_block()` 追加到 `<<material_blocks>>` 之后（中性措辞），两模板零改动、对拍三件套不受影响。
3. **对拍＝同轴且相似（difflib ≥0.6）**：one_liner ≤20 字短串噪声大，单凭相似会成片误杀；卷级 spine ≤40 同理，沿用 SPINE_SIM_LIMIT。
4. **不降温度**：排除重抽是求差异，不是合法性修复——普通首调温度即可（既有「重试降温」只属于结构性失败阶梯）。
5. **恢复判定**：内存批（directions/plans 非空且 drawnNo/卷号一致）→ 原样重开；刷新 → localStorage（key 含目标：`cp-draw:{pid}:{volRef}`／`vp-draw:{pid}:vol{N}`，载荷带 nextNo 复核）；排上/成卷/目标变化即清。
6. **排除上限 3 批 9 条**：太老的否决不必永远背着；「从头再来」清零重来。

## Risks / Trade-offs

- localStorage 与服务端无共享状态：跨浏览器不同步（单用户桌面应用，可接受）。
- 恢复的批次可能是旧素材生成的（设定后来改了）——批次本就不落库、作者可见可重抽，风险自洽。
- 章侧 3 处 redraw 按钮共用 draw()：exclude 语义统一（同目标章就带上），不需逐处分叉。

## Open Questions

（无——D21 口径 2026-09-24 已拍板）
