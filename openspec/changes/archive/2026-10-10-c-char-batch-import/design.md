# c-char-batch-import — 技术方案

## 关键决策（实现评审已定，含默认值）

1. **SheetJS 选型与引入**：registry 的 `xlsx@0.18.5` 停更且带 CVE-2023-30533 / CVE-2024-22363（攻击面＝解析用户上传文件，正中本功能）。用官方 CDN tarball `xlsx@0.20.x`（`https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz`）。**dynamic import**（`await import("xlsx")`）收在「下载模版」「解析文件」两个 handler，独立 chunk（min 约 1MB），不进主包。
2. **Excel 自动转格式防护**：解析统一 `sheet_to_json(sheet, { raw: false })` 取显示文本（"31" 就是 "31"），不设 `cellDates`；单测钉死。
3. **编码回退链**：utf-8 优先，解码出现 U+FFFD 用 `TextDecoder("gbk")` 重试一次（中文 Windows 传统 CSV＝GBK，乱码工单最大来源）。
4. **sheet 名容错**：不依赖「角色」sheet 名——遍历全部 sheet，取第一个能映射出 name 列的；都没有→报错。模版**写入**用固定 sheet 名。
5. **列头识别**：trim → 去尾部 `*` → 全角括号/间隔符归一 → 映射表（中/英键＋「别名(用·分隔)」等变体，含 `startsWith("别名")→aliases` 兜底）。首行即列头，**不做标题行嗅探**。
6. **护栏**：`accept=".xlsx,.csv"`＋扩展名白名单＋`size ≤ 10MB`＋数据行 ≤100（超限报「请分批导入」，不截断）；整行全空丢弃。
7. **建卡编排**：严格串行（顺序可预期、409 竞态最小）；409 计跳过，其他错误停批；「撤销本次全部」＝循环既有 DELETE（404 视为已撤继续；防重入旗防连点）。二级撤销不提供。
8. **草稿保留**：rows 存 CharacterManager 层 state，弹窗误触关（scrim/×/取消）直接关、重开还原；仅建卡成功才清草稿。
9. **后端扩参**：`create_character(aliases, dossier)`；校验器照 `_prefill_dossier` 纪律——dossier 白名单严格取 `DOSSIER_KEYS`、逐格 strip+[:300]、空值丢弃、非法键/非对象/非字符串值 400 `invalid_dossier`（detail 点名）；aliases list[str]→strip→空串丢→每条[:50]→前 20 条；name 补 [:50]（SQLite 不强制 String(50)）。合并 `{**prefill_dossier, **dossier}`（dossier 胜）；`PREFILL_KEYS` 不动。
10. **组件拆分**：`lib/characterImport.ts`（纯函数＋`IMPORT_FIELD_GUIDE` 常量——弹窗折叠块与模版「填写说明」sheet 同源的唯一事实源）＋`settings/BatchAddModal.tsx`（弹窗壳复用 `.scrim/.modal/.mcard` 惯例）；CharacterManager 只加按钮与编排。按钮文案「批量添加」（避开 e2e `getByRole name:"添加角色"` substring 匹配）。
11. **覆盖率契约**：新文件登记 `coverage-contract.ts`（perFile 100% 生效）；指针/文件对话框薄壳 `/* v8 ignore start */`＋不可达理由注释（仓库 17 处先例）。

## 原型迁移口径

交互基准＝`docs/design-c/drafts/ai-novel-c端-角色批量添加与拖拽排序-原型.html`（已无头浏览器验证：模版往返/示例行防呆/中英列头/停批撤销）。实施时把弹层形态移植进 `docs/design-c/prototypes/character-settings.html`（canonical parity 基线）＋`ADJUSTMENTS.md` 登记偏差，再动 `src/`。

## E2E 环境注意

遵守会话环境隔离规则（AGENTS.md）：e2e 用独立栈，不在共享检出栈上跑。
