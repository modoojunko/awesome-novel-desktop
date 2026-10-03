## 1. 模板：polish_text.prompt v3.1 → v4

- [x] 1.1 头部 changelog 注释更新为 v4（c-polish-prompt-anti-ai：策略驱动升级；保持 `<<system>>/<<user>>` 分层与 system 段首角色句机制）
- [x] 1.2 system 层新增「## 降AI策略优先级」段（design.md D1 文案照抄：①信息轮次化——含人物在场护栏（不虚构对话对象）②场景换场——含舞台/装饰区分与「示意」标记示例 ③极简化——r3 原句对示例）
- [x] 1.3 system 层新增「## 死路」禁令段（D2 文案照抄：标点/同义词/调序/人味闲笔 SHALL NOT；同义词含禁用词必改例外；「不为改而改」出口；末行示例实体防护）
- [x] 1.4 system 层新增结构红线（D3：与「反AI结构红线注入」七族同源措辞，逐模板成文；取消「不是A是B」表达力例外）；检查清单同步修两处矛盾——第 2 条拆分（破折号零容忍/分号维持三处阈值）、第 3 条删「确有表达力的可保留」
- [x] 1.5 检查清单第 6 条节奏校准（D3：逗号长句默认＋碎句即记账腔＋短句偶尔重拍对话不受限；保留「不合并段落、不拆分段落」）
- [x] 1.6 铁律微调（D4：删「70% 属正常」；篇幅改为默认 110%、信息轮次化放宽 160%；其余铁律不动）
- [x] 1.7 优先级栈更新（D5：禁止规则＞降AI策略＞结构红线＞检查清单＞文风参考）
- [x] 1.8 核对 user 层不变（writing_style/anti_ai_rules/selected_text 边界标记/surrounding_context 禁改写标注）

## 2. 测试

- [x] 2.1 `tests/test_prompt_layering.py` 全绿（分层不破）
- [x] 2.2 polish 相关测试全绿（test_write_prompt_polish 等自造 fixture 不受影响）
- [x] 2.3 新增模板特征串断言（策略段/死路/结构红线/节奏校准特征串在 system 层；「70% 属正常」「拆长并短」不再出现）
- [x] 2.4 跑 `client/backend` 相关 pytest 子集（auxiliary/polish/write 相邻文件）

## 3. 验收与收尾

- [ ] 3.1 真机抽检：选一段实测含信息承载叙述的选区跑「去AI味」，人工对照（信息轮次化是否生效、死路禁令是否被违反、篇幅落点），结论回填 change 目录
- [x] 3.2 `openspec validate c-polish-prompt-anti-ai --specs` 通过
- [x] 3.3 提交＋PR（标题不带硬编码 PR 号），CI 判读
