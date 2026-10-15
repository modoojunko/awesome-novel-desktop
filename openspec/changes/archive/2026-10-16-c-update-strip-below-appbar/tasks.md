# Tasks: c-update-strip-below-appbar

## 1. 壳层挂载重排

- [x] 1.1 Navbar 上移 ClientShell（壳层骨架第一位：顶栏 → 提示条 → 内容 → 状态条），App.tsx 摘除
- [x] 1.2 UpdateNotice / ExpiryNoticeBar 壳层实例改挂 Navbar 之下；/novel/* 壳层整组让位（路由感知）
- [x] 1.3 NovelWorkspace 在书内应用栏（.appbar-wb）之下、模块导航之上补挂两条提示条（--imm 变体沿 pathname 自动生效）
- [x] 1.4 index.css / UpdateNotice.tsx 挂载口径注释同步
- [x] 1.5 设计资产同步：list.html / book.html / preview.html 原型 strip 挪 appbar 之下＋ADJUSTMENTS 追加章节（评审 P2 整改；design:check 矩阵复跑＝书架/预览全绿，唯一红＝quota 存量 2.693% 与在案基线逐位一致；backup-restore.html 系修订演示稿不属布局基线，不动并在 ADJUSTMENTS 注明）

## 2. 测试

- [x] 2.1 ClientShell.stability.test：harness 补 QueryClientProvider 与 auth mock 扩面（Navbar 随居挂载）
- [x] 2.2 新增钉子：常规屏 DOM 序（顶栏 → 更新条 → 到期条 → 内容）；书内态壳层整组让位
- [x] 2.3 authRouting.test：ClientShell mock 同构（navbar 在 shell 内、children 之前）
- [x] 2.4 全量 vitest 绿（1502/1502）

## 3. 验证

- [x] 3.1 隔离栈 e2e：update-notice / expiry-notice / statusbar 三套绿（19/19）；全量套件 184 过＋34 条红（S端 demo 旧镜像注册校验更严／隔离栈无 AI Key／spec 默认打共享端口 19000，经 origin/main 同栈 A/B 失败集合逐条相同定罪＝存量/环境，与本改无关；另需 worktree 内 `.docker-data/client` 软链指向隔离数据目录，缺链另有 20 条 ENOENT 假红）
- [x] 3.2 截图视觉验证：书架/工作台两屏顶栏 y=0 钉在窗口顶、提示条紧随其下（几何断言 barTop=0/stripTop=48）
