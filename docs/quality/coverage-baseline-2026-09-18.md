# C端 前端覆盖率基线报告 ＋ 分批补测计划（2026-09-18）

> 用途：用户要求「100% 测试覆盖率」。已交付的口径是**本次交付触及的 5 个文件四项
> 指标 100%**（语句/分支/函数/行，阈值已入 `vitest.config.ts` + `npm run coverage`
> 可复验）。本报告给出**整仓**基线，供决定是否立项「整仓覆盖率」专项。

## 一、整仓基线（单测口径）

测量命令（在 `client/frontend` 下）：

```bash
npx vitest run --coverage --coverage.include='src/**' \
  --coverage.reporter=json --coverage.reporter=text-summary
```

注意：仓库配置里锁了 5 文件四项 100% 阈值，所以上面这条命令**会以阈值不达标报错退出**
（这是预期的——它正是"整仓未达 100%"的机器判据）；数字照常输出。

| 指标 | 整仓 | 备注 |
|---|---|---|
| 语句 | **4254 / 8071 = 52.7%** | 136 个文件 |
| 行 | 3860 / 7062 = 54.65% | |
| 分支 | 3022 / 6226 = 48.53% | |
| 函数 | 1139 / 2384 = 47.77% | |

口径说明：只统计**单元测试**（vitest）；C端 e2e（155 条）在运行时覆盖了其中相当一部分
交互，但 e2e 覆盖率不计入本表，也未被仓库任何门禁采集。

## 二、缺口分布

### 未覆盖语句 TOP 20

| 文件 | 未覆盖/总语句 |
|---|---|
| `components/novel/settings/HooksSettingForm.tsx` | 530 / 534（几乎零覆盖） |
| `components/novel/workbench/ChapterWorkspace.tsx` | 183 / 347 |
| `components/novel/settings/CharacterManager.tsx` | 150 / 377 |
| `components/novel/workbench/OutlineTree.tsx` | 143 / 192 |
| `components/novel/workbench/SettingsView.tsx` | 140 / 397 |
| `components/novel/settings/StyleSettingForm.tsx` | 138 / 277 |
| `components/novel/VersionDiff.tsx` | 131 / 131（零覆盖） |
| `pages/NovelListPage.tsx` | 123 / 123（零覆盖） |
| `components/novel/workbench/ProsePane.tsx` | 115 / 210 |
| `components/novel/workbench/VolumePanel.tsx` | 114 / 122 |
| `pages/LoginPage.tsx` | 113 / 113（零覆盖） |
| `components/novel/NovelWorkspace.tsx` | 110 / 242 |
| `components/novel/workbench/OgPane.tsx` | 90 / 106 |
| `components/novel/settings/GenreSettingForm.tsx` | 78 / 459 |
| `components/api-config/ApiConfigForm.tsx` | 78 / 78（零覆盖） |
| `hooks/useWorkbench.ts` | 76 / 171 |
| `components/novel/StructureTree.tsx` | 73 / 73（零覆盖） |
| `pages/ApiKeyConfigPage.tsx` | 71 / 71（零覆盖） |
| `hooks/useApiConfigs.ts` | 66 / 91 |
| `components/novel/settings/world/WorldSettingPanel.tsx` | 64 / 205 |

### 按目录聚合（未覆盖语句）

| 目录 | 未覆盖/总 |
|---|---|
| `components/novel/**` | 2618 / 5660 |
| `hooks/` | 324 / 810 |
| `pages/` | 321 / 321（全部零覆盖） |
| `lib/` | 265 / 744 |
| `components/api-config/` | 182 / 183 |
| `components/`（其余） | 77 / 289 |
| `components/design/` | 19 / 53 |
| `App.tsx` + `components/auth/` + `main.tsx` | 11 / 13 |

**零覆盖文件 46 个**（如 `VersionDiff.tsx`、`NovelListPage.tsx`、`LoginPage.tsx`、
`ApiConfigForm.tsx`、`StructureTree.tsx`、`ApiKeyConfigPage.tsx` 等）。

## 三、分批补测计划（建议顺序）

每批的验收标准统一：该批文件 **语句/分支/函数/行 100%**（不可达防御分支按
`/* v8 ignore start|stop */` 显式标注＋写理由），每批提交前跑 `npm run coverage`
与全量单测 + tsc，并按仓库惯例走 PR＋双路评审＋合入。

| 批 | 范围 | 未覆盖语句 | 预估 | 主要难点 |
|---|---|---|---|---|
| 批 1 | `hooks/**` + `lib/**` | 589 | 约 1 天 | 纯逻辑为主，需 stub fetch/localStorage；`useApiConfigs` 的 409/503 分支可复用本轮 `apiBoundaries` 手法 |
| 批 2 | `pages/**` + `components/api-config/**` + `components/auth/**` + `App.tsx` | 514 | 约 1~1.5 天 | 页面级需 Router/auth/tier 三件套 stub；登录/注册页涉及 OAuth 跳转桩 |
| 批 3 | `components/novel/settings/**`（含 530 行的 HooksSettingForm） | 约 1050 | 约 2~3 天 | 表单交互密集（提交/校验/回执/撤销），建议按"表单契约 × 两三条主路径"逐个收口 |
| 批 4 | `components/novel/workbench/**` + `NovelWorkspace` + `components/design/**` | 约 1650 | 约 3~4 天 | 最复杂：三栏壳层、树/编辑器/卷纲面板的联动；`ManuscriptDownloadModal` 已是先例（本轮补齐） |
| 收尾 | 阈值抬升与门禁 | — | 约 0.5 天 | 把 `coverage.include` 扩到 `src/**`，阈值按批分段抬（每批 +15~20%），末批锁 100%；可选：CI 增 `npm run coverage` job（会拉长 CI 时长） |

合计约 **8~10 个工作日**（单会话连续作业可压缩；批间无依赖，可并行拆给多会话）。

## 四、决策请求

- **按现口径结项**：交付触及的 5 文件四项 100% 已入库且可复验（`npm run coverage`），
  本次 P1/P2/P3 的每一行改动都有可判红的测试覆盖。
- **立项整仓覆盖率**：回「立项整仓覆盖率」，我按上面四批推进；每批独立 PR＋双路评审，
  批间可随时叫停。

补一句成本提示：整仓 100% 中有相当一部分是"e2e 已覆盖、但单测没覆盖"的 UI 交互，
把这部分补成单测属于**为覆盖率而写测试**（维护成本会持续存在）；若目标是"防止回归"，
更划算的替代是**分段阈值 + 新增/改动文件必须 100%**（本轮已对 5 个文件示范），
而不是一次性把整仓推到 100%。
