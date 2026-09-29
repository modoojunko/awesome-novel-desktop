# works-finish-flow Specification

## Purpose
书的完本与撤完本能力（works-finish-flow）：把「写完」与「完结」分开——全归档只是待完本，
完本是一个显式动作（finished_at 落库），完结后仍可撤回继续写。覆盖完结状态落库与
finish/reopen 端点、书架四态徽章与分状态页脚、待完本提示条、完本清单弹窗（伏笔留白
辅助确认）与撤完本入口；阶段判据与落点单源见 novel-workspace 的 view machine 条目。书架屏
自身的垂直节奏（works.html 口径的屏级间距）亦属本能力。

## Requirements

### Requirement: 完结状态落库与 finish/reopen 端点

- `novels` 表 SHALL 增加可空列 `finished_at`（TIMESTAMP）：完本动作写入服务端当前时间，撤完本清空；此外 SHALL NOT 有任何路径写该列。迁移 SHALL 走 `main.py` lifespan 既有「列存在检查→ALTER TABLE ADD COLUMN」守卫模式，无回填、无兼容层。
- `POST /api/novels/{project_id}/finish` SHALL 在满足全部守卫时写入 `finished_at` 并在响应中返回更新后的书摘要（含 `finished_at`）；守卫任一不满足 SHALL 返回 409：**未完结**、**主线章数 > 0**、**主线已归档章数 == 主线章数**（主线口径与书架统计同源：`chapters.ghost_of` 为空才算主线）。
- `POST /api/novels/{project_id}/reopen` SHALL 仅在**已完结**时清空 `finished_at` 并返回更新后的书摘要，否则 SHALL 返回 409。
- `GET /api/novels`（list）与书详情端点 SHALL 下发 `finished_at`（ISO 字符串或 null）。
- 完结与撤完本 SHALL 触发 `updated_at` 常规更新（书架排序口径不变）。

#### Scenario: 主线全归档后完本成功

- **WHEN** 对一本主线 3 章且 3 章全部归档、未完结的书调用 finish
- **THEN** `finished_at` 写入当前时间，响应含该时间戳；list 下发同一值
- **AND** 再调 finish SHALL 返回 409（已完结）

#### Scenario: 有未归档主线章时拒绝完本

- **WHEN** 对一本主线 5 章仅归档 3 章的书调用 finish（旧稿支线章不计入）
- **THEN** 返回 409，`finished_at` 保持为空

#### Scenario: 撤完本回待完本

- **WHEN** 对一本已完结的书调用 reopen
- **THEN** `finished_at` 清空，list 中该书 `finished_at` 为 null
- **AND** 对未完结的书调用 reopen SHALL 返回 409

### Requirement: 书架卡片四态徽章与分状态页脚

- 书架卡片阶段徽章 SHALL 呈现四态（单源 `lib/novelStage.ts`）：`setting`＝设定中、`writing`＝写作中、`ready`＝**待完本**（accent 底）、`done`＝**已完结**（ok 底）；「已归档」标签 SHALL 退役。判据：`finished_at` 非空→已完结；主线章数 ≤0→设定中；主线全归档未完结→待完本；其余→写作中。
- 卡片页脚 SHALL 分状态呈现：
  - **待完本**：「全书 N 章已归档」＋`回看`（secondary sm，落预览视图）＋`完本`（primary sm，打开完本清单弹窗）；
  - **已完结**：「完结于 X」（相对时间口径与「更新于」一致）＋`查看`（落预览视图）；
  - **写作中/设定中**：「更新于 X」＋`继续创作`（现状不变）。
- 卡片本体点击落点 SHALL 与标签同结论：待完本落写作视图；已完结落预览视图（现状口径）；其余不变。
- ⋯ 菜单（重命名/删除）对四态书 SHALL 均可用；已完结书 SHALL 增「完本信息 · 撤完本」项，点击打开完本清单弹窗（已完结态）。

#### Scenario: 全归档未完结书呈现待完本

- **WHEN** 书架上一本书主线章全部归档且 `finished_at` 为空
- **THEN** 徽章为「待完本」，页脚为「全书 N 章已归档」＋`回看`＋`完本`，卡片点击落写作视图

#### Scenario: 已完结书呈现完结页脚

- **WHEN** 一本书 `finished_at` 非空
- **THEN** 徽章为「已完结」，页脚为「完结于 X」＋`查看`，⋯ 菜单含「完本信息 · 撤完本」

#### Scenario: 待完本卡回看落预览

- **WHEN** 在待完本书卡片页脚点「回看」
- **THEN** 打开该书且落预览视图（一次性落点覆盖，刷新或再次进入不受影响）

### Requirement: 待完本提示条

