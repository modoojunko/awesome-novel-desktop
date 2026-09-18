# C端 前端覆盖率基线报告 ＋ 分批补测计划（2026-09-18）

> 用途：用户要求「100% 测试覆盖率」。已交付的口径是**逐批纳入契约的文件四项
> 指标 100%**（批 0 = 5 个文件；批 1 首波后 = 17 个文件，语句/分支/函数/行，阈值已入 `vitest.config.ts` + `npm run coverage`
> 可复验）。本报告给出**整仓**基线，供决定是否立项「整仓覆盖率」专项。

## 进度更新

### 批 1 收尾（2026-09-18，PR #423，测量 commit 待合）
`pages/LoginPage`（登录/静默检测/浏览器授权轮询）＋ `pages/NovelListPage`（书架：六类 Banner＋
卡片＋改名/删除全链）补到四项 100%；契约 21 → **23 个文件**，并把 **pages 目录完整性**
写入 `coverageContract` 的目录断言（此后 pages 下新增页面漏进契约会直接红）。

| 指标 | 第二波后 | 收尾后 |
|---|---|---|
| 语句 | 58.47%（4718/8068） | **61.48%（4957/8062）** |
| 行 | 60.66% | **63.56%（4487/7059）** |
| 分支 | 53.8% | **56.75%（3530/6220）** |
| 函数 | 52.89% | **55.53%（1324/2384）** |

批 1（风险优先：账号/密钥/页面/路由面）至此收口。下一批按报告第四节顺序：
批 2 `hooks/**` + `lib/**`（除已覆盖部分）→ 批 3 `components/novel/settings/**`
→ 批 4 `components/novel/**` 其余。

### 批 1 第二波（2026-09-18，PR #422，测量 commit 8b8e7ec）
页面面 4 个文件补到四项 100%：`pages/ApiKeyConfigPage`（收口）、`components/ExpiryNoticeBar`、
`pages/LandingPage`、`pages/NovelLayout`；契约 17 → **21 个文件**。

| 指标 | 首波后 | 第二波后 |
|---|---|---|
| 语句 | 55.69%（4496/8072） | **58.47%（4718/8068）** |
| 行 | 57.77% | **60.66%（4284/7062）** |
| 分支 | 51.78% | **53.8%（3351/6228）** |
| 函数 | 50.2% | **52.89%（1261/2384）** |

**本轮评审抓到一条系统性假绿模式（值得全项目警惕）**：负向断言写成
`await waitFor(() => expect(x).toBeNull())` 会在异步取数 **resolve 之前**就通过——
"不该出现"从此不可判红（18 个变异探针 8 个存活，全出于此）。修法（已内化）：
**deferred promise + `await act(async () => resolve(...))` 做正同步点**，再断言缺席；
边界臂（如"第 8 天不该提示"）必须显式存在，否则 `days <= 8` 这类越界变异会存活。

### 批 1 首波（2026-09-18）
已交付：`components/api-config/**`（8 个文件）＋ `App.tsx`＋`components/auth/AuthGuard.tsx`
＋ `hooks/useDeviceActivation.ts` ＋ `lib/selection.ts`，共 **12 个文件补到四项 100%**
（语句/分支/函数/行），并纳入覆盖率契约（`vitest.config.ts` 的 include 与
`coverageContract.test.ts` 自检清单，契约从 5 → **17 个文件**；CI 的单测步继续用
`--coverage` 把关）。

整仓随之变化（同一命令口径）：

| 指标 | 基线（批 0 时） | 批 1 首波后 |
|---|---|---|
| 语句 | 52.7%（4254/8071）※ | **55.69%（4496/8072）** |
| 行 | 54.65% | **57.77%** |
| 分支 | 48.53% | **51.78%（3225/6228，重测口径）** |
| 函数 | 47.77% | **50.2%** |

※ 批 0 那一列（4254/8071）是在 #418 的 `v8 ignore` 定稿**之前**测的，用 `bca2fba` 重测得
4257/8074（差 3 语句 / 4 分支 / 2 行 = 被后加的 ignore 从分母抹掉的两条未覆盖语句）。
自本波起：**每个数字随 PR 重新测量并标注测量 commit**，避免"分母静默缩小"复发。

<!-- 每完成一波在此追加一行并按需更新上方数字与第四节批次表的完成标记 -->

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
| `App.tsx` + `components/auth/` + `main.tsx` | 11 / 11（全零覆盖） |

**零覆盖代码文件 38 个**（如 `VersionDiff.tsx`、`NovelListPage.tsx`、`LoginPage.tsx`、
`ApiConfigForm.tsx`、`StructureTree.tsx`、`ApiKeyConfigPage.tsx` 等）；另有 **8 个无语句
文件**（6 个 CSS + `volume/types.ts`、`types/api-config.ts` 两个纯类型文件），不计入缺口。
整仓 136 个受测文件中包含这 6 个 CSS。

