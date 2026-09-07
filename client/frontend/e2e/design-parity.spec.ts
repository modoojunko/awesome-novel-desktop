// 设计一致性视觉比对（design:check 第 2 层）—— 原型即基线。
// 同一次 run 内截「原型 file:// 页」与「应用页（打桩固定数据）」，
// pixelmatch 逐像素比对；差异图落 docs/design-c/baselines/。
// 仅 design:check（DESIGN_PARITY=1）运行；常规 `playwright test` 跳过，
// 且 docs/design-c/ 本地资产缺失时自动跳过（不入 git，fresh clone 无此目录）。
//
// 基线 = Open Design v2 原型 list.html（自包含单文件，系统字体栈，无 tw.css）。
// 原型状态注入：localStorage ainovel.books（显式空数组=空态，见 ADJUSTMENTS.md）。
// 应用侧打桩 /api/novels 与原型 SEED_BOOKS 逐字段对齐；updated_at 用相对 now
// 计算，使「N 小时前/昨天/N 天前」文案与原型字面量一致。
// 设计为单一亮色主题——无主题矩阵（旧 novelforge/parchment 双主题已废）。
import fs from "fs";
import path from "path";
import { test, expect } from "@playwright/test";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { stubUpdateNotice } from "./helpers";

// process.cwd() = client/frontend（playwright 运行目录，与既有 spec 一致；type:module 下无 __dirname）
const PROTO_FILE = path.resolve(process.cwd(), "../../docs/design-c/prototypes/list.html");
const BASELINE_DIR = path.resolve(process.cwd(), "../../docs/design-c/baselines");
const RUN_PARITY = process.env.DESIGN_PARITY === "1";
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 1 } as const;
const MAX_DIFF_RATIO = 0.002; // 0.2% 像素阈值（抗锯齿容差）

// 与原型 SEED_BOOKS 完全一致的固定数据（相对时间由 stub 时动态计算）
const H = 3600_000;
const FIXED_NOVELS = () => [
  {
    id: "parity-1",
    name: "星海拾遗",
    slug: "parity-1",
    current_phase: "write", // → 写作中
    total_volumes: 2,
    total_chapters: 4,
    word_count: 1371,
    genre: "科幻",
    synopsis: "废弃星港上，导航员沉舟捡到一枚不属于人类纪元的导航信标，决定修好旧船去追一段回声。",
    updated_at: new Date(Date.now() - 2 * H).toISOString(), // → 2 小时前
  },
  {
    id: "parity-2",
    name: "长夜灯",
    slug: "parity-2",
    current_phase: "settings", // → 设定中
    total_volumes: 1,
    total_chapters: 2,
    word_count: 0,
    genre: "悬疑",
    synopsis: "一座永远天亮不了的县城，一个在深夜点灯的人。",
    updated_at: new Date(Date.now() - 24 * H).toISOString(), // → 昨天
  },
  {
    id: "parity-3",
    name: "雾中法庭",
    slug: "parity-3",
    current_phase: "archive", // → 已归档
    total_volumes: 3,
    total_chapters: 9,
    word_count: 12842,
    genre: "都市",
    synopsis: "律所新人姜序被卷入一场横跨十二年的旧案，迷雾散去时，法槌落下。",
    updated_at: new Date(Date.now() - 72 * H).toISOString(), // → 3 天前
  },
];

// 原型侧 localStorage 注入用（字段名与 SEED_BOOKS 一致；stage/stageLabel/updated 为原型字面量）
const PROTO_BOOKS = [
  {
    title: "星海拾遗", genre: "科幻", stage: "writing", stageLabel: "写作中",
    vols: 2, chs: 4, words: 1371, updated: "2 小时前",
    summary: "废弃星港上，导航员沉舟捡到一枚不属于人类纪元的导航信标，决定修好旧船去追一段回声。",
  },
  {
    title: "长夜灯", genre: "悬疑", stage: "setting", stageLabel: "设定中",
    vols: 1, chs: 2, words: 0, updated: "昨天",
    summary: "一座永远天亮不了的县城，一个在深夜点灯的人。",
  },
  {
    title: "雾中法庭", genre: "都市", stage: "done", stageLabel: "已归档",
    vols: 3, chs: 9, words: 12842, updated: "3 天前",
    summary: "律所新人姜序被卷入一场横跨十二年的旧案，迷雾散去时，法槌落下。",
  },
];

