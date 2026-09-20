# 2026-09-05 开发日记配图方案（图位清单 + 提示词）

文章：《开发日记 09-05，测试全绿，打开就崩》（AI 写的 bug，测试全绿，dmg 打开就崩）

## 图位清单（三处）

| 位置 | 图 | 状态 |
|---|---|---|
| 问题段后（bridge 未创建） | 图1 断桥比喻 | 文生图占位，提示词见下 |
| 测试拆解段后 | 图2 C端交付结构图（含 bridge 位置与 v0.15 断点） | 已渲染：`figT3-small.png`，文件名"日记图2-交付结构与bridge位置.png" |
| 修复段后 | 图3 新门禁拦截流 | 已渲染：`figT2-small.png`，文件名"日记图3-新门禁.png" |

## 图2 交付结构图（已画好，基于仓库真实结构）

内容：client 目录三件套（frontend / backend / packaging）→ PyInstaller 冻结打包（mac 出 dmg，win 出 exe）→ 用户双击 → create_window 时注入 bridge（v0.15 漏了 bridge = NativeBridge() 这一行）→ 注入成功走前端 window.pywebview.api 调 bridge；漏了这行当场 NameError，GUI 启动即炸；另一分支 backend 在本机起服务。

真实代码出处：`client/packaging/build/pywebview_app.py`，NativeBridge 类在 268 行，`bridge = NativeBridge()` 单例在 298 行，代码注释里现在还留着"v0.15 曾漏掉本行"的警句。

## 图1 文生图提示词（断桥）

一座玻璃质感的桥断了一截，缺口处透出微光，桥的那头悬浮着一颗发光的绿色圆形图标。冷色调扁平插画，深蓝主色配绿色点缀，画面内不出现任何文字，无水印。

## 图3 门禁图（已画好）

打包入口 → F821 静态检查（用了没定义的名字？）→ 有则拦下打包失败 / 干净则出安装包。
