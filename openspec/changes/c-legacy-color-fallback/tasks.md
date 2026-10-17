# tasks — c-legacy-color-fallback

> 现场：v0.34.4，Windows 11，WebView2 108.0.1462.46；窗口正常装载、后端正常、浏览器兜底未触发；页面白底黑字。目标：不改现有编译产物、不要求用户任何操作。

## 1. 生成器

- [x] 1.1 `scripts/gen-legacy-colors.mjs`：解析构建产物 CSS，完整复制；每个 `oklch()`/`color-mix()` 求值为 `rgb()/rgba()`，声明值改写为 `var(--lgc-N)`；验证＝单测 + 真实产物生成
- [x] 1.2 颜色数学：oklch↔sRGB、color-mix 预乘 alpha（oklch 与 srgb 两个空间）、短弧色相；**不透明无彩色按 hue=0 参与插值**（Chromium 实测校正）；验证＝Chromium 对拍 798 项 0 差异
- [x] 1.3 主题展开：默认主题 + 5 套 `data-theme`；仅值变化时出覆写；验证＝单测（accent 表达式有主题覆写、fg 表达式无覆写）
- [x] 1.4 结构对拍闸门：规则/选择器/声明顺序/`!important` 逐节点比对；声明值必须等于「原值 → `var(--lgc-N)`」；验证＝生成器内建，失败即构建红
- [x] 1.5 残留与可解性闸门：成品声明不得含颜色函数；未知变量/变量循环/非 oklch·srgb 空间/at-rule 参数内颜色函数一律抛错；验证＝单测（未知变量报错）

## 2. 构建接线

- [x] 2.1 `package.json`：`build` 末尾执行生成器；新增 `design:legacy` 手动入口；验证＝`npm run build` 绿
- [x] 2.2 `index.html` 条件加载：原样式表之后注入同步脚本，仅当 `CSS.supports('color','oklch(…)')` 或 `color-mix(in oklch,…)` 不支持时 `document.write` 加载兼容表；验证＝Chromium 模拟 `CSS.supports=false` 出现 1 个链接、默认 0 个
- [x] 2.3 幂等：排除自身注入的 legacy 链接，二次生成产物字节一致；验证＝单测 + 真实 dist 连跑两次哈希一致
- [x] 2.4 原 CSS 零改动：生成前后哈希一致；验证＝真实 dist 哈希对拍

## 3. 测试

- [x] 3.1 `scripts/gen-legacy-colors.test.mjs`：14 条（极值色、alpha 混色、srgb 混色、无彩色色相行为钉、多函数替换、结构保真、媒体查询/关键帧、`!important`、主题覆写、令牌编译、未知变量、落盘幂等）；验证＝全绿
- [x] 3.2 `vitest.config.ts` 纳入 `scripts/**/*.test.mjs`；验证＝全量 `npx vitest run` 133 文件 / 1684 用例全绿
- [x] 3.3 产物级验证：`dist/legacy-colors.css` 声明中 `oklch(`/`color-mix(` 计数为 0；`index.html` 恰好 1 处 legacy 引用；验证＝命令输出

## 4. 规格与文档

- [x] 4.1 openspec change：proposal/design/tasks + `design-system` 规格增量（ADDED「旧内核颜色兼容层」四场景）
- [x] 4.2 说明源文件规范不变：`design-system` 既有「oklch token / color-mix 派生、源文件禁止裸 hex/rgb」保持；兼容表为构建产物

## 5. 回归与交付

- [x] 5.1 全量前端单测 + design:lint；验证＝1684/1684，lint 无新增违规
- [ ] 5.2 PR 评审（未推送；本地分支 `c-legacy-color-fallback`）
- [ ] 5.3 发版后真机复验：同一台 108 机器（或强制旧内核）页面颜色恢复正常，`dist/index.html` 加载 legacy 表
