# c-agent-effects 任务

## 1. 后端 Effect 产生
- [ ] 1.1 写类工具注册表加 effect_domain/effect_target_from 元数据
- [ ] 1.2 router._consume step_end 时收集 effect → run_end 注入 effects 数组

## 2. 前端 Effect 消费
- [ ] 2.1 Aui2Dock run_end 分支提取 effects → 调 onEffects
- [ ] 2.2 NovelWorkspace 实现 onEffects → 按域刷新（复用已有加载函数）＋dirty 保护

## 3. 测试
- [ ] 3.1 后端：effect 生成钉（写工具 → effects 数组正确）
- [ ] 3.2 前端：onEffects 回调钉
