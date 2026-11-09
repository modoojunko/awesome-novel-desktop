# Design: c-knowledge-source-align

## 跨仓布局

| 仓 | 改动 | 说明 |
|---|---|---|
| awesome-novel-knowledge | 主体 | 转换层重写/schema 升版/validate 硬闸/存量重跑/基线 v2 发布 |
| ai-novel（C 端） | 仅树数据文件 | kb/data/taxonomy.json 补 tone/tic 两条 slot_map（随下版）；零代码改动 |

树两处零漂移：知识仓 taxonomy/taxonomy.json 与 C 端 kb/data/taxonomy.json 同批改（本 change 的 tasks 里作为一步原子落）；CDN /knowledge/tree/ 指针随发（tree_publish 已就绪）。

## 架构主从

两个知识库各自维护（boss 2026-11-09 定口径）：S端官方知识库＝本仓（知识内容仓＋CDN
/knowledge/ 分发，内容生产与发布都在这）；C端作家知识库＝账号本地库（作家自主积累）。
S端库经 CDN 投影为作家库的只读「官方精选」层（overlay 写时复制既有）——本 change 只修
S端库生产链，作家库零侵入。

## 判定：拆书引擎与提示词零修改

批量拆书调用的提示词就是 C 端 prompts 仓的 deconstruct_* 模板（经
--client-backend/--prompt-pack-dir 复用 C 端检出，知识仓无自有提示词）——
模板已是 v2 口径（实测拆书产物 name/how/example/evidence_ch/confidence/kind
张张全），**零修改**。引擎调用链（断点续跑/journal/维度派发）同样**零修改**。
本 change 只重写「产物→源条目」的转换映射段（约几十行旧口径挑键逻辑）。

## 核心决策：拆书能力封装为 SDK，S端（知识仓）与 C 端都调用（boss 2026-11-09 拍板）

依赖分桶实测（deconstruct/*＋kb/deconstruct_import）：

- **应用层耦合**（models/db/config）全部集中在任务编排层：dispatcher/pipeline/
  service/router/imports/apply/calibrate/mdrender——进度落库/取消/路由是 C 端应用特有；
- **纯核心零应用层依赖**：模板渲染（settings_map/cards）、批次切分、产物解析归并、
  载荷校验（kb/payloads/kb/concepts）、树归属（node_for 注入树配置）、映射
  （deconstruct_import 映射逻辑——KbKnowledge 返回对象改 dict 解耦 models）。

SDK 形态：独立包（暂名 `novel-deconstruct-sdk`），纯核心入包；AI 调用以接口注入
（SDK 收 `async chat(...)` 回调，不绑 C 端 ai_client 实现）；树配置注入（taxonomy
json 传入，不绑包内文件）。两端消费：

- C 端：保留任务编排层（dispatcher/pipeline 落库/进度/取消），引擎调用改调 SDK；
- S端（知识仓）：pip install SDK，批量驱动直接调——**解除对 ai-novel 检出的
  运行期依赖**（构建 CI 单仓即可）。

### 分期（一期起步，二期全量）

- **一期（本 change）**：抽「映射＋校验＋树归属」为 SDK 首模块——
  `map_deconstruct_products` 纯化版（返回 dict）＋payloads 校验＋taxonomy node_for
  注入式；C 端 kb/deconstruct_import 改薄壳调 SDK；知识仓 deconstruct_batch 改依赖
  SDK。消掉知识仓对 C 端映射代码与检出的依赖（拆书引擎调用仍走 C 端检出——二期收）。
- **二期（另行立项）**：拆书引擎纯层全量入 SDK（模板渲染/归并/批次），C 端编排薄壳化；
  知识仓彻底零 ai-novel 依赖。

### 过渡期兼容

一期 SDK 由 C 端仓以「仓内包」形态承载（client/backend/vendor_sdk/ 或独立目录
pip install -e），知识仓 CI 双仓 checkout 拉 C 端装 SDK——二期独立发包后解除。

## 构建依赖策略（一期过渡＋二期终态）

- 一期：知识仓 CI 双仓 checkout（拉 ai-novel 装 SDK，pin C 端 commit 入 manifest）；
  本地跑 boss 机器零成本；
- 二期终态：知识仓单仓 CI（pip install novel-deconstruct-sdk），零 ai-novel 依赖。

deconstruct_batch.py 已运行期依赖 C 端后端检出（AI_NOVEL_BACKEND_DIR/--client-backend）——
转换映射同样 import `kb.deconstruct_import.map_deconstruct_products(user_id, task_id, genre,
products)`（返回 KbKnowledge 对象列表），再适配成基线源条目 json：

```
KbKnowledge 字段            → 基线源条目
  concept/genre             → 同名
  title                     → title（≤40 截断）
  instruction               → instruction（闸长 240）
  example                   → example（条目级新字段）
  evidence                  → evidence_ch（条目级新字段；纯章号，剥例句混串）
  payload_json（v2 全字段）  → payload（kind/confidence/name/how/steps...）
  when_json                 → when
  src_ref/src_key           → src_key（baseline:{genre}:{hash} 口径重排）
  node 归属（slot→node_for）→ node_key（新增；树缺位时留空）
```

user_id/task_id 传占位（映射只用于形状，不落库）。**C 端映射演进＝知识仓自动跟随**，永久消两链漂移。

## 存量重跑策略

- 断点缓存（~/.cache/awesome-novel-knowledge/deconstruct-batch）已有产物缓存——转换重写后缓存按「转换器版本号」失效（journal 记 converter_version=2），自动全量重转换，不重拆书（不耗 LLM 额度）；
- 试拆版文件：斩神/749 全本书稿若在书单目录则重跑即得全本条目（试拆文件剔除）；不在则标记废弃＋tombstone；
- validate 增违规码：`payload_key_invalid`（键面外）、`node_key_unknown`（树无此 key）。

## 发布与兼容

- 基线 v2：build --version 2 → publish（CI/本地开闸同基线惯例）→ 指针翻 v2；
- 向前兼容依赖既有「整条跳过」机制——v2 新键条目在 0.44~0.46 客户端被跳过不炸（gates 按键面判 invalid → skip 单条）——tasks 里必须实跑一次 0.46 客户端口径的 gates 单测验证；
- CDN /knowledge/tree/ v1 与基线 v2 无耦合（树走自己的 latest），互不阻塞。

## 回滚

- 基线指针回翻 v1（版本不可变原则：v2 目录留存不删）；知识仓 git revert；C 端树文件随版回退。
