# 「爱小说」品牌口径更新评审稿（awesome-novel-agent 5.0 代际落位）

> 供品牌设计师评审。背景拍板：**爱小说对外一直宣传的是 awesome-novel-agent 的 5.0 版本**——新产品是旧开源写作工具 awesome-novel-agent（宣传名 Awesome Novel，VERSION v4.28.0）的第 5 代；本稿回答「哪些文案要更新、怎么改、什么不能动」。
> 2026-10-02 · 事实全部实勘自当前仓库；品牌策略结论出自 Brand Guardian 评审，关键新发现已二次复核。

## 一、实勘底座（先看事实）

| 事实 | 现状 | 与「5.0 血统」口径的关系 |
|---|---|---|
| 旧项目 | github.com/modoojunko/awesome-novel-agent，宣传名 **awesome-novel**，v4.28.0，宣传页口号「人铸灵魂，AI行笔墨」 | 血统来源；口号已原样继承 ✅ |
| 官网域名 | www.awesomenovel.com | 与 awesome 血统一致 ✅ |
| C 端落地页 | `LandingPage.tsx:36` 已露出 **AWESOME-NOVEL**（被 `landingPage.test.tsx:35` 钉死） | **三处已自发倒向 Awesome，只有 brand.json 停在 AI Novel** |
| 品牌单源 | `brand/brand.json`：name=爱小说，nameEn=**AI Novel**，tagline=AI 辅助长篇小说写作 | 无任何血统/代际表述 ❌ |
| C 端后端镜像 | `client/backend/brand.py:19` nameEn=「AI Novel」，`test_brand.py` 有防漂移断言 | 改名须同批 |
| S 端 landing | Hero pill「AI 辅助长篇小说写作平台」；页脚「© 2026 星纬（海口）投资有限公司 · 爱小说 · AI Novel」（e2e 钉死 `landing.spec.ts:153`）；Hero 主句被 `landing.spec.ts:9` **和** `live/smoke.spec.ts:23` 双重钉死 | 代际宣示零露出 ❌ |
| 官网 title | 「爱小说 · AI Novel」 | 同上 |
| 版本双轨 | 安装包/应用内 **semver v0.25.x**；营销代际 **5.0** | 两套数字并存，无消歧规则 ⚠️ |
| README 两份 | 头「# AI Novel · 爱小说」；clone 地址指向 **awesome-novel-desktop**（注意：与血统仓 awesome-novel-agent 是两个仓库） | 血统宣示缺位；血统链接勿指错仓 |
| 产品形态差异 | 旧项目 AGPL 开源社区产品；新产品闭源商业软件（EULA/激活码/套餐制） | 血统措辞有法律与社区观感红线 |

## 二、命名架构裁定（建议采纳）

**三层结构 + 一条全称串场线：**

| 层 | 名字 | 使用场合 |
|---|---|---|
| 中文主名 | **爱小说** | 一切中文场合第一顺位（窗口标题、页脚、商店名） |
| 英文副名 | **Awesome Novel**（取代 AI Novel） | 组合名「爱小说 Awesome Novel」：官网 title、页脚、README 头、EULA 产品名 |
| 代际徽标 | **5.0 全新一代** | Hero pill、下载页、公告、README 徽章；随 6.0 演进，**永不进 brand.json** |
| 血统全称 | **awesome-novel-agent** | 仅关于页/README/公告的血统句：「源自开源项目 awesome-novel-agent」 |

全称串场（对外第一次提及时）：**「爱小说 Awesome Novel 5.0 —— 源自开源写作工具 awesome-novel-agent 的第 5 代」**。

**副名为何必须换**：域名锁死 awesomenovel.com、C 端已上线 AWESOME-NOVEL、旧社区认知在 Awesome——三个资产全在 Awesome 一侧；「AI Novel」是品类描述词，显著性与检索辨识度都弱。换名是资产承接，不是改名。

## 三、逐表面更新清单

| # | 露出面 | 裁定 | 改成什么 | 优先级 | 风险与联动 |
|---|---|---|---|---|---|
| 1 | `brand/brand.json` nameEn | **改** | `"nameEn": "Awesome Novel"`；tagline 不动（代际不进单源） | **P0** | 四处同批：`brand.py` `_DEFAULTS`＋`test_brand.py`＋#4 页脚 e2e＋#9 README。漏一处即构建/测试红 |
| 2 | S 端 Hero pill | **改** | 「awesome-novel 全新一代 · AI 辅助长篇小说写作平台」 | **P0** | e2e 未钉 pill，无测试风险；代际第一露出位 |
| 3 | S 端 Hero 副句下 | **增补（不改原句）** | 血统行：「开源写作工具 awesome-novel 的第 5 代，理念与六阶段工作流一脉相承。」 | **P0** | 主句「人铸灵魂」被两处 e2e 钉死，**主句一个字不动** |
| 4 | S 端页脚组合名 | **改（与 #1 同批）** | 「… · 爱小说 · Awesome Novel」 | **P1** | e2e `landing.spec.ts:153` 正则含「AI Novel」，**测试与文案必须同批改** |
| 5 | 官网 title | **改** | 「爱小说 Awesome Novel — AI 辅助长篇小说写作平台」（品类词降级为 SEO 位） | **P1** | 无钉死测试 |
| 6 | README 两份头部 | **改** | 「# 爱小说 · Awesome Novel」＋徽章行「awesome-novel-agent 第 5 代 · 源自开源项目（链旧仓库）」 | **P0** | 血统链接指 `awesome-novel-agent`，**勿指 clone 地址的 awesome-novel-desktop** |
| 7 | `site-config.json` brandName | **不改** | 保持空串（空＝单源纪律） | 不动 | 填值会制造第二事实源 |
| 8 | 安装包名 AI_Novel_Setup_* | **缓改** | 随下一个正式大版本切 `Awesome_Novel_*`，旧链接保留一个版本周期 | **P2** | 外发链接/渠道换发成本高，现在不动 |
| 9 | 数据目录 `%APPDATA%\AI Novel` 等 | **不改** | 用户资产路径，工程代号 ≠ 品牌文案 | 不动 | — |
| 10 | C 端 AWESOME-NOVEL | **不改** | 与新口径天然一致，是 #1 的佐证 | 不动 | 已被测试钉死 |
| 11 | EULA/关于页产品名 | **待核对** | 若写「AI Novel」随 #1 批次统一为「爱小说 Awesome Novel」 | **P1** | 法务确认是否触发 EULA 重新同意；评审时未实勘 EULA 文本 |
| 12 | `docs/marketing/c-sellpoints.md` | **微调** | 文首增补代际口径一行：「对外统一称第 5 代/5.0 代际；桌面 semver（v0.25.x）只出现在下载与更新场景」 | **P1** | 内部文档，零风险 |
| 13 | `docs/marketing/s-landing-copy.md` | **落地时套规则** | Hero 加血统行；FAQ 增「爱小说和 awesome-novel 是什么关系？」；全篇禁「v5.0」 | **P1** | 该文件现存放于 `feat/tier-plan-four-tiers`（abcea86d），落地时套用 |

