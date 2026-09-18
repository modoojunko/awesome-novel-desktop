// 设计一致性视觉比对 —— 阅读预览屏（/#/novel/:id 预览 vs preview.html）。
// c-preview-reader：预览自 book.html 独立成屏（三栏阅读器），本 spec 接管原
// design-parity-book 的 preview 场景（ADJUSTMENTS「preview.html」#1）。
//
// 口径与 design-parity-book.spec.ts 一致：原型 file:// 直开（本屏即预览视图，
// 无需点击切换）；应用侧打桩全量 API，数据与本文件 SEED 逐字段对齐——
// 种子正文唯一事实源 = 原型 PROSE 数组（运行时提取，避免手抄漂移）。
//
// 状态口径（成稿状态，非章纲三态）：
//   archived → 已归档（优先）；has_prose → 草稿；其余 → 拟定。
//   种子：c1-c15 已归档（有正文）· c16 拟定（无正文）· c17 草稿（有正文未归档）。
//   初始章 = 写作视图当前章（ADJUSTMENTS #13 本地态），parity 态默认第一章
//   vol-1-ch-1，与原型「默认选首章」一致。
import fs from "fs";
import path from "path";
import { test, expect, type Page } from "@playwright/test";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { stubUpdateNotice } from "./helpers";

const PROTO_FILE = path.resolve(process.cwd(), "../../docs/design-c/prototypes/preview.html");
const BASELINE_DIR = path.resolve(process.cwd(), "../../docs/design-c/baselines");
const RUN_PARITY = process.env.DESIGN_PARITY === "1";
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 1 } as const;
const MAX_DIFF_RATIO = 0.002;
const PID = "p1";

/** 从 preview.html 提取 PROSE 种子（唯一事实源）。 */
function extractProse(): Record<string, string> {
  // 原型缺失的环境（如 CI）在模块加载期读文件会崩——守卫后交给 test.skip。
  if (!fs.existsSync(PROTO_FILE)) return {};
  const src = fs.readFileSync(PROTO_FILE, "utf-8");
  const m = src.match(/const PROSE = \{([\s\S]*?)\};/);
  if (!m) throw new Error("preview.html 中未找到 PROSE 种子");
  const out: Record<string, string> = {};
  for (const [, id, text] of m[1].matchAll(/(\w+):\s*'((?:[^'\\]|\\.)*)'/g)) {
    out[id] = text;
  }
  return out;
}

// 与原型 wordCount 同口径：去空白字符数
const words = (s: string) => s.replace(/\s/g, "").length;

// ── 种子（与原型 SEED 逐字段对齐）──────────────────────────────────────
const SEED = (() => {
  const prose = extractProse();
  const ids = (a: number, b: number) =>
    Array.from({ length: b - a + 1 }, (_, i) => `c${a + i}`);
  // 卷结构：vol1=1-6 · vol2=7-12 · vol3=13-17（全局章号，nodeLabel 单源）
  const layout: Array<{ ref: string; title: string; ids: string[]; titles: string[] }> = [
    { ref: "vol-1", title: "星海初航", ids: ids(1, 6), titles: ["锚点", "跃迁", "静默带", "旧航图", "拾荒者", "中继站"] },
    { ref: "vol-2", title: "星群之间", ids: ids(7, 12), titles: ["人群", "引力井", "船徽", "双航路", "镜面", "出队"] },
    { ref: "vol-3", title: "回声之海", ids: ids(13, 17), titles: ["归航", "镜像", "潮间", "刻痕", "回声之海"] },
  ];
  const chapter = (id: string, title: string) => {
    const no = parseInt(id.slice(1), 10);
    const has = !!prose[id];
    const archived = id !== "c16" && id !== "c17";
    return {
      chapter: no,
      title,
      word_count: has ? words(prose[id]) : 0,
      status: id === "c16" ? "in_progress" : "confirmed",
      has_prose: has,
      archived,
    };
  };
  const volumes = layout.map((v) => ({
    ref: v.ref,
    title: v.title,
    chapters: v.ids.map((id, i) => chapter(id, v.titles[i])),
  }));
  const project = {
    id: PID,
    name: "星海拾遗",
    type: "科幻",
    genre: "科幻",
    genre_label: "科幻",
    source: "manual",
  };
  // GET /tree（modnav「写作 16/17 章纲」与原型计数一致：c16 in_progress，其余 confirmed）
  const tree = {
    volumes: volumes.map((v) => ({
      ref: v.ref,
      title: v.title,
      summary: "",
      chapter_count: v.chapters.length,
      has_prose: v.chapters.some((c) => c.has_prose),
      chapters: v.chapters.map((c) => ({
        ref: `${v.ref}-ch-${c.chapter}`,
        volume: parseInt(v.ref.slice(4), 10),
        chapter: c.chapter,
        title: c.title,
        status: c.status,
        word_count: c.word_count,
        has_prose: c.has_prose,
        archived: c.archived,
      })),
    })),
  };
  // GET /readiness：题材/简介/风格 done → 设定 3/7（＝原型计数）
  const readiness = { missing: ["world", "hooks", "characters"].map((key) => ({ key })) };
  // GET /chapters/vol-1-ch-1（预览初始章 = 写作视图当前章）
  const first = prose.c1 ?? "";
  const chapterDetail = {
    volume: 1,
    chapter: 1,
    title: "锚点",
    status: "confirmed",
    prose: first,
    word_count: words(first),
    archived: true,
  };
  return { project, volumes, tree, readiness, chapterDetail };
})();

