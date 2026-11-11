# 原型截图（c-deconstruct-compliance-guard 批 A）

## 改了什么

- `docs/design-c/drafts/ai-novel-c端-拆书.html`
  - 创建页：拆书使用承诺卡（已签署/未签署双态）＋「阅读并签署」弹窗＋来源类型/作者行
  - 完成详情：签署状态行（已签署/待同步/待登录/本机签署四态演示）
  - 出口弹窗：建书确认勾选、同名 warn、未存证时导出软门提示、承诺未存证时弹窗内阻塞出口
- `docs/design-c/drafts/ai-novel-c端-拆书监控-原型.html`
  - 运行态详情页头加「承诺已签 · v1」静态胶囊（快照非交互，不演示四态）

## 截图

| 文件 | 展示内容 |
|---|---|
| `create-signed.png` | 创建页已签署态：承诺卡、来源类型/作者、创建按钮可用 |
| `create-unsigned.png` | 创建页未签署态：未签署胶囊、阅读并签署、创建按钮禁用＋就近提示 |
| `consent-modal.png` | 签署弹窗：承诺全文三项＋同意勾选（未勾时提交禁用） |
| `done-signed.png` | 完成详情：已签署状态行＋四态切换 chips |
| `exit-build-blocked.png` | 待同步时建书：确认勾选与同名 warn，开始建书禁用，弹窗内「重试同步」 |
| `exit-build-login.png` | 待登录时建书：弹窗内「去登录」出口 |
| `exit-build-ready.png` | 已签署＋已勾确认：开始建书可用 |
| `exit-export-softgate.png` | 导出软门：「本机导出，承诺未取得服务端存证」 |

## parity 判定

拆书屏不在 `docs/design-c/prototypes/` 的像素 parity 基线内（该基线只覆盖
list/book/settings 等屏），因此 `prototypes/ADJUSTMENTS.md` 不新增条目；
`npm run design:check` 的 parity 场景不受本次原型改动影响。实现侧按
`docs/ux/design-language.html` §5/§6/§13 使用既有 notice、pill、checkbox 与按钮词汇，
不新增组件形态与语气档。

## 复现

截图由 Playwright 打开本地 HTML、按 `STATE` 切换器与组件交互后抓取（1440×1100，
fullPage；抓取时隐藏页面集导航与状态栏）。脚本不入库，按上表逐态点击即可复现。
