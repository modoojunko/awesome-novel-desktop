// 设计一致性视觉比对（design:check 第 2 层）—— 原型即基线。
// 同一次 run 内截「原型 file:// 页」与「应用页（打桩固定数据）」，
// pixelmatch 逐像素比对；差异图落 docs/design-c/baselines/。
// 仅 design:check（DESIGN_PARITY=1）运行；常规 `playwright test` 跳过，
// 且 docs/design-c/ 本地资产缺失时自动跳过（不入 git，fresh clone 无此目录）。
//
// 基线 = prototypes/list.html（v2 换代：工具栏＋分组＋分页，c-works-toolbar；2026-09-20）。
// 原型状态注入：localStorage od.works.v1（显式空数组=空态；书含 state/createdAt/updatedAt
// 数字时间戳——缺失会触发 v2 归一化改写、排序静默退化，见 ADJUSTMENTS 换代 v2 章 #11）；
// quota 场景另注 ainovel.member='0'。应用侧打桩 /api/novels 与原型数据逐字段对齐；
// updated_at 用相对 now 计算，使「N 小时前/昨天/N 天前」文案与原型注入字面量一致。
// 设计为单一亮色主题——无主题矩阵（旧 novelforge/parchment 双主题已废）。
import fs from "fs";
import path from "path";
import { test, expect, type Page } from "@playwright/test";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { stubUpdateNotice } from "./helpers";

// process.cwd() = client/frontend（playwright 运行目录，与既有 spec 一致；type:module 下无 __dirname）
const PROTO_FILE = path.resolve(process.cwd(), "../../docs/design-c/prototypes/list.html");
const BASELINE_DIR = path.resolve(process.cwd(), "../../docs/design-c/baselines");
const RUN_PARITY = process.env.DESIGN_PARITY === "1";
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 1 } as const;
const MAX_DIFF_RATIO = 0.002; // 0.2% 像素阈值（抗锯齿容差）

// 与原型注入同源固定数据（相对时间由 stub 时动态计算；排序结论＝状态 rank 恒优先：
// 待完本→写作中→设定中→已完结，组内 updated_at 倒序）。
const H = 3600_000;
const D = 86400_000;
const NOW = Date.now();
const FIXED_NOVELS = () => [
  {
    id: "parity-ready",
    name: "沙漏之下",
    slug: "parity-ready",
    current_phase: "write",
    total_volumes: 2,
    total_chapters: 6,
    total_archives: 6, // 全归档未完结 → 待完本（rank 0，恒置顶）
    word_count: 21400,
    genre: "玄幻",
    synopsis: "时间在城外的沙丘上倒流，捡贝壳的少年成了唯一记得明天的人。",
    updated_at: new Date(NOW - 26 * H).toISOString(), // → 昨天
    created_at: new Date(NOW - 60 * D).toISOString(),
    finished_at: null,
  },
  {
    id: "parity-1",
    name: "星海拾遗",
    slug: "parity-1",
    current_phase: "write",
    total_volumes: 2,
    total_chapters: 4,
    total_archives: 0, // 4 章未全归档 → 写作中（rank 1）
    word_count: 1371,
    genre: "科幻",
    synopsis: "废弃星港上，导航员沉舟捡到一枚不属于人类纪元的导航信标，决定修好旧船去追一段回声。",
    updated_at: new Date(NOW - 2 * H).toISOString(), // → 2 小时前
    created_at: new Date(NOW - 90 * D).toISOString(),
    finished_at: null,
  },
  {
    id: "parity-2",
    name: "长夜灯",
    slug: "parity-2",
    current_phase: "settings", // → 设定中（0 章，rank 2）
    total_volumes: 1,
    total_chapters: 0,
    total_archives: 0,
    word_count: 0,
    genre: "悬疑",
    synopsis: "一座永远天亮不了的县城，一个在深夜点灯的人。",
    updated_at: new Date(NOW - 26 * H).toISOString(), // → 昨天
    created_at: new Date(NOW - 5 * D).toISOString(),
    finished_at: null,
  },
  {
    id: "parity-3",
    name: "雾中法庭",
    slug: "parity-3",
    current_phase: "archive",
    total_volumes: 3,
    total_chapters: 9,
    total_archives: 9,
    word_count: 12842,
    genre: "都市",
    synopsis: "律所新人姜序被卷入一场横跨十二年的旧案，迷雾散去时，法槌落下。",
    updated_at: new Date(NOW - 72 * H).toISOString(), // → 3 天前
    created_at: new Date(NOW - 200 * D).toISOString(),
    finished_at: new Date(NOW - 72 * H).toISOString(), // → 已完结：完结于 3 天前
  },
];

