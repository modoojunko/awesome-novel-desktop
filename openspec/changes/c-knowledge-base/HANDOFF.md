# 写作知识库 · 实施交接文档（2026-11-01 全量重写，此前的批1 版本已过时）

## 一句话现状

PR #993（`c-knowledge-base` → main）**21 笔提交、CI 双绿**：批 1-7 全部开工，一期能力闭环
（存/看/管/进书/备份），**真机首验完成并修了 4 个 mock 探不到的真 bug**。**刀2c ①②③ 全落**（① 存储切换 5e062fa3；② 消费面走查过；③ 头像字节 boot 搬迁），
剩二阶段（AI 整理＋写法块注入）。

## Boss 拍板集（按时间序，均已执行或挂账）

| 拍板 | 状态 |
|---|---|
| 知识库是编写 prompt 的唯一记忆源；各库只是知识的一部分（底座论） | 架构总纲 |
| 角色库是知识库的一个实例；迁移进一期 | 刀2a/2b/2c 推进中 |
| AI 整理（关系/合并/纠偏）挪二阶段 | 挂账 |
| 写法块选择器+注入（动态拼提示词）「建完再看」＝二阶段 | 挂账 |
| 3D 蒲公英/大脑降 Lab；默认 2D 全局图（force-graph） | 已交付 |
| 去派生流程（UI/文案全删，数据模型保留，P1 再议新库入口） | 已执行 |
| 刀2c 走**后端适配器**（router 委托 kb_entries，前端零改动） | 2026-11-01 已拍板 |
| 1.17 design:check 收编改判：随逐屏校准批次走（强登记污染设计闸信号） | 已执行 |

## 已交付（按批，commit 可考）

| 批 | 内容 | commit |
|---|---|---|
| 批1 底座 | 11 表/六概念/闸门/推断/浏览页 | e007304f＋修复 d755cc84/8a0e658a |
| 前端真链路修复 | kbApi 双前缀/不剥壳/死调用/收起死臂 | c4fc03f0 |
| 批3 启用落设定 | kb/snapshot.py＋库卡＋来源行（KbSourceStrip） | 28e2e17c＋2f84612a |
| 批4 挑原型 | kbPrototype.ts＋弹窗＋KbPref.adopt_count | 334e93c0 |
| 批5 备份 v9 | FORMAT_VERSION 9＋配置包 kb 段＋单书 kb-book.yaml＋恢复重建标签 | 2ecd5928 |
| 批6 刀1 迁移 | CharacterPayload 全量 24 字段＋migrate_library.py＋表 DEPRECATED | 88a468e3 |
| 批6 刀2a 写通道 | PATCH/DELETE 条目（rev 并发/软删）＋payload 补 aliases/role/kind | 97141aba |
| 批6 刀2b 地基 | 双向映射单源＋适配器裁定＋备份恢复自动镜像 | e184bbfa＋4044f35c |
| 批6 刀2c ① 存储切换 | library/service 读写切 kb_entries＋kb_entry_blobs 头像新表＋复活臂＋备份带字节 | 5e062fa3 |
| 批6 刀2c ②③ 消费面＋头像搬迁 | 走查三面全过＋blob_migration boot 迁移（幂等/孤儿保留/搬后删旧行） | 本轮 |
| 批7 全局图 | graph 两端点＋force-graph 2D（聚合/下钻/面包屑/邻域高亮） | 7b1d4f12＋4e0ae77f |
| 真机四连修 | 手录 500/默认装载/kapsule 两层/节点可见性 | 2e493fb4＋79d17ff2 |
| 性能/工件 | 10 万级回归闸＋tasks 勾选＋roadmap | 3786618d |

## 关键架构（动代码前必读）

- 表：`models/kb.py` 11 张（账号 8＋书内 3）；**C端无 alembic**，boot `create_all` 兜底，
  新表自动建、**新列不会被加到已存在表**（未发版前可随意改表，发版后加列须走迁移）
