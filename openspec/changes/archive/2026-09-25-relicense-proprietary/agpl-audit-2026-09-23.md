# S端 依赖 AGPL 排查结论（relicense-proprietary 任务 5.5）

日期：2026-09-23　方法：干净 venv 安装 `server/requirements.txt` 全量依赖后逐发行版三级取值
（License-Expression → License → classifier）；npm 侧扫 `server/frontend/package-lock.json` 全部 license 字段。

## 结论：零 AGPL / SSPL 命中

- **pip（44 个发行版）**：无 AGPL/SSPL。全部为宽松许可（MIT/BSD/Apache-2.0/PSF-2.0/MPL-2.0）。
- **npm（S端 frontend lockfile）**：无 AGPL/SSPL。

## 两项非 AGPL 但值得登记的发现

1. **psycopg2-binary —— "LGPL with exceptions"**：仅 S端 使用；S端 以云托管方式提供服务、
   **不分发**二进制（AGPL 式网络使用条款对 LGPL 无意义、LGPL 对「使用/链接」也无传染——仅修改该库
   本身才需开放修改），无合规动作需要。C端 分发包不含 psycopg2（C端 后端只走 SQLite/aiosqlite）。
2. **cryptography —— "Apache-2.0 OR BSD-3-Clause" 双许可**：两端 venv 均有。按 OR 任选其一即可，
   客户端分发声明按 Apache-2.0 口径已列入 THIRD-PARTY-NOTICES.txt 清单。

## 处置

- S端 不挂常驻许可证门禁（proposal Non-Goals 既定：不分发无 copyleft 分发义务）；本排查为一次性摸底，
  未来新增依赖时人工留意即可。
- 命中数：AGPL 0 ／ SSPL 0 ／ 需动作项 0。