- 书架页 SHALL 在存在待完本书时、于页头下方显示提示条（`notice info` 语气）：「《书名》主线已收齐 · N 章全部归档 · 可以完本了」，附 `去完本`（打开该书完本清单弹窗）与 `知道了`（关闭）。
- `知道了` SHALL 为会话内记忆（页面挂载期内不再重现），SHALL NOT 持久化；多条待完本书时 SHALL 只提示排序最前的一条，完结或关闭后可提示下一条。

#### Scenario: 待完本提示条出现与关闭

- **WHEN** 书架存在待完本书
- **THEN** 显示提示条；点「知道了」后本轮不再显示；完结该书后提示条消失

### Requirement: 完本清单弹窗

- 完本清单弹窗 SHALL 基于 `design/Modal` 宽卡，含两态：
  - **待完本态**：标题「完结《书名》？」＋ lead（主线 N 章 · M 卷 · 约 K 字都已归档）＋三行检查：
    1. 「章节已全部归档」——ok 形态（判据与端点守卫同源）；
    2. 伏笔行——`hooksApi.list` 过滤 `status=active`：无 active 伏笔→ok 形态「伏笔都已回收」；有→warn 形态「还有 N 条伏笔悬着」，逐行列出名称＋「第 X 章埋下」，每行可切换 `留白/未收` 标记（**仅弹窗内辅助确认，SHALL NOT 写回伏笔表**；弹窗重开重置）；
    3. 「归档收尾都已清」——静态 ok 形态，描述引导书内「设定 / 伏笔」页签逐条确认收尾提案。
  - 底部 SHALL 为 `再想想`（关闭）＋`完结这本书`（primary，调 finish 端点）；409 SHALL 以 toast 呈现守卫原因且不关闭弹窗。
  - **已完结态**：完结信息（主线 N 章 · M 卷 · 约 K 字 · 完结于 X）＋`撤完本 · 继续写`（secondary，调 reopen 端点，成功后卡片回到待完本/写作中）＋`关闭`。
- 完结成功 SHALL 更新本地书状态（响应的 `finished_at`）并 toast「《书名》已完结 · 归档收尾提案可在「设定 / 伏笔」页签逐条确认」；文案 SHALL NOT 提及不存在的后台任务。

#### Scenario: 完本清单呈现未回收伏笔并可标记留白

- **WHEN** 打开一本含 2 条 active 伏笔书的完本清单弹窗
- **THEN** 伏笔行为 warn 形态并列出 2 条（名称＋埋下章），点某行「留白」后该行标记切换为「留白」，伏笔表数据不变

#### Scenario: 完结成功卡片转已完结

- **WHEN** 在弹窗点「完结这本书」且端点成功
- **THEN** 弹窗关闭、toast 呈现、该书卡片徽章转「已完结」、页脚转「完结于 X」、待完本提示条消失

#### Scenario: 撤完本回到待完本

- **WHEN** 在已完结态弹窗点「撤完本 · 继续写」且端点成功
- **THEN** 弹窗关闭、该书卡片回到「待完本」（若已有未归档章则「写作中」）

### Requirement: 书架屏垂直节奏（works.html 口径）

书架屏（/novels） SHALL 采用区别于全局壳的屏级垂直节奏（设计真值 `docs/design-c/drafts/works.html`，2026-09-19 实测差异来源）：

- 主区（main）顶距 SHALL 为 40px（全局基线 48px）；
- 页头（page-head）下缘距 SHALL 为 26px（全局基线 36px）；
- 页头副题（.sub）SHALL 无下缘距（全局基线 1em，系旧原型未重置 UA 默认 `p` margin 的显式复刻）；
- 窄屏（≤480px）断点同步：主区 padding 顶距 28px（基线 32px）、页头 gap 14px（基线 16px）、页头下缘距 22px（基线 28px）。

实现 SHALL 以屏级作用域落笔（沿 model-config 屏级节奏先例），SHALL NOT 修改 base.css 全局壳——其余屏（书内工作台、模型配置等）与其各自原型的既有节奏 SHALL 保持不变。parity 基线 `prototypes/list.html` SHALL 与实现同批采用同值，并 SHALL 在 ADJUSTMENTS.md 登记（design-system「Prototype-first flow」既有约束）。

#### Scenario: 桌面视口与 works.html 逐像素一致

- **WHEN** 以同一份四态书数据分别渲染 works.html 原型与应用书架屏（1440×900）
- **THEN** 页头、待完本提示条与卡片栅格的垂直位置一致（卡片栅格顶部较改前上移 31px），`design:check` books/empty/quota/finish 四场景像素差均 <0.2%

#### Scenario: 其余屏节奏不受影响

- **WHEN** 打开模型配置屏（或书内工作台）
- **THEN** 其主区/页头间距与各自原型保持一致，无视觉位移

#### Scenario: 窄屏断点同步收紧

- **WHEN** 视口宽 ≤480px 打开书架屏
- **THEN** 主区顶距 28px、页头 gap 14px、页头下缘距 22px，与 works.html 窄屏断点一致
