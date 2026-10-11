# Tasks: c-update-strip-below-appbar

## 1. 壳层挂载重排

- [x] 1.1 Navbar 上移 ClientShell（壳层骨架第一位：顶栏 → 提示条 → 内容 → 状态条），App.tsx 摘除
- [x] 1.2 UpdateNotice / ExpiryNoticeBar 壳层实例改挂 Navbar 之下；/novel/* 壳层整组让位（路由感知）
- [x] 1.3 NovelWorkspace 在书内应用栏（.appbar-wb）之下、模块导航之上补挂两条提示条（--imm 变体沿 pathname 自动生效）
- [x] 1.4 index.css / UpdateNotice.tsx 挂载口径注释同步

## 2. 测试

- [x] 2.1 ClientShell.stability.test：harness 补 QueryClientProvider 与 auth mock 扩面（Navbar 随居挂载）
- [x] 2.2 新增钉子：常规屏 DOM 序（顶栏 → 更新条 → 到期条 → 内容）；书内态壳层整组让位
- [x] 2.3 authRouting.test：ClientShell mock 同构（navbar 在 shell 内、children 之前）
- [x] 2.4 全量 vitest 绿（1502/1502）

## 3. 验证

- [x] 3.1 隔离栈 e2e：update-notice / expiry-notice / statusbar 三套绿（19/19）；全量套件绿（环境前提：worktree 内 `.docker-data/client` 软链指向隔离数据目录，缺链是纯环境红）
- [x] 3.2 截图视觉验证：书架/工作台两屏顶栏 y=0 钉在窗口顶、提示条紧随其下（几何断言 barTop=0/stripTop=48）