## 四、两套版本数字的消歧铁律

1. **数字永远带限定词**：营销代际必须绑「代」（第 5 代 / 5.0 代际 / 全新一代）；工程 semver 必须绑「版」（桌面版 v0.25 / 0.25.x）。裸写「5.0」「0.25」都算违规。
2. **同屏共现括号隔离、主从分明**：`爱小说 Awesome Novel 5.0（桌面版 v0.25）`；下载场景反过来只写工程版：「桌面版 v0.25 · Windows / macOS」。
3. **禁止伪造 semver**：不写「v5.0.0」——实际更新通道是 0.25.x，穿帮只需一条更新日志。

可直接采用：
- 关于页：「当前代际：5.0 ｜ 桌面版本：v0.25.x（见更新日志）」
- FAQ：「5.0 是产品代际，表示这是 awesome-novel 之后的第五代；安装包上的 v0.25 是桌面软件的工程版本号，两者各自独立演进。」
- 公告标题模板：「爱小说 Awesome Novel 5.0 代际更新 · 桌面版 v0.26 发布」

## 五、血统宣示：能用的词与红线

**能用**：第 5 代 / 5.0 代际 / 全新一代 / 升级之作 / 源自 awesome-novel / 一脉相承（限理念与工作流层面）。

**禁用及原因**：

| 措辞 | 坑 |
|---|---|
| 「开源 5.0」「5.0 开源版」 | 新产品闭源商业软件，构成开源暗示，AGPL 社区观感风险最高 |
| 「免费升级」 | 与套餐制冲突，构成事实承诺（除非商务另行拍板迁移政策） |
| 「取代/替代 awesome-novel」 | 旧项目未声明停更，改「并行表述」：开源版仍按 AGPL 独立存在 |
| 「v5.0.0」 | 伪 semver（见第四节） |
| 「awesome-novel」裸用不链旧仓库 | 易被读成「拿社区成果闭源变现」；血统句永远带旧仓库链接 |

**三条可直用的宣传句**：
1. 官网 Hero pill：「awesome-novel 全新一代 · AI 辅助长篇小说写作平台」
2. 血统主句（Hero/理念区/README 徽章通用）：「爱小说，开源写作工具 awesome-novel-agent 的第 5 代——人铸灵魂，AI 行笔墨，一脉相承。」
3. 迁移公告（旧 QQ 群/旧仓库用户）：「写给 awesome-novel 的老用户：你们熟悉的六阶段工作流，在爱小说里长成了第 5 代。开源版仍按 AGPL 独立存在，你的旧稿随时可以导入续写。」（「导入续写」已上线有支撑；**不承诺**旧项目工程数据迁移——「拆书成设定」还待立项，写了就是空头支票）

## 六、不建议动的清单

1. 法定主体「星纬（海口）投资有限公司」＋两枚备案号——一字不动。
2. Hero 主句「人铸灵魂，AI 行笔墨」——被 `landing.spec.ts` 与 `live/smoke.spec.ts` 双重钉死；不同批改测试就一行别碰。
3. 数据目录路径、窗口标题「爱小说」、`site-config.json` brandName 空值、域名与旧仓库名——只增不改。
4. brand.json 的 `tagline`——代际语义由 pill 承担，不塞进单源。

## 七、落地批次建议

- **P0 一批**：brand.json＋brand.py＋test_brand.py＋README 两份＋Hero pill/血统行（均无 e2e 钉死文本）。
- **P1 一批**：页脚组合名＋`landing.spec.ts:153` 正则（同批！）＋官网 title＋EULA 核对＋c-sellpoints/s-landing-copy 口径段。
- **P2 观望**：安装包名随正式大版本；路线图条目不带版本数字。

## 附：评审过程勘误

- 本稿评审时 `s-landing-copy.md` 与 landing 组件改动曾被并行会话从共享检出的工作树收编，**未丢失**：现随提交 `abcea86d` 存于分支 `feat/tier-plan-four-tiers`（含全部 landing 文案组件改动）。落地品牌更新时须以该分支为基或等其合入。
- C 端落地页 `AWESOME-NOVEL`（LandingPage.tsx:36）、`brand.py` nameEn、smoke.spec 对主句的钉死、README clone 指向 awesome-novel-desktop——四项均为本次评审新发现并已二次复核。
