---
id: kb-0001
q: macOS 安装后提示「无法打开」怎么办？
keywords: mac, macos, 无法打开, 已损坏, 打不开, 右键, 门禁
tags: 安装与启动
capabilities: installer-release
related: ch-01
updated: 2026-10-05
---

## 答案

Apple 会拦截没有开发者公证证书的应用（独立开发者搞不起）。解决方法：

1. 在「应用程序」文件夹里**右键**点「AwesomeNovel」；
2. 点菜单里的「打开」；
3. 弹窗再点「打开」即可。

只需要第一次，以后正常打开。DMG 包里也有「首次使用.command」脚本，双击一次自动完成。

## 客服口径

- 属正常安全拦截，不是软件损坏；按上面三步即可，无需重装。
- 用户仍打不开时：收集 macOS 版本（Intel 还是 Apple Silicon）＋截图，转技术确认包架构是否匹配。
- 勿建议用户关闭系统安全设置（Gatekeeper 全局关闭）。
