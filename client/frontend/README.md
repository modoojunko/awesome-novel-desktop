# C端 前端 — Awesome Novel 桌面应用 UI

基于 Next.js 的 React SPA，封装在 pywebview 窗口中运行。

## 技术栈

| 项 | 选型 |
|----|------|
| 框架 | Next.js (React) |
| 样式 | Tailwind CSS + daisyUI |
| 语言 | TypeScript |
| 包管理 | npm |

## 开发

```bash
cd client/frontend
npm install
npm run dev
# 访问 http://localhost:3000
```

## 构建

```bash
npm run build
# 产物输出到 .next/
```

## 测试

```bash
# 类型检查
npx tsc --noEmit

# E2E 测试（需要 Docker :80 运行）
npx playwright test
```

## 目录结构

```
client/frontend/
├── src/
│   ├── app/          页面路由
│   ├── components/   可复用组件
│   ├── hooks/        组合式逻辑
│   └── lib/          工具函数
├── public/           静态资源
├── e2e/              Playwright E2E 测试
└── package.json
```

> 注意：C端 为桌面应用，生产环境通过 PyInstaller 打包为 exe，前端构建产物嵌入其中。
