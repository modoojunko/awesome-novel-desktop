# Tasks: c-knowledge-source-align

> 跨仓 change：主体在知识内容仓（awesome-novel-knowledge，独立 git 仓，本地
> ~/Desktop/coding/awesome-novel-knowledge）；C 端仓只动树数据文件两行（slot_map 补
> tone/tic）。无用户可见界面改动（Design Impact：免原型，见 proposal）。

## 1. SDK 一期：映射＋校验＋树归属抽出（boss 2026-11-09 拍板：封装成 SDK，S端和 C 端都调用）

- [x] 1.1 SDK 包骨架（client/backend/vendor_sdk/novel_deconstruct_sdk，仓内包 pip install -e 过渡；二期独立发包）：`mapping.py`（map_deconstruct_products 纯化版——返回 dict 解耦 models）、`payloads.py`（载荷校验迁入）、`taxonomy.py`（node_for 注入式——树配置传入不绑包内文件）
- [x] 1.2 C 端 kb/deconstruct_import 改薄壳调 SDK（映射行为零变化，既有钉全绿）
- [x] 1.3 AI 调用接口注入：一期映射层不调 AI（纯函数），接口注入随二期引擎入 SDK（design 分期口径）
- [x] 1.4 SDK 单测：v2 全字段透传／树注入／校验闸（独立于 C 端后端可跑）

## 2. 知识仓：转换层改调 SDK（治本）

- [ ] 2.1 tools/deconstruct_batch.py：journal 增加 converter_version=2（旧缓存按版本失效自动重转换，不重拆书）
- [ ] 2.2 「产物→源条目」映射改调 SDK（novel_deconstruct_sdk.mapping——解除对 C 端映射代码的依赖），KbKnowledge dict → 基线源条目（透传 name/how/example/evidence_ch/confidence/kind/steps；条目级新增 example/evidence_ch/node_key）
- [ ] 2.3 node_key 归属：SDK node_for 注入知识仓 taxonomy/taxonomy.json（与 C 端同一份树）；求不到留空
- [ ] 2.4 文风 tone 输出 text 键（v2 口径）；删旧「（手法 instruction / 文风文笔 value）」注释与代码路径
- [ ] 2.5 转换层单测：v2 全字段产物 → 源条目全字段断言（example/evidence_ch/confidence/kind/node_key）；SDK 演进零改动断言

## 3. 知识仓：schema 升版＋validate 硬闸＋树补映射

- [ ] 3.1 schema/entry.schema.json：concept enum 扩「世界设定」「角色设定」；条目级 example/evidence_ch/confidence/kind/node_key 字段定义（type/maxLength）；payload 键面枚举（additionalProperties 按概念约束）
- [ ] 3.2 tools/validate.py：新增违规码 payload_key_invalid（键面外，如 v1 value 键）、node_key_unknown（树无此 key）；硬闸与 C 端 gates.check_baseline_entry 对拍单源复核
- [ ] 3.3 树文件补映射：taxonomy/taxonomy.json slot_map 增「文风|tone→style_role」「文笔|tic→craft_rule」——同批同步 C 端仓 kb/data/taxonomy.json（两处零漂移），CDN tree 翻 v2（tree_publish --version 2）

## 4. 知识仓：存量重跑＋试拆替换

- [ ] 4.1 215 条源条目按 converter v2 重跑（书稿目录重跑批量拆书收集段，断点缓存自动失效重转换；不重拆书不耗额度）
- [ ] 4.2 试拆版文件处置（boss 已拍板 2026-11-09：书稿在，本地下载目录——执行时与 boss 确认具体路径）：「拆书-斩神-前30章」「749-前40章」以全本书稿重拆替换，试拆文件剔除＋tombstone 登记
- [ ] 4.3 validate 全量过（零 payload_key_invalid／node_key_unknown）；源条目 payload 键分布复测：evidence_ch/confidence/kind/example 非零、value 键清零

## 5. 基线 v2 发布

- [ ] 5.1 tools/build.py --version 2（签名）＋本地全链 verify
- [ ] 5.2 发布 CDN /knowledge/baseline/v2/＋指针翻 v2（CI workflow 或 KNOWLEDGE_LOCAL_PUBLISH=1）
- [ ] 5.3 0.46/0.47 客户端 gates 口径单测实跑：v2 条目在 0.46 gates 下「整条跳过不炸」、0.47 gates 全收（向前兼容实证）
- [ ] 5.4 CDN 验收：v2 四件（manifest/entries/tombstones/latest）200＋sha 对拍；旧 v1 目录不动

## 6. C 端仓：树数据文件（两行）

- [x] 6.1 kb/data/taxonomy.json slot_map 补「文风|tone→style_role」「文笔|tic→craft_rule」（与 2.3 同内容）
- [ ] 6.2 kb 相关测试回归（树挂靠/总结/提炼全钉）

## 7. 回归

- [ ] 7.1 知识仓：validate 全量＋build/publish dry-run＋tree_publish dry-run
- [ ] 7.2 C 端：后端 kb 全量 pytest（树装配/总结/提炼/基线 sync 钉）＋ruff；前端 vitest 全量＋tsc（树视图/基线臂无改动回归）
- [ ] 7.3 真机：0.46.8 重开 → 基线 v2 同步 → 知识库列表官方臂形状（text 键/例句/可信度）→ 树视图基线挂靠可见
- [ ] 7.4 （纯数据与内容仓工具链改动，不触共享段——Design Impact 免原型判定依据见 proposal）
