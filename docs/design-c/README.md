# C端 设计资产目录（design-c）

> **本目录不含任何"标准"。** 设计标准的唯一权威在 [`../ux/`](../ux/)：
> 规范正文 [`design-language.html`](../ux/design-language.html) ·
> 全端一致性裁决 [`cross-end.html`](../ux/cross-end.html)；
> 机器可读的强制层是两端各自的 `scripts/design-vocab.mjs`（禁令同源，与标准同批修改）。

本目录只承载被门禁机器消费的**运行资产**。版本管理分层（2026-08-28 起）：
`prototypes/`（视觉真值 + ADJUSTMENTS 登记簿）**入库**，fresh clone 即可跑 parity；
`baselines/`（比对 PNG）与 `prototypes/assets/`（v1 编译残留）仍按 `.gitignore` 保持本地。

## 目录

```
docs/design-c/
├── README.md      本 runbook（只讲怎么跑；讲"长什么样"去 ../ux）
├── pages/         现行页面集（opendesign 产物）：每页一个自包含 HTML＋components 组件库，
│                  页间 hash 链接互跳、无后端调用；随实现演进而更新
├── prototypes/    视觉真值：index / list / book / model-config 自包含 HTML（oklch、无外部依赖）
│   ├── ADJUSTMENTS.md   基线偏差登记簿（原型即基线：先改原型并登记，再改实现）
│   ├── CLAUDE.md        原型交付约定
│   └── assets/          v1 tailwind 编译残留，v2 原型不再引用
├── drafts/        已清空（2026-09-26）：设计稿对应功能全部实现，两批清出至 docs/archive/
└── baselines/     design:check 的 proto/app/diff 三联图（排障用）

已实现设计稿归档：docs/archive/design-c-drafts-2026-09-25/ 与 -2026-09-26/
（git 跟踪件在 git 历史；未跟踪件与过程文档原件在各批目录）。
```

## 命令（都在 client/frontend 下）

```bash
npm run design:lint     # 白名单校验：词表档位/任意值登记簿/裸色/emoji/daisyUI 回归
npm run design:check    # lint + DESIGN_PARITY=1 Playwright 双开像素比对，阈值 <0.2%
```

前置：应用栈在跑、原型文件存在。diff 图落 `baselines/`。
（v1 的 `design:css` 同源编译已随 daisyUI 换装退役——现行原型自包含，无可编译的外部样式。）

## 变更流程

改 `prototypes/*.html` → 在 `prototypes/ADJUSTMENTS.md` 登记每处偏差原因 →
改实现对齐原型 → `design:check` 全绿（<0.2%）。
要动"标准"本身（令牌档位 / 组件词汇 / 语气词表 / 文案口径）时，
改 `../ux/` 的规范正文并两端同批更新 `design-vocab.mjs`，不要在本目录改。

## 历史

v1 词汇表 `DESIGN.md`（daisyUI 双主题 / lucide 口径）与 v1 屏规格 `specs/01-novel-list.md`
已随 #181~#187 换装失效，整体归档于 `../archive/design-c-v1/`，仅作考古用。
