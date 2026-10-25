# Tasks: c-prose-model-search

## 1. 前端

- [x] 1.1 `modals.tsx` `ModelPicker`：增 `query` 状态与过滤分组（模型 id/配置名命中、大小写不敏感、空组整组隐藏）；触发位文案改从全量选项取（当前项被滤掉时显示不跟搜索词变）；重开清零。验证：AiModal.test 新例——过滤/配置名命中/空态/重开清零。
- [x] 1.2 弹层顶搜索框：sticky 钉顶＋打开即聚焦＋`data-testid="ai-model-search"`；键盘（方向键/Enter/Esc/IME 组合期早退/cursor 钳位）沿 ApiConfigForm 先例；无匹配空态文案。验证：新例 Enter 带按次模型对、Esc 只收弹层、无匹配 Enter 不误选、IME 早退、选完/收层焦点回触发位（评审 P2 整改）、重开光标钉全量下标（评审 P3 整改）。
- [x] 1.3 `model-config.css` 新词 `.mp-search`（sticky＋无边框 mono 输入＋search 图标；只用既有 token 与 12.5px 字号档）。验证：`design:lint` 0 违规。
- [x] 1.4 门禁：vitest 全量＋coverage（1807/1807，全仓 100%）、`tsc --noEmit`、`design:lint`。验证：命令 0 红。

## 2. 设计资产

- [x] 2.1 `ADJUSTMENTS.md` 登记条目 c-prose-model-search（交互口径＋词汇入册＋不进 parity 依据）。验证：条目落档。

## 3. 收尾

- [x] 3.1 openspec sync delta→主 spec、change 移档 archive，随实现 PR 同批带上（sync 前 fetch 确认基线＝9d11bae1）。验证：`openspec validate` 绿。
- [ ] 3.2 PR＋CI 双绿；真机抽检＝多配置清单下搜索过滤、键盘选型、Esc 收层不关弹窗。验证：用户侧抽检或 demo 栈换包后自测。