function stubPreviewAPI(page: Page) {
  page.route("**/api/**", (r) => r.fulfill({ json: {} })); // 兜底：未预期请求静默空对象
  page.route("**/api/auth/verify", (r) =>
    r.fulfill({ json: { tier: "none", is_member: false, expired: false, trial_remaining_days: 0 } }),
  );
  page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
  page.route(`**/api/novels/${PID}`, (r) => r.fulfill({ json: SEED.project }));
  page.route(`**/api/novels/${PID}/volumes`, (r) => r.fulfill({ json: SEED.volumes }));
  page.route(`**/api/novels/${PID}/tree`, (r) => r.fulfill({ json: SEED.tree }));
  page.route(`**/api/novels/${PID}/readiness`, (r) => r.fulfill({ json: SEED.readiness }));
  page.route(`**/api/novels/${PID}/chapters/vol-1-ch-1`, (r) =>
    r.fulfill({ json: SEED.chapterDetail }),
  );
  page.route("**/api/genres/candidates", (r) => r.fulfill({ json: {} }));
  page.route(`**/api/v1/novels/${PID}/ai-model`, (r) =>
    r.fulfill({
      json: {
        api_config_id: "c1",
        model: "gpt-4o",
        config_name: "主配置",
        ai_state: "ready",
        effective_model: "gpt-4o",
        reason: "ready",
        message: "已就绪",
      },
    }),
  );
  page.route("**/api/v1/api-configs", (r) => r.fulfill({ json: [] }));
  page.route(`**/api/novels/${PID}/workflow/phase-status`, (r) =>
    r.fulfill({
      json: {
        phases: { settings: "in_progress", outline: "in_progress", prompt: "pending", write: "pending", archive: "pending" },
      },
    }),
  );
}

/** PNG 比对 + 三张基线图落盘，返回差异率（断言归调用方）。 */
function compareShots(protoShot: Buffer, appShot: Buffer, base: string): number {
  const a = PNG.sync.read(protoShot);
  const b = PNG.sync.read(appShot);
  if (a.width !== b.width || a.height !== b.height) {
    throw new Error(
      `截图尺寸不一致（结构差异）：原型 ${a.width}x${a.height} vs 应用 ${b.width}x${b.height}`,
    );
  }
  const diff = new PNG({ width: a.width, height: a.height });
  const diffCount = pixelmatch(a.data, b.data, diff.data, a.width, a.height, {
    threshold: 0.1,
  });
  fs.mkdirSync(BASELINE_DIR, { recursive: true });
  fs.writeFileSync(path.join(BASELINE_DIR, `${base}.proto.png`), protoShot);
  fs.writeFileSync(path.join(BASELINE_DIR, `${base}.app.png`), appShot);
  fs.writeFileSync(path.join(BASELINE_DIR, `${base}.diff.png`), PNG.sync.write(diff));
  return diffCount / (a.width * a.height);
}

test.describe("design-parity 阅读预览屏（preview.html）", () => {
  test.skip(
    !RUN_PARITY || !fs.existsSync(PROTO_FILE),
    !RUN_PARITY ? "仅 design:check 运行（DESIGN_PARITY=1）" : "原型缺失：docs/design-c/ 为本地资产",
  );

  test("preview · 三栏阅读器", async ({ browser }) => {
    // ── 原型侧（设计真值；直接落在预览视图）──────────
    const protoCtx = await browser.newContext({ viewport: VIEWPORT });
    const protoPage = await protoCtx.newPage();
    await protoPage.goto(`file://${PROTO_FILE}`);
    await protoPage.evaluate(() => document.fonts.ready);
    // 帧位标定（design-parity-book 同款）：固定等待锁定确定性采样帧
    await protoPage.waitForTimeout(700);
    const protoShot = await protoPage.screenshot();
    await protoCtx.close();

    // ── 应用侧（打桩固定数据；modnav 点「预览」进三栏）──
    const appCtx = await browser.newContext({ viewport: VIEWPORT });
    await appCtx.addInitScript(() => {
      localStorage.setItem("auth_token", "parity-stub-token");
      localStorage.setItem("auth_username", "modoojunko"); // 与原型头像首字一致（像素级比对）
    });
    const appPage = await appCtx.newPage();
    stubPreviewAPI(appPage);
    await stubUpdateNotice(appPage, "update");
    await appPage.route("**/api/auth/config", (r) => r.fulfill({ json: { portal_url: "" } }));
    await appPage.goto(`/#/novel/${PID}`);
    await appPage.waitForSelector(".chtab", { timeout: 10000 });
    const proseLoaded = appPage.waitForResponse(`**/api/novels/${PID}/chapters/vol-1-ch-1`);
    await appPage.locator(".modnav button", { hasText: "预览" }).click();
    await proseLoaded;
    await appPage.waitForSelector('[data-testid="preview-prose"]');
    await appPage.waitForLoadState("networkidle");
    await appPage.evaluate(() => document.fonts.ready);
    // 帧位标定（同款）：page-enter 0.4s 收敛后采样
    await appPage.waitForTimeout(700);
    const appShot = await appPage.screenshot();
    await appCtx.close();

    // ── 比对（全窗口；基线落 docs/design-c/baselines）──
    const ratio = compareShots(protoShot, appShot, "preview.reader");
    expect(
      ratio,
      `像素差异率 ${(ratio * 100).toFixed(3)}%（阈值 0.2%）— 三张对比图见 docs/design-c/baselines/preview.reader.*`,
    ).toBeLessThan(MAX_DIFF_RATIO);
  });
});
