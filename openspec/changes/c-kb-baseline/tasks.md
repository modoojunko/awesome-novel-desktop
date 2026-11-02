# c-kb-baseline · Tasks

## 批A 同步管线（后端）

- [ ] A1 `kb/baseline.py`：sync 入口（latest 指针→manifest 校验→下载→merge→记版本，全链幂等）
- [ ] A2 merge 规则（用户资产优先/tombstone 下架分层/首装保守口径，design D3）
- [ ] A3 启动补偿挂接（照 prompt-pack sync 先例；失败静默＋状态记录）
- [ ] A4 单测：首装/重跑幂等/用户改过保状态/tombstone 分层/失败不阻断

## 批B 来源标签（后端＋前端）

- [ ] B1 src_kind="baseline" 常量与筛选支持（kb 服务/路由）
- [ ] B2 知识库页来源筛选项「官方精选」＋条目卡标签
- [ ] B3 AI 整理跳过 baseline（候选查询过滤＋整理单测）
- [ ] B4 前端入约＋组件测试

## 批C 内容与发布（内容仓）

- [ ] C1 打样扩量：玄幻/都市补齐＋新增 1-3 题材（每类手法＋场景写法 10-15 条过 validate）
- [ ] C2 publish 真实上传实现＋KNOWLEDGE_CDN_BUCKET secrets（boss 侧配）
- [ ] C3 基线包 v1 发布＋真机同步走查