// 原型侧 od.works.v1 注入（v2 schema：state/finishedAt＋数字 createdAt/updatedAt；
// updated 为展示字面量，与 FIXED_NOVELS 的相对时间结论逐字一致）
const PROTO_BOOKS = [
  {
    title: "沙漏之下", genre: "玄幻", state: "ready",
    vols: 2, chs: 6, words: 21400, updated: "昨天",
    createdAt: NOW - 60 * D, updatedAt: NOW - 26 * H, parked: {},
    summary: "时间在城外的沙丘上倒流，捡贝壳的少年成了唯一记得明天的人。",
  },
  {
    title: "星海拾遗", genre: "科幻", state: "writing",
    vols: 2, chs: 4, words: 1371, updated: "2 小时前",
    createdAt: NOW - 90 * D, updatedAt: NOW - 2 * H, parked: {},
    summary: "废弃星港上，导航员沉舟捡到一枚不属于人类纪元的导航信标，决定修好旧船去追一段回声。",
  },
  {
    title: "长夜灯", genre: "悬疑", state: "setting",
    vols: 1, chs: 0, words: 0, updated: "昨天",
    createdAt: NOW - 5 * D, updatedAt: NOW - 26 * H, parked: {},
    summary: "一座永远天亮不了的县城，一个在深夜点灯的人。",
  },
  {
    title: "雾中法庭", genre: "都市", state: "done", finishedAt: "3 天前",
    vols: 3, chs: 9, words: 12842, updated: "3 天前",
    createdAt: NOW - 200 * D, updatedAt: NOW - 72 * H,
    summary: "律所新人姜序被卷入一场横跨十二年的旧案，迷雾散去时，法槌落下。",
  },
];

// 分页场景：13 本同名写作中（rank 同组、updated 递减），两侧同数据
const PAGE_N = 13;
const paginationAppNovels = () =>
  Array.from({ length: PAGE_N }, (_, i) => ({
    id: `parity-p${i}`,
    name: `分页书${String(i).padStart(2, "0")}`,
    slug: `parity-p${i}`,
    current_phase: "write",
    total_volumes: 1,
    total_chapters: 2,
    total_archives: 1, // 未全归档 → 写作中
    word_count: 1000 + i,
    genre: "玄幻",
    synopsis: "分页演示书。",
    updated_at: new Date(NOW - i * H).toISOString(),
    created_at: new Date(NOW - (i + 10) * D).toISOString(),
    finished_at: null,
  }));
const paginationProtoBooks = () =>
  Array.from({ length: PAGE_N }, (_, i) => ({
    title: `分页书${String(i).padStart(2, "0")}`,
    genre: "玄幻",
    state: "writing",
    vols: 1, chs: 2, words: 1000 + i,
    updated: `${i} 小时前`,
    createdAt: NOW - (i + 10) * D,
    updatedAt: NOW - i * H,
    parked: {},
    summary: "分页演示书。",
  }));

const MEMBER_VERIFY = { tier: "monthly", is_member: true, expired: false, trial_remaining_days: 0 };
// quota 场景隔离口径：is_member=false 触发免费额度墙，但 tier 非 none/trial 且未过期，
// 屏蔽账号 Banner（原型无 Banner），只比额度墙本身
const FREE_VERIFY = { tier: "monthly", is_member: false, expired: false, trial_remaining_days: 0 };

type Case = {
  state: string;
  books: unknown[];
  protoBooks?: unknown[];
  member: boolean;
  /** 两侧同点操作（点击选择器各自给） */
  act?: { proto: string; app: string } | { proto: string; app: string }[];
  fill?: { proto: string; app: string; text: string };
};

