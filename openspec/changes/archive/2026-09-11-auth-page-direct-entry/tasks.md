# auth-page-direct-entry Tasks

## 1. C端：授权地址直开 /auth（PR1 主体）

- [x] 1.1 service.py：auth_url 构造改为 `{web_origin}/auth?...`（public_server_api 剥尾部 `/api`，容忍尾斜杠），query 三参不变；注释注明裸域配置约束。验证：client 后端单测绿
- [x] 1.2 补 auth_url 构造单测：web_origin 剥离（带/不带尾斜杠）、pc_hash/pc_name/device_profile 三参齐全、pc_name 经 urlencode。验证：pytest 该文件绿（test_auth_url.py 6 用例 + normalize 6 用例 = 12 绿）
- [x] 1.3 全仓 grep 确认 client 侧无其他 auth-page 引用（mimosa baseline 目录除外）。验证：grep 输出仅测试 docstring 字样，零功能引用

## 2. S端 前端：AuthPage.vue 小修（随 PR1）

- [x] 2.1 AuthPage.vue：onMounted 读 `route.query.pc_name`，提交时作为 apiAuthorize 第 4 参传入。验证：vue-tsc --noEmit 绿
- [x] 2.2 AuthPage.vue：两个 AppInput 补 autocomplete（username / current-password）+ name 属性。验证：vue-tsc --noEmit 绿 + 页面渲染截图
- [x] 2.3 server/frontend e2e 全量 174 用例绿（含 auth-page.spec 注册链接断言升级为携带 query）。验证：playwright 174 passed

## 3. S端 后端：删除内联页（PR2 主体，合并在装新包之后）

- [x] 3.1 authorize.py：删 AUTH_PAGE_HTML（原 21-99 行）、GET /api/auth-page 路由、HTMLResponse 导入，更新模块 docstring。验证：ruff 绿 + pytest 全绿
- [x] 3.2 test_web_api.py：auth-page 断言改写为 404（test_auth_page_removed）。验证：pytest 该文件绿
- [x] 3.3 test_api_path_normalize.py：剥前缀形态断言改写为 404。验证：pytest 该文件绿
- [x] 3.4 contract/test_c端_contracts.py：契约改写为「GET /api/auth-page 返回 404」，注释注明页面实体迁至 S端 前端 /auth。验证：pytest 该文件绿

## 4. 验证与交付

- [x] 4.1 S端 后端全量 pytest 绿（venv python，341 passed）。验证：退出码 0
- [x] 4.2 C端 后端受影响测试绿（venv python 本地跑受影响文件 12 绿；全量容器跑留待 C端 发版门禁）。验证：退出码 0
- [x] 4.3 change 目录附 /auth 页渲染截图对照（screenshots/auth-form.png + auth-invalid.png）。验证：截图文件存在
- [x] 4.4 PM/UI 复审结论回收：UI 终审 P0=0、P1=autocomplete（已修，另加 name）；PM 复审无 P0、5 条 P1 全部修入本 change（注册闭环带 query 回跳 /auth、429 走 err.status 判定、tier 抽 constants/tiers.ts 单源+none/free 隐藏、form 包裹回车提交、autocomplete+name）；顺手清了 P2-2（成功态兜底文案）与 P2-4（document.title）及 role=alert。其余 P2（brand-row 词汇收敛、h1 三值统一、aria-busy、失败焦点迁移、iOS 16px 全局项、无效态品牌行）登记为切流后清理单，不阻塞。验证：复审输出归档会话记忆
- [x] 4.5 PR1 提交并合入 main（base=main，分支 feat/auth-page-direct）；提醒用户打 tag 发版+装新包。验证：PR URL 可访问
- [ ] 4.6 PR2 提交（hold 至用户装新包后合并）。验证：PR URL 可访问