## 三、分批补测计划（建议顺序）

每批的验收标准统一：该批文件 **语句/分支/函数/行 100%**（不可达防御分支按
`/* v8 ignore start|stop */` 显式标注＋写理由），每批提交前跑 `npm run coverage`
与全量单测 + tsc，并按仓库惯例走 PR＋双路评审＋合入。

**排序原则 = 风险优先**（账号 / 密钥 / 计费 / 数据写入面排在体量大的纯 UI 之前）：
零覆盖清单里 `pages/LoginPage.tsx`(113)、`pages/ApiKeyConfigPage.tsx`(71)、
`components/api-config/**`(182/183) 合计 **366 条未覆盖语句**是"凭证与计费"面，
必须最先补——它们已在批 2 内，故批 2 提前到批 1 之前执行。

| 批 | 范围 | 未覆盖语句 | 预估（乐观下界） | 主要难点 |
|---|---|---|---|---|
| **批 0（校准）** | 从批 1 或批 3 挑一个文件（建议 `HooksSettingForm` 534 或 `hooks/**` 全目录）按"四项 100% + 每条 ignore 写可达性论证"的同一标准走完并计时 | — | 约 0.5~1 天 | 用真实速率回填下面四批的估算；本轮 5 文件 442 语句用了两个 PR、24 条用例才四项 100% |
| 批 1（=风险面） | `pages/**` + `components/api-config/**` + `components/auth/**` + `App.tsx` + `hooks/useDeviceActivation` + `lib/selection.ts` | 514 | 需按批 0 校准回填 | 页面级需 Router/auth/tier 三件套 stub；登录/注册/注销页涉及 OAuth 跳转桩，密钥表单涉及掩码与校验 |
| 批 2 | `hooks/**` + `lib/**`（除已覆盖部分；`lib/markdown.ts` 建议直接删，见遗留项） | 589 | 同上 | 纯逻辑为主，需 stub fetch/localStorage；可复用本轮 `apiBoundaries` 手法 |
| 批 3 | `components/novel/settings/**`（含 530 行的 HooksSettingForm） | 约 1050 | 同上 | 表单交互密集（提交/校验/回执/撤销），建议按"表单契约 × 两三条主路径"逐个收口 |
| 批 4 | **`components/novel/**` 其余全部**（workbench 936 + NovelWorkspace 110 + volume/license 等约 480）+ `components/design/**` | 约 1664 | 同上 | 最复杂：三栏壳层、树/编辑器/卷纲面板的联动；`ManuscriptDownloadModal` 已是先例（本轮补齐） |
| 收尾 | 阈值抬升 | — | 约 0.5 天 | 把 `coverage.include` 扩到 `src/**`，阈值按批分段抬（每批 +15~20%），末批锁 100% |

估算口径说明：上一版"8~10 人日"是**乐观下界**——它没算"每一处 `v8 ignore` 都要写可达性
论证并被评审挑战"的成本（本轮 7 处里就有 2 处论证不成立、被两路评审各用探针实测推翻）。
请以批 0 的实测速率 × 剩余语句数回填，再乘 1.5~2 的安全系数。

**CI 门禁已在 #418 打开（契约清单自本波起是单一事实源 `src/coverage-contract.ts`）**：`client-frontend-ci.yml` 的单测步改为 `npx vitest run --coverage`，
阈值从此在 PR 上生效（实测与不开覆盖率无显著差异；契约清单见 `src/coverage-contract.ts`）。

## 四、决策请求

- **按现口径结项**：交付触及的 5 文件四项 100% 已入库且可复验（`npm run coverage`），
  本次 P1/P2/P3 的每一行改动都有可判红的测试覆盖。
- **立项整仓覆盖率**：回「立项整仓覆盖率」，我按上面四批推进；每批独立 PR＋双路评审，
  批间可随时叫停。

## 五、附：本轮顺带发现的两个小项（未在本 PR 修）

1. `src/lib/markdown.ts`（0/13，全仓无引用）是**死代码**——行内转义实现已被
   `ProsePane.tsx` 与 `PreviewView.tsx` 各复制一份；建议直接删除（而不是排进补测计划），
   顺带给整仓分母瘦身并避免第三份转义实现漂移。
2. `RestoreModal` 完成页在 `okCount === 0` 时恒显示「模型配置已恢复」，即使本次是
   "全部恢复失败"——文案与实际不符（测试已按真实用户路径「只恢复配置包」改写，
   该文案问题登记为产品取舍，未在覆盖率 PR 内改）。

补一句成本提示：整仓 100% 中有相当一部分是"e2e 已覆盖、但单测没覆盖"的 UI 交互，
把这部分补成单测属于**为覆盖率而写测试**（维护成本会持续存在）；若目标是"防止回归"，
更划算的替代是**分段阈值 + 新增/改动文件必须 100%**（批 0/批 1 已示范），
而不是一次性把整仓推到 100%。
