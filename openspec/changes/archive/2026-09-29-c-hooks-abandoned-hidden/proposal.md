# c-hooks-abandoned-hidden — 废弃伏笔默认不显示

## Why

用户拍板（2026-09-29）：「废弃的伏笔不显示」。#589 存量清理把 15 条重复变体标废弃后，
废弃条目仍出现在设定页台账三分组与工作台伏笔页签投影里，对写作与维护都是噪音。
废弃＝留痕可恢复，不该占日常视图；设定页保留「显示已废弃」开关作恢复入口。

## What Changes

- 设定页伏笔台账：废弃组**默认不渲染**；有废弃条目时列表尾部出轻开关
  「显示已废弃（N）／隐藏已废弃」，点开恢复三分组形态（组内行可改回活跃）。
- 工作台「伏笔」页签投影：SHALL NOT 显示废弃条目；汇总行计数只含活跃/已收束；
  行状态标注收两态（悬置/已收）。
- 后端零改动（数据留痕不动）。

## Impact

- specs：foreshadow-settings（台账与伏笔卡 MODIFIED）、workbench（中栏伏笔页签 MODIFIED）。
- 前端：HooksSettingForm.tsx / HooksPane.tsx ＋ vitest。
