# 爱小说 · 操作手册（用户手册＋客服知识库）

一套内容源，两个产出：**给用户的 HTML 手册**＋**给客服的知识库问答**。

```
docs/manual/
├── README.md          ← 本文件（方案与纪律）
├── build.py           ← 构建器（python3 + markdown，无其他依赖）
├── content/*.md       ← 用户手册章节（面向用户，大白话）
├── kb/*.md            ← 客服知识库条目（答案＋客服口径两节）
└── dist/              ← 构建产物（随源一起提交）
    ├── manual.html      用户手册单文件：侧栏目录＋本地搜索＋打印样式
    ├── kb-export.md     客服知识库·人类可读版（按场景分组，含内部口径）
    └── kb-export.jsonl  客服知识库·机读版（喂 AI 客服/RAG，一条一 JSON）
```

## 怎么用

```bash
python3 docs/manual/build.py           # 构建三产物
python3 docs/manual/build.py --check   # 保鲜门（见下）
```

- **用户拿 manual.html**：单文件零依赖，可挂官网/CDN、可随安装包内置、可直接打印成 PDF。
- **客服拿 kb-export**：md 版人看（培训/值班手册），jsonl 版喂机器（AI 客服问答）。
  每条 KB 固定两节：`## 答案`（可直接复述给用户）＋`## 客服口径`（收集什么信息、什么能承诺、何时转技术）。

## 保鲜机制（核心设计）

每篇 front-matter 的 `capabilities:` 声明该篇描述的 openspec capability：

```yaml
capabilities: chapter-dossier, workbench
```

`build.py --check` 逐个核对 `openspec/specs/` 下 capability 是否真实存在——**spec 改名/退役而手册没跟上，门直接红**。纪律：

1. 归档任何用户可见的 change 时，跑一次 `--check`；
2. 手册/KB 的修改随行为变更同一个 PR 走（和 specs sync 同批）；
3. 每篇带 `updated:` 日期，正式发布前过一遍近 30 天变更的 capability 对应篇章。

## 目录（v1 规划）

| 章节 | 状态 |
|---|---|
| ch-01 安装与开始 | ✅ |
| ch-02 写作全流程一览 | ✅（含断章新口径） |
| ch-03 套餐、激活码与账号 | ✅ |
| ch-04 设定详解（简介/题材/世界观/角色/主线/文风/伏笔） | ✅ |
| ch-05 卷与章纲（分卷规划/拆章抽卡/剧情推演/确认门） | ✅ |
| ch-06 正文工作台（生成/编辑/去AI味/朱雀/归档受理制） | ✅ |
| ch-07 预览、导出与备份（含免登出口/完本撤回） | ✅ |
| kb 客服知识库 | 10 条在库（安装/断章/归档修改/书稿找回/AI 失败/兑换码/退款发票/下载无反应/换机迁移/完本撤回），持续扩 |

口吻定形：大白话、短句、面向「不会用电脑也能装」的用户；不出现内部术语与 capability 名。

## 截图配图规范（v1 试点：场景·写正文）

截图来自**本会话独立环境**（不碰共享栈），配方：

1. 环境：`client/frontend` 构建产物由本地 C端 后端伺服——
   `DATA_ROOT=/tmp/<独立目录> SERVER_API_BASE=http://127.0.0.1:19000/api uvicorn main:app --port 8100`（S端 用本地 19000，绝不连生产）；
