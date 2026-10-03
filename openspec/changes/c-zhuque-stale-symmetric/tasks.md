# Tasks：c-zhuque-stale-symmetric

## 1. 前端：双向判定

- [x] 1.1 `useZhuqueCheck.evaluateStale`：status=ok 且有送检指纹时 `stale = 送检指纹 !== liveHash`（双向置位/解除；一致时若已 stale 才写，避免无谓 notify）
- [x] 1.2 vitest：置灰后 live 回到送检指纹 → 自动解除；不一致保持置灰；idle/running 不受影响

## 2. 验收

- [x] 2.1 `openspec validate c-zhuque-stale-symmetric --strict` 过；vitest/tsc/build 全绿（存量红除外）
- [x] 2.2 真机：检测→切页再切回不再误报过期（或短暂闪烁后自动恢复彩色）；改字置灰→撤销→自动恢复彩色
