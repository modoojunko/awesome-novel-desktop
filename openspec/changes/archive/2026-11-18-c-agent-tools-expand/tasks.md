# c-agent-tools-expand 任务

## 1. 结构动作三件
- [ ] 1.1 caps/chapter.py：confirm/unconfirm/archive/unarchive 薄包装（service 直调，CapabilityError 归一）
- [ ] 1.2 tools.py 六写工具（confirm/unconfirm/archive/unarchive/add_volume/add_chapter）＋kind=write＋授权卡预览映射
- [ ] 1.3 scopes 全域共享挂账＋validate 覆盖
- [ ] 1.4 行为钉：确认/归档/建卷章各一钉（gate 拒绝→不执行；批准→真落库）

## 2. 世界观三件
- [ ] 2.1 caps/world.py 薄包装（draft/check/lore-suggest 同后端函数）
- [ ] 2.2 三读/产卡工具＋设定域挂账
- [ ] 2.3 产卡钉：世界观候选卡渲染＋不自动写回断言

## 3. 收尾
- [ ] 3.1 注册表/域校验＋ruff＋后端全量
- [ ] 3.2 e2e 回归（chat-dock 15/15 不回归）
- [ ] 3.3 重建 mac app＋提交


> 归档注记（2026-11-18）：未勾 10 项为 b176974f 拍板的暂缓批（handler 体反向抽取
> 挂 touch-me-when-changed 触发器，回归风险＞当前收益）——非欠账，随归档闭环。