2. 会话：往 19000 注册一次性 `e2e_manual_*` 账号（全仓既定模式），token 写入 `DATA_ROOT/config.json`——**坑**：`expires_at` 必须是未来时间否则判定降免费；`last_login_at` 必须是过去时间否则「系统时间异常」；entitlement 快照照抄 `auth_local/service.py` 的 STANDARD_FALLBACK；
3. 播种与拍摄：`client/frontend/scripts/manual-shots-ch06.cjs`（Playwright；UI 播种演示书《云海剑歌》，**全程不碰 AI 调用**；截图前藏 toast——只 `display:none`，`remove` 会让 React 崩树白屏）；
4. 档位对比：改 config.json 的 `tier`＋`entitlement` 后 reload 重拍（trial=PRO 态、none=免费态）；
5. 图片：`img/<场景号>-<内容>.png`，1680w PNG（试过 JPEG q82 省 1.7x 但文字发糊，弃）；build 时内嵌 base64，manual.html 保持单文件（约 4MB）；
6. 脱敏：一次性账号＋虚构演示书＋伪 API Key（`sk-demo-not-real`，永不真实调用）；
7. **AI 链路场景**（生成正文/拆卷拆章抽卡等要拍 AI 交互的）：用本地 mock 模型
   `client/frontend/scripts/manual-mock-ai.py`（Anthropic Messages 协议，9100 端口，
   `client/backend/.venv/bin/uvicorn mock_ai:app --port 9100` 起）——两段式响应
   （首次=润色提示词、后续=正文流），`/v1/models` 返回 mock-v4。零真调用、流式节奏可控。
   坑：①模型配置保存后必须 `PUT /api/v1/novels/{id}/ai-model` 把书绑到配置，否则 write 503 missing_model；
   ②配置名每次运行要唯一（软删后唯一约束仍咬旧名）；③生成是两段式（润色→过目→再点生成），
   截「流式帧」要等正文字数超过提示词基线再拍；④选中段落才能展开「段落加工」，合成 Range 不进
   ProseMirror，须真实鼠标拖选。

新场景照此配方各建一个 `manual-shots-<scene>.cjs`。

## 结构范式（对齐腾讯云产品文档）

参照 cloud.tencent.com 的文档体系，本手册的信息架构四层：

| 层 | 腾讯云对应 | 本手册 |
|---|---|---|
| 快速上手 | 入门步骤（1 创建实例 → 2 连接实例） | ch-01 安装＋ch-02 全流程（编号步骤，一篇跑通） |
| 操作指南 | 操作指南（按任务域一篇一事） | ch-03～07 |
| 故障处理 | 故障处理（按症状命名：无法连接实例…） | kb 条目（书不见了/AI 生成失败/下载无反应…） |
| 常见问题 | 常见问题（按主题分组） | kb 按标签分组（侧栏与导出均分组） |

**单篇五件套模板**（对齐腾讯云单篇写法，新章节照此铺）：

1. 开篇一句「本文介绍…」——先声明本篇管什么；
2. 「开始之前」＝前提条件＋本章档位分布一句话；
3. 旅程步骤「第 N 步」编号推进，**权益点用【免费】【PRO】【MAX】徽标内嵌到每个功能点**（构建时自动着色：灰=免费／深绿=PRO／金=MAX），入口可见、点开引导的口径写进正文；
4. callout 分级：引用块以「`说明：`」「`提示：`」「`注意：`」开头，构建时自动着色（蓝=补充信息／绿=小技巧／黄=易错点）；
5. 结尾「下一步」——链向旅程下一篇，全册连成路径网（含跨到 kb 条目的内链）。

场景篇章配真机截图（拍摄规范见上节），每步至少一图；图文必须同批更新。

**待补**：使用限制页（生成次数/朱雀检测次数/设备数上限的具体数字，待产品确认后成篇——对应腾讯云每个产品必备的「使用限制」）。

## 事实源对齐（写内容前必读）

- **套餐价格与权益**：唯一事实源＝生产库 `tiers`/`skus`（见 tier-catalog skill）。样章中的四档价格是 2026-10-05 的矩阵口径，**正式发布前必须对一遍生产目录**。
- **客服时限口径**：一般咨询 48 小时、个保权利 15 个工作日——与 docs/legal 四件套逐字一致，不得改写（contact-support spec）。
- **客服邮箱**：单源 `server/frontend/src/constants/support.ts` 的 `SUPPORT_EMAIL`；本目录 `build.py` 顶部有一份镜像常量，换邮箱时两处同步改。
- **产品行为**：以合入 main 的 specs 为准，不写未发布功能；拆书等在途设计不进手册。

## 待拍板

1. **手册放哪**：A. 挂官网/CDN＋C端 顶栏「帮助」外链（推荐先做）；B. 随安装包内置离线版（二期）。
2. **客服知识库喂给谁**：人工客服培训（md 即可）／AI 客服 RAG（jsonl 即可）／飞书知识库（需加导出格式，说一声就加）。
3. **截图**：正式稿需要真机截图（v0.26 口径），谁出、何时出待定；当前样章纯文字可先评审结构。
4. **铺开方式**：docs-only 改动，建议不开 openspec change，定形后直接 PR 铺内容。