const MEMBER_VERIFY = { tier: "monthly", is_member: true, expired: false, trial_remaining_days: 0 };
// quota 场景隔离口径：is_member=false 触发免费额度墙，但 tier 非 none/trial 且未过期，
// 屏蔽账号 Banner（原型无 Banner），只比额度墙本身
const FREE_VERIFY = { tier: "monthly", is_member: false, expired: false, trial_remaining_days: 0 };

const CASES = [
  { state: "books", books: PROTO_BOOKS, member: true },
  { state: "empty", books: [] as unknown[], member: true },
  { state: "quota", books: [PROTO_BOOKS[0]], member: false }, // 免费额度墙：1/1
] as const;

test.describe("design-parity 书架屏（list.html）", () => {
  test.skip(
    !RUN_PARITY || !fs.existsSync(PROTO_FILE),
    !RUN_PARITY ? "仅 design:check 运行（DESIGN_PARITY=1）" : "原型缺失：docs/design-c/ 为本地资产"
  );

  for (const c of CASES) {
    test(c.state, async ({ browser }) => {
      // ── 原型侧（设计真值）──────────────────────────────────
      const protoCtx = await browser.newContext({ viewport: VIEWPORT });
      await protoCtx.addInitScript(
        ({ books, member }) => {
          localStorage.setItem("ainovel.books", JSON.stringify(books));
          localStorage.setItem("ainovel.member", member ? "1" : "0");
        },
        { books: c.books, member: c.member },
      );
      const protoPage = await protoCtx.newPage();
      await protoPage.goto(`file://${PROTO_FILE}`);
      await protoPage.evaluate(() => document.fonts.ready);
      await protoPage.waitForTimeout(700);
      const protoShot = await protoPage.screenshot();
      await protoCtx.close();

      // ── 应用侧（打桩固定数据）──────────────────────────────
      const appCtx = await browser.newContext({ viewport: VIEWPORT });
      await appCtx.addInitScript(() => {
        localStorage.setItem("auth_token", "parity-stub-token");
        localStorage.setItem("auth_username", "parity");
      });
      const appPage = await appCtx.newPage();
      const novels = c.state === "books" ? FIXED_NOVELS() : c.state === "quota" ? [FIXED_NOVELS()[0]] : [];
      await appPage.route("**/api/novels", (r) => r.fulfill({ json: novels }));
      // 原型常显更新提示条（ADJUSTMENTS #15）→ 应用侧同文案打桩，保持像素基线
      await stubUpdateNotice(appPage, "update");
      await appPage
        .route("**/api/auth/verify", (r) => r.fulfill({ json: c.member ? MEMBER_VERIFY : FREE_VERIFY }));
      // portal_url 给真值：appbar「联系客服」按钮与原型同步渲染（空值时按钮隐藏，会造像素差）
      await appPage.route("**/api/auth/config", (r) =>
        r.fulfill({ json: { has_api_key: true, portal_url: "https://www.awesomenovel.com" } })
      );
      await appPage.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
      await appPage.goto("/#/novels");
      await appPage.waitForLoadState("networkidle");
      await appPage.evaluate(() => document.fonts.ready);
      await appPage.waitForTimeout(700); // page-enter 0.4s 收敛
      const appShot = await appPage.screenshot();
      await appCtx.close();

      // ── 比对 ────────────────────────────────────────────────
      const a = PNG.sync.read(protoShot);
      const b = PNG.sync.read(appShot);
      if (a.width !== b.width || a.height !== b.height) {
        throw new Error(
          `截图尺寸不一致（结构差异）：原型 ${a.width}x${a.height} vs 应用 ${b.width}x${b.height}`
        );
      }
      const diff = new PNG({ width: a.width, height: a.height });
      const diffCount = pixelmatch(a.data, b.data, diff.data, a.width, a.height, {
        threshold: 0.1,
      });
      fs.mkdirSync(BASELINE_DIR, { recursive: true });
      const base = `list.${c.state}`;
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.proto.png`), protoShot);
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.app.png`), appShot);
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.diff.png`), PNG.sync.write(diff));
      const ratio = diffCount / (a.width * a.height);
      expect(
        ratio,
        `像素差异率 ${(ratio * 100).toFixed(3)}%（阈值 0.2%）— 三张对比图见 docs/design-c/baselines/${base}.*`
      ).toBeLessThan(MAX_DIFF_RATIO);
    });
  }
});
