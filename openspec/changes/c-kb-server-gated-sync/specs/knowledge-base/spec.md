## MODIFIED Requirements

### Requirement: 知识编辑器与种子

知识 SHALL 从两条通道进入：**知识编辑器**（新建/修改共用：知识名、分类＝题材＋类别、
知识定义、实例（可多条，每条含实例文本＋出处＋原文摘句）、其他字段（状态/别名））与种子
（题材目录随包内置；**概念树 SHALL NOT 随包内置——知识树是 S 端签名的私有 COS 数据**，
C 端经 `POST /api/kb/sign` 的 `tree_pointer`/`tree_data` 换短时 URL 同步到本地缓存后由
加载器只读消费，包内 SHALL 零 taxonomy 文件）。知识名、题材、类别、知识定义 SHALL 为必填；
类别 SHALL 由作家在六类注册表内选择，SHALL NOT 只靠推断入库。实例 SHALL 允许 0..N 条；
新增/修改知识时 SHALL 记录版本、创建时间与更新时间。知识关系 SHALL NOT 由作家在编辑器中
手动新建/删除（手动关联另行立项）；关系来源＝AI 整理产出＋作家逐条采纳，知识视图只读展示。
表单中 SHALL NOT 出现系统词汇（基线/场景/槽位/句末断/when_json）；面向作家的文案 SHALL
使用日常用语（"知识名""类别""知识定义""实例""出处"）。

知识树同步 SHALL 满足：S 端 `tree_pointer`/`tree_data` 要求登录但**不占题材配额**（免费）；
指针（latest.json）Ed25519 验签（与内容仓 tree_publish 同一 legacy 三字段签名域）通过后
才消费版本/哈希/大小；下载体 SHALL 逐字节校验 sha256 与 size 并过结构闸（单根/父可解析/
slot_map 指向存在/无环）；安装 SHALL staging 原子替换、receipt 最后写、原始字节零重序列化；
版本 SHALL 只向前（低版本拒绝，同版本缓存损坏按同版本修复）；同步 SHALL 静默失败可重试、
不阻断启动；登录成功 SHALL 自动探测并在有新版时更新；`KB_TREE_SYNC=0` 关启动/登录钩。

树未同步/结构为空时系统 SHALL 表现为「树未就绪」：知识总结与知识提炼 SHALL 明确拒绝
（稳定原因 `tree_not_ready`），SHALL NOT 回落任何内置层次或硬编码根节点制造本地知识；
知识树视图 SHALL 展示用户已有知识点（排序降级）并透出未同步状态，SHALL NOT 误报为 500。

#### Scenario: 首装同步知识树

- **WHEN** 新装客户端登录后（S 端可达）
- **THEN** 树按 S 端签名 URL 下载校验后落本地缓存，知识总结/提炼可用；树版本更新静默前进

#### Scenario: 树免费不占题材次数

- **WHEN** 用户免费档今日已用完题材同步次数，知识树仍需更新
- **THEN** 树同步照常完成（tree 不检查也不扣题材配额）

#### Scenario: 树未同步时提炼

- **WHEN** 树未同步（空缓存/S 端不可达）且作家点「知识提炼」
- **THEN** 按钮禁用（UI）或任务以 `tree_not_ready` 明确失败，不产生任何本地知识结构

#### Scenario: 指针被篡改

- **WHEN** latest.json 签名/哈希/大小任一校验失败
- **THEN** 保留既有缓存不动，同步记 failed，已有树继续可用

#### Scenario: 回退保护

- **WHEN** S 端指针版本低于本地已装版本
- **THEN** 同步跳过（older_than_installed），本地较新树继续使用

#### Scenario: 新建一条知识

- **WHEN** 作家点「+ 新建知识」并填写知识名、题材、类别、知识定义后保存
- **THEN** 系统创建知识（version=1、created=updated=当前时间），并允许后续添加任意多条实例

#### Scenario: 必填项缺失

- **WHEN** 作家未填知识名、题材、类别或知识定义就保存
- **THEN** 对应字段下以作家语言提示，不保存

#### Scenario: 手录提交落素材

- **WHEN** 作家在知识库页手录一条素材并提交
- **THEN** 该行以素材态（`origin='material'`）落库，不直接进星图/选择器/写法块；总结整理后才成为知识

#### Scenario: 实例可增删

- **WHEN** 作家在编辑器里点「+ 添加实例」或移除一条实例后保存
- **THEN** 该知识下的实例按当前列表与顺序落库；知识自身 id 不变
