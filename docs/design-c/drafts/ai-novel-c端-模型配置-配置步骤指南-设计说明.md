# ai-novel C端 · 模型配置「配置步骤指南」设计说明

2026-10-29 · 原型待拍板

- 原型：`ai-novel-c端-模型配置-配置步骤指南-原型.html`（自包含，浏览器直开；六态演示条在底部）
- 源稿：`ai-novel-c端-模型配置-配置步骤指南-原型.src.html`；构建 `build-modelhelp-proto.py`；自检 `check-modelhelp-proto.py`（PASS）
- 宿主抓取物：`ai-novel-c端-模型配置-配置帮助-captures/`（main 检出 vite＋副本库私有后端 8101，2026-10-29 抓取，含豆包/OpenCode Go 方块与真实配置卡数据）

## 1. 背景与目标

作家配置 API Key 时的高频卡点（本次 Gemini/OpenCode Go 实测中再次确认）：不知道去哪领 Key、不知道选哪个方块、Base URL 不知道抄到哪一截、测试连接报错不会归因。表单里虽有 Base URL 案例引导（cf-hint）与零散提示，但没有一份「从零到用上」的完整步骤说明。

拍板要求（2026-10-29）：设计一份**配置步骤帮助信息**，按 **OpenAI / Anthropic / Google 三类接口格式**组织配置步骤。

## 2. 方案总览

**一个指南弹窗＋两处入口**：

1. **指南弹窗「配置指南」**：复用应用 Modal 体系（.modal/.mcard/.mh），顶部三页签＝**OpenAI 格式｜Anthropic 格式｜Google 系**（与表单里「接口格式」切换器同名同序，降低认知成本）。每个页签内容同构：
   - **适用范围**：该格式覆盖的供应商方块 chips（逐字用方块名）＋一句定位说明；
   - **四步步骤**（编号圆＋标题＋正文）：
     1. 领 API Key —— 每家服务商的领 Key 入口地址表（OpenAI 格式页签含 8 行速查表）；
     2. 选方块、贴 Key —— 强调「地址已预填，只需贴 Key」；中转站的选块与格式切换规则；
     3. 选模型 / 填模型 id —— 清单自动拉取为主、手填 id 兜底（给示例 id）；
     4. 测试连接 —— 「连接正常」即完成；
   - **常见问题**（折叠 details）：每类 2–3 条真实高频错（401/404/清单拉不到/思考模式报错/超时），全部按「现象 → 用户能做的动作」写。
2. **入口一（列表页）**：页头「添加 API Key」左侧加「配置指南」副按钮（btn-secondary）。
3. **入口二（添加弹窗内）**：供应商方块区下方加一行 cf-hint：「不知道怎么填？看三步配置指南——领 Key → 贴 Key → 测试连接。」链接打开指南并定位到当前供应商所属页签。

## 3. 内容口径与文案纪律

- **三类的划分就是表单里的「接口格式」概念**：OpenAI 格式（含全部官方厂商方块＋OpenCode Go·通用＋OpenAI 兼容）、Anthropic 格式（Anthropic＋OpenCode Go·Claude 系＋Claude 兼容中转）、Google 系（Gemini 官方走兼容地址＝按 OpenAI 格式配；带 Gemini 的中转）。不引入「协议族」等新术语。
- **作家语汇纪律**（判例：原型文案＝产品文案）：全文无「协议/SDK/端点/探针/兼容层」等实现词汇，check 脚本黑名单钉住；错误归因全部用现象（401/404/超时/清单拉不到）＋用户动作。
- **与现有表单提示同源**：Anthropic「地址填到哪一截」FAQ 与表单 cf-hint 文案口径一致（填到域名、自动补版本段）；Gemini「关不掉思考」与表单既有提示一致。
- **诚实边界**：Google 系页签**不承诺**「OpenCode Go 订阅里的 gemini 可直连」——应用当前对 Google 原生格式不支持（10-28 实测：zen chat 口对 gemini 503、仅 google 原生口出货）；文案给的替代路径是「带 Gemini 的中转服务」，等应用内原生支持排期落地后再补。
- **有据纪律**：领 Key 地址表全部为各平台公开的常见入口（platform.deepseek.com、open.bigmodel.cn、platform.moonshot.cn、bailian.console.aliyun.com、console.volcengine.com/ark、aistudio.google.com/apikey、console.anthropic.com、platform.openai.com、opencode.ai）；**发布前需逐条人工复核一遍**（入口地址会改版）。

## 4. 交互细节

- 页签切换为纯前端切换，不关弹窗；从弹窗内入口打开时按当前已选供应商自动定位页签（DeepSeek→OpenAI 格式；Anthropic/OpenCode Go·Claude 系→Anthropic 格式；Gemini→Google 系；其余默认 OpenAI 格式）。
- **弹窗固定尺寸 880×760（拍板 2026-10-29：不做自适应——不随视口缩放、不随页签切换跳尺寸）**；内容区超高时内部滚动兜底。领 Key 速查表排两列网格（8 家 4 行），三个页签默认态均零滚动完整呈现（实测 overflow=0）；FAQ 展开后超出部分走内部滚动。高度另钳 `min(760px, calc(100vh - 48px))`：桌面最小窗（1024×680）下只缩高度走内部滚动，头部/关闭钮不裁出屏（评审 P3 整改）。
- 关闭：× 与点背景均可；指南叠在添加弹窗之上（z-index 更高），关闭指南回到添加弹窗原状，不丢已填内容。
- 不做：不做分步向导（wizard）绑架流程——指南是「随时可看的手册」，不打断配置动作；不在指南里做可点击的跳转注入（保持只读说明，实现量小、行为可预期）。

## 5. 宿主与工程落点

- 原型宿主＝真界面抓取逐字（check 脚本对拍 `dom-config-list.html`/`dom-modal-vendor.html`）；graft 全部 template＋运行时挂载，未改动任何抓取节点（页头按钮成组为运行时 wrapper）。
- 实现落点（工程化时）：
  - 新增 `components/api-config/ConfigGuideModal.tsx`（文案做成常量表，地址表数据化，便于复核与增补）；
  - `ApiKeyConfigPage.tsx` 页头加副按钮；`ApiConfigForm.tsx` 供应商 field 的 vgrid 之后加 hint 行＋open 事件（弹窗内入口，带 `data-gtab` 定位参数）；
  - 无后端改动、无路由改动；预计一个前端小 PR（含 vitest）。

## 6. 待拍板

1. 两处入口是否都要（建议：都要——列表页管「第一次来」，弹窗内管「正在配的时候」）。
2. OpenAI 格式页签的领 Key 速查表要不要加「复制地址」小钮（建议 v1 不加，保持纯文本）。
3. Google 系页签要不要提「OpenCode Go 订阅含 gemini 但应用暂不支持直连」（建议：不提，等原生支持排期落地再补一句，避免教用户折腾本地垫片）。
4. 领 Key 地址表发布前逐条复核的责任人/时机（建议随实现 PR 一起过一遍）。