- 分层：kb/concepts（词表）→ payloads（强校验 extra=forbid）→ gates（入库闸）→
  infer（概念推断）→ service（CRUD/默认库/标签）→ snapshot（书绑定/落设定）→
  migrate_library（角色库桥）；**kb/ SHALL NOT import write/、deconstruct/**
- 消费端键＝payload 真实键：文风/文笔→style 白名单键（STYLE_WRITE_KEYS）、世界→
  world V2 8 键、角色→建卡预填（kbPrototype.ts）、手法→写法块（二阶段）
- 信任链：`get_current_user` **不验签 JWT**，只核对请求头 token 与
  `$DATA_ROOT/config.json` 的 token 一致；AuthGuard 只查 localStorage 非空
- 后端信封：一切 `/api/kb` 响应 `{ok: true, data}`；前端 kbApi `unwrap` 剥壳；
  request() 自带 `/api` 前缀，各 API 库 BASE 只写功能段（`/kb` 不是 `/api/kb`）

## 真机冒烟栈配方（复用 data-smoke/，已有登录态）

```bash
# 终端1 后端（隔离 DATA_ROOT＋独立端口）
cd client/backend && DATA_ROOT=./data-smoke SERVER_API_BASE=http://127.0.0.1:19099/api \
  .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8801
# 终端2 前端（vite 代理指自起后端；curl 探活用 localhost 不能用 127.0.0.1——vite 绑 IPv6）
cd client/frontend && VITE_API_PROXY=http://127.0.0.1:8801 npm run dev -- --port 5201 --strictPort
```

浏览器：开 `http://localhost:5201/tools/kb`（HashRouter，直导航用 `/#/tools/kb`）→
无 token 会跳 /login → console 执行
`localStorage.setItem('auth_token','smoke-token-kb-2026')` → 回 `/#/tools/kb`。
config.json 里 token/username 已备好（smoke-tester）。**「正在准备写作能力」弹窗**
=S端不可达拉提示词包失败，预期内、不阻断 KB 页。收栈：`lsof -ti :8801 :5201 | xargs kill -9`。
⚠️ 后台起服务**别接 `| head`**（管道 SIGPIPE 会掐死进程）。

## 判例集（踩过的坑，反着长记性）

- **mock 假绿**：页面只有 mock 测试时真链路 bug 全潜伏（kbApi 双前缀/不剥壳/死调用/
  手录 500 四案全靠真机+覆盖率契约钓出）；新页面必须真机走一遍再算完
- **真机 500 根因**：`create_entry` 失败臂 `error` 恒 None，router 必须判 `entry is None`
  而非 `if error`（回归钉：test_手录校验失败_422带字段错误而非500）
- **CharacterLibraryBlob 真 FK 墙**（刀2c ① 实证）：blob.library_id 有指向
  character_library 的真 FK＋foreign_keys=ON，entry id 键插必炸——「新表 kb_entry_blobs」
  才是活库唯一无手术的路；交接文档旧计划「新卡键=entry id 写 Blob 表」作废
- **共享测试库 id 冲突**（刀2c ① 再踩）：`db.get` 按 PK 不分用户——备份恢复测试
  清源/改包内 id 模拟新机；跨类共跑时计数断言别用全表 count（捞别家行假红）
- **手录默认装载**：表单只有一句文本，payload 为空时 service 按概念补默认槽位
  （手法→scene 日常/文笔→rule/文风→sample/世界→extra/角色→archetype），否则校验必炸
- **kapsule 双层调用**：`ForceGraph()(el)` 先配置层拿装配函数再传 DOM；单层调用把 el
  当 config 吞掉、永不 append canvas，且 tsc cast＋单测双层 mock 全是假绿——真机插桩
  `built:canvas=0` 实锤
- **force-graph val=面积系数**：val 3~7 → r≈2px 不可见；题材 40/格子随计数封顶 40/
  条目 8＋graphData 后 `zoomToFit(400, 60)`；节点可见性必须真机截图验证
- **commit 后属性过期**：expire_on_commit=False 下只读对象过 commit/rollback 无恙；
  判例真因＝server_default 列（created_at/updated_at）插后未载，`await db.refresh(e)` 收口
- **CI 口径**：ruff==0.16.3 `--extend-select F811,F821,F841 .`（**全仓扫**含 main.py；
  函数内 import 排序也会红）；前端覆盖率契约（src/coverage-contract.ts）perFile 100
  ＋目录完整性——新页面/组件必须入约并补测试
- ~~「Python 用 Optional[X]」~~ **作废**：target py312，ruff UP045 强制 `X | None`
- 管道吞退出码：`pytest | tail` 的 0 是 tail 的；用 `; echo EXIT=$?` 或落文件
- vite 后台起服务别接 `| head`；探活用 `localhost`（IPv6 绑定）

## 余账（按序，下一件是二阶段）

### 刀2c ①（2026-11-01 已落，parity 全套原样跑绿＋4 回归钉）
`library/service.py` 读写从 CharacterLibrary 切 kb_entries，全部完成：
- 读侧 `payload_to_card` 单源映射，API 卡形状逐键不变（嵌套 src/avatar 在
  `_card_view` 包回；updated_at＝entry.updated_at）；列表＝全部 active 角色设定条目
- 写侧 `card_to_payload`＋kb create/update/delete_entry（闸门/payload 校验/标签
  物化/rev 复用）；update_entry 扩 genre（同步 concept_id）/src_novel_name 可选参
- **头像（FK 实证修订，boss 未及拍板按推荐落地、可翻案）**：新字节住新表
  kb_entry_blobs（Blob 表真 FK 挡 entry id 键，sqlite 实证）；迁移存量经 src_key
  回联读；删卡双清；备份往返带字节（kb/entry-avatars/*.webp＋yaml 元数据）
- 软删卡重新收录＝同键复活（置回 active＋update_entry 整卡覆盖）
- parity：test_character_library.py 全套零改动跑绿；新增
  tests/test_kb_character_adapter.py 4 钉（FK/回联/双清复活/备份往返）；
  test_library_avatar_gen.py 特性测试随存储演进改播种（同 id 双播 CharacterLibrary
  供 prompt builder 直测＋KbEntry 供端点）与断言目标表（行为断言全保留）
- 判据：前端 6 组件零改动（无前端 diff）
- 已知可接受行为差：空卡（无 persona 无 name）从可存变 400（指令闸）；空字符串格
  落 payload 时省略（读侧 falsy 等价）；拆书 collect-to-kb 的 character:N 条目与
  to-library 名字键并存于同一列表（二阶段 AI 整理去重）

### 刀2c ②③（2026-11-01 已落）
**② 消费面走查**（全过，零代码改动）：
- kb 快照：`build_members` 对角色/手法无落点直接跳过——新卡进 kb 后即便启用角色库
  也落 0 条，system 快照零污染 ✓
- 建卡预填：`kbPrototype.ts` 对任意角色设定 payload 生效（archetype→persona 句＋
  dossier/cog 白名单格）——收录/拆书新卡自动成为可选原型，特性增强 ✓
- 主表停写 sweep：生产写路径只剩 `backup/importer.py` 恢复段（设计内 legacy 兼容）✓

**③ 头像字节搬迁**（`kb/blob_migration.py`＋main.lifespan boot 挂钩；**data-smoke 真栈已验**：
legacy 卡＋字节 → 迁移端点镜像 → 重启 boot 日志 `migrated=2 removed=2`、legacy 0 行、
新表 2 行、字节照读；data-smoke 里留了一张带头像的迁移卡 smokelib 可复用）：
- boot 一次性迁移：CharacterLibraryBlob → kb_entry_blobs（src_key 回联 entry id）；
  幂等（(entry_id,variant) 已在跳过）；同键多用户（同备份恢复到两账号）各自补齐；
  搬成功的旧行删除（省双份存储）；孤儿行（父卡在、条目不在）保留走 union 读兜底
- 失败不挡启动（照 import backfill 先例，下次启动重试）；无 legacy 行时 O(1) 探测即返
- 回归钉：test_kb_blob_migration.py（搬运/幂等/孤儿/多用户同键）

### 二阶段（已拍板挂账）
AI 整理（关系/合并/纠偏，kb_relations 写入口＋全局图关系边）；写法块选择器+注入
（kb_match_runs 消费链，delta 草案在 drafts/c-kb-write-block/）。

### 小账
- 节点圆视觉打磨（半径/配色饱和度）可再调；真机待复验：设定面板来源行
  （KbSourceStrip 启用/同步/解绑真栈走查，本轮只验了知识库页）
- OpenDesign 原型 v29 后的改动未推送（守护进程停了）

## 设计文档（权威，不要重写）

| 文档 | 路径 |
|---|---|
| 整体方案 | `docs/design-c/drafts/ai-novel-c端-写作知识库-整体方案.md` |
| 选型 | `docs/design-c/drafts/ai-novel-c端-知识星图-选型.md` |
| 数据结构 | `docs/design-c/drafts/ai-novel-c端-写作知识库-数据结构.md` |
| 原型 | `docs/design-c/drafts/ai-novel-c端-写作知识库-原型.html`（v29） |
| 实施计划 | `openspec/changes/c-knowledge-base/roadmap.md`（批3-6 已勾选） |
| 适配器裁定 | `drafts/c-kb-character/specs-adapter-note.md` |

## 验证口径（每笔提交前全跑）

```bash
cd client/backend && .venv/bin/python -m pytest tests/ -q --ignore=tests/e2e   # ~4.5min，2661+
.venv/bin/python -m ruff check --extend-select F811,F821,F841 .                 # 全仓
cd ../frontend && npx tsc --noEmit && npm run coverage                          # 全量+契约阈值
node scripts/check-inline-colors.mjs src                                        # 内联色闸
```
CI：client-backend-ci（Lint＋test）/ client-frontend-ci（licenses/tsc/vitest --coverage/build）。
openspec validate c-knowledge-base 绿；归档照「实现 PR 合入前 sync delta＋移档」规矩。
