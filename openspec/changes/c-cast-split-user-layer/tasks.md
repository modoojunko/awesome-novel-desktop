# Tasks: c-cast-split-user-layer

## 1. 代码（client/backend）

- [x] 1.1 `prompt/context.py`：新增 `cast_anchors_block`（主角/反派过滤，复用 `_CAST_DEPTH_ROLES`；`cast_profile_block` 不动，arc/素材包消费方不受影响）
- [x] 1.2 `write/chapter_writer.py`：`build_system_prompt` 的 cast_anchors 改恒定锚；`to_user_material` 新增「本章出场配角」块（名/别名逐字匹配本章素材文本；无命中不出节）；相关注释理由句更新
- [x] 1.3 测试：两条旧设计用例改写为新契约（配角不入 system／新增配角 system 逐字节不变＋出场走 user）＋新增别名匹配用例；`test_chapter_writer.py` 34/34 绿（容器内挂提示词仓跑）
- [x] 1.4 全量套件：2147 passed；15 failed 逐条核对为存量/环境问题（pytest 9.x 无 pytest-asyncio 的 async 用例、auth 时序、挂载触发的 repo_no_prompt_templates），原版代码对照同样失败

## 2. 配套

- [x] 2.1 提示词仓 `sync.py` CURATED：write_chapter `{cast_anchors}` 占位符描述同步（cb4d53b；模板正文零改动；lint＋50 绿）
- [x] 2.2 演示栈重建：compose build client-backend ＋ up -d，容器内验证（配角不入 system／出场配角进 user）

## 3. 验收（真机/演示栈）

- [ ] 3.1 生成正文弹窗「查看本次提示词」：system 段无配角卡、user 段尾部有本章出场配角（或无该节＝本章无配角出场）
- [ ] 3.2 新建一张配角卡后连生成两章：第二章 system 不因新配角变化（提示词缓存前缀稳定）
- [ ] 3.3 废卡（小憨憨类）删除后确认不再出现在任何层（数据侧手工）
