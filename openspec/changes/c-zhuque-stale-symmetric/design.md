# Design：c-zhuque-stale-symmetric

## D1. 双向判定（唯一逻辑改动）

`evaluateStale` 语义从单向置位改为状态等式：

```
status=ok 且有送检指纹时：mismatch = (送检指纹 !== liveHash)
若 mismatch !== 当前 stale → setState(key, { stale: mismatch })
```

- **只管 ok 态**：running/error/idle 一律不碰（running 中解析回的旧指纹不会污染检测中状态）。
- **仅在翻转时写**：避免同值 setState 触发无谓 notify（三消费点全量重渲染）。
- 异步边界（WebCrypto fingerprint promise）在守卫前——resolve 时重读仓状态，竞态安全。

## D2. 为什么双向是正确语义

`stale` 的诚实含义＝「结果与当前正文不一致」。修复前的单向置位让瞬态误判（两段式选章恢复窗口里编辑器装着别章内容）**锁死**到重检；双向后终态恒等于真值——窗口期仅短暂闪烁（两段式恢复是既有导航语义，本 change 不改导航）。副产语义：「改了又改回」（撤销）自动恢复彩色——结果对当前正文确实有效，诚实呈现。

## D3. 调用面与既有语义核对

- 调用点两处（ProsePane 载入一次性评估＋docChanged 事务监听），签名未变。
- applyZhuqueSegments 的灰变体、结果条 stale 态、重检出口全部沿用状态，无感。
- 清除/落库/水合/复合键（#636/#649）零交互改动；abort 恢复 prev 后由下一次 evaluate 收敛。

## D4. 测试

- vitest 新增：置灰 → live 回送检指纹自动解除 → 再改动再置灰；既有 stale 链用例不变全绿。