const CASES: Case[] = [
  { state: "books", books: FIXED_NOVELS(), protoBooks: PROTO_BOOKS, member: true },
  // 单态分组：钉 ready（「主线已收齐 · 去完本」入口唯一出现处）
  { state: "group", books: FIXED_NOVELS(), protoBooks: PROTO_BOOKS, member: true, act: { proto: "#filters .chip[data-kind='ready']", app: '[data-od-id="filter-ready"]' } },
  // 筛选无果：已完结 chip ＋ 搜索不中 → bk-empty（标题＋清除筛选）
  {
    state: "empty-filter",
    books: FIXED_NOVELS(),
    protoBooks: PROTO_BOOKS,
    member: true,
    act: { proto: "#filters .chip[data-kind='done']", app: '[data-od-id="filter-done"]' },
    fill: { proto: "#q", app: 'input[type="search"]', text: "不存在的书名" },
  },
  { state: "empty", books: [], protoBooks: [], member: true },
  { state: "finish", books: FIXED_NOVELS(), protoBooks: PROTO_BOOKS, member: true }, // 完本清单弹窗：点「完本」后采样
  // 免费额度墙：1/1＋锁卡（两侧同为一本，protoBooks 必须显式配对——回退 PROTO_BOOKS 会 4 本 vs 1 本）
  { state: "quota", books: [FIXED_NOVELS()[1]], protoBooks: [PROTO_BOOKS[1]], member: false },
  { state: "pagination", books: paginationAppNovels(), protoBooks: paginationProtoBooks(), member: true },
];

test.describe("design-parity 书架屏（list.html v2）", () => {
  test.skip(
    !RUN_PARITY || !fs.existsSync(PROTO_FILE),
    !RUN_PARITY ? "仅 design:check 运行（DESIGN_PARITY=1）" : "原型缺失：docs/design-c/ 为本地资产"
  );

  for (const c of CASES) {
    test(c.state, async ({ browser }) => {
      const books = typeof c.books === "function" ? (c.books as () => unknown[])() : c.books;
      const protoBooks = c.protoBooks ?? PROTO_BOOKS;

      // ── 原型侧（设计真值）──────────────────────────────────
      const protoCtx = await browser.newContext({ viewport: VIEWPORT });
      await protoCtx.addInitScript(
        ({ books: pb, member }) => {
          localStorage.setItem("od.works.v1", JSON.stringify(pb));
          localStorage.setItem("ainovel.member", member ? "1" : "0");
        },
        { books: protoBooks, member: c.member },
      );
      const protoPage = await protoCtx.newPage();
      await protoPage.goto(`file://${PROTO_FILE}`);
      // demo-bar 是原型自带的状态切换 chrome（非基线，收编前删除）——
      // c-prompt-pack-onboard-modal 起挂在 list.html 底部，比对前移除
      // （book parity 藏 doc-head 同理：应用侧没有这块，不移除会造整条底栏像素差）
      await protoPage.evaluate(() => document.querySelector(".demo-bar")?.remove());
      await protoPage.evaluate(() => document.fonts.ready);
      // 帧位标定（e2e-speedup-infra 判保留）：parity 截图需两侧同一确定性帧，
      // 固定等待即标定值，非脆弱等待——勿换 pageSettled（遮罩动画帧位会漂，实测 84% 差异）
      await protoPage.waitForTimeout(700);
      await driveBoth(protoPage, c, "proto");
      const protoShot = await protoPage.screenshot();
      await protoCtx.close();

      // ── 应用侧（打桩固定数据）──────────────────────────────
      const appCtx = await browser.newContext({ viewport: VIEWPORT });
      await appCtx.addInitScript(() => {
        localStorage.setItem("auth_token", "parity-stub-token");
        localStorage.setItem("auth_username", "modoojunko"); // 与原型头像首字一致（像素级比对）
      });
      const appPage = await appCtx.newPage();
      await appPage.route("**/api/novels", (r) => r.fulfill({ json: books }));
      // finish 场景：完本清单弹窗的数据源打桩（无 active 伏笔 → 第二行 ok 形态）
      if (c.state === "finish") {
        await appPage.route("**/api/novels/parity-ready/hooks", (r) =>
          r.fulfill({ json: { ok: true, data: { count: 0, items: [] } } }));
        await appPage.route("**/api/novels/parity-ready/volumes", (r) => r.fulfill({ json: [] }));
      }
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
      // 帧位标定（同上）：page-enter 0.4s 收敛后采样
      await appPage.waitForTimeout(700);
      await driveBoth(appPage, c, "app");
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

/** 场景动作（两侧同一操作，选择器各给）：finish 点完本、group/empty-filter 切筛选、搜不中。 */
async function driveBoth(page: Page, c: Case, side: "proto" | "app") {
  if (c.state === "finish") {
    await page.getByText("完本", { exact: true }).click();
    await page.waitForTimeout(700);
    return;
  }
  const acts = c.act ? (Array.isArray(c.act) ? c.act : [c.act]) : [];
  for (const a of acts) {
    await page.locator(a[side]).click();
    await page.waitForTimeout(300);
  }
  if (c.fill) {
    await page.locator(c.fill[side]).fill(c.fill.text);
    await page.waitForTimeout(300);
  }
}
