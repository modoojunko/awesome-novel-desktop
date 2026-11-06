# c-kb-summarize · Tasks

## 批A · 模型归位（素材态）

- [x] A1 消费端过滤收口：`kb/query_scope.py` `visible_knowledge_filter()`（origin != 'material'），四处消费端（星图装配/选择器/写法块/书级副本）统一引用；列表默认视图**含**素材行（带标展示，不滤）；验证：素材行在四处均不可见、列表可见（单测）
- [x] A2 手录切素材：`create_entry` 素材路径（origin=material、默认槽位装载退役）；表单提交文案「素材已收录，总结后成为知识点」；验证：手录单测断言 origin=material
- [x] A3 拆书收录切素材：`collect_task_to_kb` 每产物卡落素材行（幂等键口径不变，不再建知识＋实例）；验证：收录单测断言素材行、无知识行
- [x] A4 列表「素材」标＋素材查看/删除（真删＋确认弹窗文案）；验证：列表返回素材行带标、删除走真删

## 批B · 总结管线

- [x] B1 ensure DDL：`kb_summarize_runs` / `kb_summarize_candidates` 两表（幂等，挂 lifespan 既有 ensure 通道）；验证：空库跑两遍不报错
- [x] B2 `kb/summarize.py`：聚类（genre+concept 分桶）→ LLM 提炼（提示词 `kb_summarize`）→ 候选校验（material_ids 归属桶、标题非空、定义 ≤500）→ 落候选 pending；runs 记录＋单飞（同 genre running 即跳过）＋模板缺失 fail-soft；验证：单测覆盖候选校验三闸、单飞、fail-soft（llm=False 确定性路径同整理先例）
- [x] B3 采纳/忽略端点：采纳＝建知识（origin=summary）＋素材转实例＋素材行归档＋候选 adopted；忽略＝dismissed；已用素材的后到候选自动剔除；验证：单测覆盖采纳转化三步、素材用尽剔除
- [x] B4 触发：整理面板手动触发端点＋启动期积压 ≥5 自动触发（同整理启动钩挂点）；验证：单测覆盖阈值判断与触发落档
- [x] B5 提示词仓：`kb_summarize.prompt`（输入素材组→输出候选 JSON 契约）＋manifest 登记＋配额墙核对；验证：prompts 仓 CI 绿

## 批C · 前端

- [x] C1 整理面板「总结知识点」入口＋运行状态行；候选确认清单（采纳/忽略，复用 pending 关系清单交互先例）；验证：组件测试覆盖入口、清单渲染、采纳/忽略调用
- [x] C2 列表素材行「素材」标＋查看（只读抽屉态：原文＋出处）＋删除（真删确认）；验证：组件测试断言标与只读态
- [x] C3 手录表单提交文案更新；验证：文案测试

## 批E · 知识树与树形图谱

- [x] E1 `kb_entries` 加 `parent_id` 列（ensure DDL）＋写入环防御闸（parent 链回溯自己即拒）；验证：单测覆盖挂根/挂父/环拒
- [x] E2 总结候选带 parent 归属（提示词输出 parent 归组；候选校验 parent 合法性）；采纳落树位；验证：单测覆盖挂根/挂父采纳
- [x] E3 星图装配改知识树：概念根 → parent 逐层知识星（层级边实线）＋六类关联边（虚线）＋深子树折叠计数；素材不进图；验证：装配纯函数单测（层级/折叠/合法边）
- [x] E4 `StarSeaPanel` 树形渲染＋知识卡（点叶子开卡见实例群）；WebGL 降级口径不变；验证：组件测试

## 批D · 回归与验收

- [x] D1 后端全量相关子集绿＋ruff；前端 coverage 契约绿＋tsc
- [ ] D2 全链真机走查：手录素材 → 总结 → 候选确认采纳 → 星图/选择器出现该知识 → 关系整理吃新知识；记录截图
- [ ] D3 提示词包发布（kb_summarize 上包）随发版流程
