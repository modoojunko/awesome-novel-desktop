# Tasks（补录——实现已于 #565 完成，此处回填执行记录）

## 1. 排查定因

- [x] 1.1 前端消费方定位：按对象读 `outline.characters` 的仅设定页签 SettingsChangelogPane 与
  右栏统计 AiAssistPanel 两处；验证：grep 全仓——chapterForm 写侧 string[]（`join("\n")` 读/
  `lines()` 写）正确，e2e 零断言钉此形状
- [x] 1.2 契约实勘：读侧 `assemble_chapter` characters=string[]＋`character_states` 单列（仅非空
  条目），写侧 `_replace_children_impl` 同形；GET 路由 `workflow.engine.load_chapter` 纯委托 store，
  `get_chapter_row` 只回元数据、不含 outline 键不覆盖；真库 novel-dev.db vol-1-ch-1 三角色名字在库、
  state_change 全空——与「3 个空行」吻合；验证：代码链闭环＋sqlite 拷贝只读实勘（不打开活库句柄）

## 2. 修复

- [x] 2.1 SettingsChangelogPane：characters 按 string[] 取名字、character_states 按名字对齐出
  state_change（Map 对齐＋空名过滤）；验证：tsc --noEmit 0 错
- [x] 2.2 AiAssistPanel 设定页签统计：改从 character_states 计数（保留 trim 过滤形态，最小 diff）；
  验证：tsc --noEmit 0 错
- [x] 2.3 测试 mock 改真实契约形状（storylineHooksAndLore）＋补出场角色名字上屏断言；验证：
  vitest 3 文件 12 用例绿（storylineHooksAndLore/rewriteFlow/AiAssistPanel）

## 3. 评审与合入

- [x] 3.1 review-agent 评审（合并基线 0d02dc9e＝分支点）：无 qualifying findings——API 形状闭环
  验证；「角色关系」页签 graphStats 数关系边（/characters/graph）非同型 bug；chapterForm join 交叉
  印证契约；看过不 flag：重名 React key（存量、本次严格改善）、hasChanges 死变量（存量未触及）、
  名字 trim/filter 防御性冗余（够不上 flag 线）；验证：评审报告在案
- [x] 3.2 分支 fix/settings-changelog-cast-shape（独立 worktree，主检出只留并行会话自己的 4 个
  未提交后端文件）→ PR #565 → CI 三条 CodeQL Analyze 失败＋build 取消（与 #564 完全同签名，
  main 自身 CodeQL 亦红）→ squash 合入 = e427e16d；验证：gh pr view 565 = MERGED，远端分支已删

## 4. 部署

- [x] 4.1 演示栈 client-frontend 从合并 commit 临时 worktree 重建（`-p novel-demo` compose build
  带 brand 上下文；主检出 chapter_writer.py 被并行会话 WIP 占用不能 ff，不动它；换包前先
  `docker run --entrypoint sh` 进镜像抓特征串）；验证：镜像内 bundle `character_states`×2
- [x] 4.2 5174 换包验证：`up -d --no-deps client-frontend` 仅重建前端容器（后端未动、SQLite 数据
  不涉），线上 bundle 指纹 `character_states`×2＋章档特征（dossier/章档）保留＝无版本倾斜；验证：
  curl 5174 资产名变更＋grep 实证；遗留——演示栈 project 引用的 wt-demo compose 文件已随 worktree
  删除成幽灵路径，本次以主检出 compose 定义重建成功，后续整机重建宜统一到主检出配方
