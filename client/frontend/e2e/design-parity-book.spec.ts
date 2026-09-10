// 设计一致性视觉比对 —— 书工作台屏（/#/novel/:id vs book.html）。
// 口径与 design-parity.spec.ts（书架）/ design-parity-config.spec.ts（模型配置）一致：
// 原型 file:// 注入 localStorage ainovel.book.v2 控状态（free=清除默认 / pro={pro:true}）；
// 应用侧打桩全量 API，数据与原型 buildBook() 种子逐字段对齐。
//
// 种子对齐要点（原型 → 应用 stub）：
//   卷/章标题：原型存整串「第一卷 · 星海初航」；应用 title 只存名称（nodeLabel 派生序号）
//   → stub title='星海初航'/'锚点'，渲染结果一致（novel-entity-name 口径）。
//   三态点：原型按 chGaps（未确认且有缺口=warn）；应用按章 status 派生
//   → c3/c4 stub status='in_progress' 落 dot-warn，与原型缺口的 warn 一致。
//   字数：正文段落数组 join 后去空白长度（countWords 同口径），运行时从 book.html
//   源码提取 PROSE_C1/C2，避免手抄漂移（C1=793 / C2=578 / 全书 1,371）。
//   免费态零 phase-status 请求；PRO 态 phase-status 非 all-pending（不弹 OnboardingCard）。
//   readiness：题材/简介/风格 done（3/7）＝原型 ITEMS 默认（genre/intro/style done），
//   modnav「设定 3/7」与设定视图左栏进度两侧一致。
//
// PR 4 新增三屏（screen 字段；原型 LS 不还原 preview 视图 → 统一运行时点击）：
//   volume：点卷行 → 卷纲面板（GET /volumes/vol-1 对齐 buildBook v1.og 全字段）。
//   settings：modnav 设定 → two-col 默认题材面板（GET /settings/genre → genre_id
//   + GET /genres/{id} 对齐 SET_GENRE；category 用 slug、label 派生「科幻系」）。
//   preview：modnav 预览 → 只读树 + 只读正文（初始章 = 写作视图当前章 vol-1-ch-1）。
import fs from "fs";
import path from "path";
import { test, expect, type Page } from "@playwright/test";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { stubUpdateNotice } from "./helpers";

const PROTO_FILE = path.resolve(process.cwd(), "../../docs/design-c/prototypes/book.html");
const BASELINE_DIR = path.resolve(process.cwd(), "../../docs/design-c/baselines");
const RUN_PARITY = process.env.DESIGN_PARITY === "1";
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 1 } as const;
const MAX_DIFF_RATIO = 0.002;
const PID = "p1";

/** 从 book.html 源码提取 PROSE_C1/C2 段落数组（原型正文种子，唯一事实源）。 */
function extractProse(): { c1: string[]; c2: string[] } {
  // 原型是 gitignored 本地资产：无 docs/design-c 的环境（如 CI）在模块加载期就会
  // 读文件——必须守卫，否则 import 即崩，下面的 test.skip(原型缺失) 永远到不了。
  if (!fs.existsSync(PROTO_FILE)) return { c1: [], c2: [] };
  const src = fs.readFileSync(PROTO_FILE, "utf-8");
  const grab = (name: string): string[] => {
    const m = src.match(new RegExp(`const ${name} = \\[([\\s\\S]*?)\\];`));
    if (!m) throw new Error(`book.html 中未找到 ${name}`);
    return JSON.parse(`[${m[1]}]`);
  };
  return { c1: grab("PROSE_C1"), c2: grab("PROSE_C2") };
}

// 与原型 countWords 同口径：去空白字符数
const words = (paras: string[]) => paras.join("\n").replace(/\s/g, "").length;

// ── 种子（与 buildBook() 逐字段对齐）──────────────────────────────────────
const SEED = (() => {
  const prose = extractProse();
  const w1 = words(prose.c1);
  const w2 = words(prose.c2);

  const project = {
    id: PID,
    name: "星海拾遗",
    type: "科幻",
    genre: "科幻",
    // 书内题材标签取值来源（新契约核心承诺 → 老书历史来源）：对齐原型 .genre-tag「科幻」
    genre_label: "科幻",
    source: "manual",
  };

  // GET /volumes（workbench 树：结构 + 字数 + 归档位）
  const volumes = [
    {
      ref: "vol-1",
      title: "星海初航",
      chapters: [
        { chapter: 1, title: "锚点", word_count: w1, status: "confirmed", has_prose: true, archived: false },
        { chapter: 2, title: "跃迁", word_count: w2, status: "confirmed", has_prose: true, archived: true },
        { chapter: 3, title: "回声", word_count: 0, status: "in_progress", has_prose: false, archived: false },
      ],
    },
    {
      ref: "vol-2",
      title: "星群之间",
      chapters: [
        { chapter: 4, title: "熄灭", word_count: 0, status: "in_progress", has_prose: false, archived: false },
      ],
    },
  ];

  // GET /tree（useOutline：三态点 + modnav 2/4 章纲）
  const tree = {
    volumes: volumes.map((v, vi) => ({
      ref: v.ref,
      title: v.title,
      summary: vi === 0 ? "废弃星港上，导航员沉舟捡到一枚不属于人类纪元的导航信标。" : "（摘要待补充）",
      chapter_count: v.chapters.length,
      has_prose: v.chapters.some((c) => c.has_prose),
      chapters: v.chapters.map((c) => ({
        ref: `${v.ref}-ch-${c.chapter}`,
        volume: vi + 1,
        chapter: c.chapter,
        title: c.title,
        status: c.status,
        word_count: c.word_count,
        has_prose: c.has_prose,
        archived: c.archived,
      })),
    })),
  };

  // GET /chapters/vol-1-ch-1（默认选中章：章纲已确认 + 正文 793 字）
  const chapter = {
    volume: 1,
    chapter: 1,
    title: "锚点",
    status: "confirmed",
    outline: {
      summary: "信标点亮，沉舟决定沿着信号追踪它的来处。",
      key_points: ["信标亮起，节奏像呼吸", "通讯指示灯跟着信号明灭", "「拾荒者」旧船的关联"],
      characters: ["沉舟"],
      location: "废弃星港 · 观测舱",
      time: "第七年最后一天",
      narrative_pov: "第三人称有限",
      perspective_guidance: "",
    },
    memo: {
      current_task: "建立「回声」悬念：让读者与沉舟一起看见信标，并想知道信号的源头。",
      reader_expectation: {
        state: "被精准的信号节奏勾起好奇，尚不知信标与旧船的关联。",
        strategy: "感官先行 + 克制揭示：只给现象，不给解释。",
        detail: "",
      },
      payoff_plan: {
        must_resolve: ["舷窗裂纹的意象成立"],
        must_hold: ["信标来源成谜"],
        partial_advance: ["修船过程可部分推进"],
      },
      required_changes: ["沉舟从旁观者变成行动者（决定修船出发）。"],
      prohibitions: ["不揭示信标制造者身份"],
    },
    emotional_design: { primary_mood: "压抑" },
    segments: [
      { summary: "港区之夜：信标亮起", target_words: 1200 },
      { summary: "修船与出发决定", target_words: 800 },
    ],
    prose: prose.c1.join("\n"),
    word_count: w1,
    archived: false,
  };

  // GET /readiness：题材/简介/风格 done → 设定 3/7（＝原型 ITEMS 默认）
  const readiness = {
    missing: ["world", "anti-ai", "hooks", "characters"].map((key) => ({ key })),
  };

  // GET /volumes/vol-1（卷纲面板：buildBook v1.og 全字段；chapters 供「去配章纲」）
  const volumeDetail = {
    ref: "vol-1",
    volume: 1,
    title: "星海初航",
    summary: "废弃星港上，导航员沉舟捡到一枚不属于人类纪元的导航信标。",
    direction_method: "template",
    template_name: "悬疑递进",
    core_conflict: "人类与回声源头的相遇：信任还是提防",
    emotional_arc: "从压抑到爆发，结尾留悬念",
    arc_mode: "层层逼近",
    primary_drive: "信息差",
    info_gap_start: "信标与沉舟的身世有关（读者知道、角色不知）",
    info_gap_end: "回声的源头浮出：一个等待三百年的同类",
    chapter_target: 4,
    stages: [
      { stage_name: "建立悬念", stage_function: "信标出现，节奏像呼吸；修船的决定成形", chapter_count: 3 },
      { stage_name: "首次揭示", stage_function: "旧船与信标的关联浮出水面", chapter_count: 1 },
    ],
    conflict_ladders: [
      { layer_no: 1, chapters_range: "第1-2章", obstacle: "港区资源枯竭，修船无门", turning_type: "信息转折", turning_point: "指示灯随信号明灭" },
      { layer_no: 2, chapters_range: "第3-4章", obstacle: "跃迁不可逆，退路被拆除", turning_type: "状态转折", turning_point: "锚点信号衰减" },
    ],
    chapter_plans: [
      { chapter_no: 1, title: "锚点", summary: "信标点亮，沉舟决定沿着信号追踪它的来处", emotional_anchor: "好奇与不安", info_gap: "信标与身世有关（读者知、角色不知）", arc_position: "开端" },
      { chapter_no: 2, title: "跃迁", summary: "点火与代价：亲手拆掉自己的锚点", emotional_anchor: "壮阔后的失落", info_gap: "坐标尽头是什么（未知）", arc_position: "推进" },
    ],
    character_voices: [
      { character_name: "沉舟", situation: "修好旧船驶离星港，退路已断", unfinished: "回声的源头仍未确认", interlude_thought: "七年寂静，换一次出发", next_action: "沿信号寻找源头" },
    ],
    chapters: volumes[0].chapters.map((c) => ({
      ref: `vol-1-ch-${c.chapter}`,
      volume: 1,
      chapter: c.chapter,
      title: c.title,
      status: c.status,
      word_count: c.word_count,
      has_prose: c.has_prose,
      outline_status: c.status,
      archived: c.archived,
    })),
  };

  // 设定视图·题材面板（默认面板）：GET /settings/genre → 五字段契约（D19 关系化）
  const genreSetting = {
    core_promise: "以弱破强的痛快",
    promise_note: "读者要看到弱者用脑子翻盘",
    forbidden_list: [{ tagId: "forbidden:no-deus-ex-machina" }],
    cost_ratio: 8,
    battlefield: ["battlefield:resources", "battlefield:status"],

  };
  const genreDef = {
    id: "deep-space",
    name: "深空探索",
    description: "以航程与未知为核心的科幻：技术精确、情绪克制。",
    category: "scifi",
    narratorRole: "第三人称有限视角叙述者",
    typicalArc: "收到信号，就一定要走到信号的尽头。",
    toneBlueprint: {
      defaultTone: "克制冷静、情绪靠细节外化",
      atmosphereOptions: ["冷寂", "克制", "悬念感"],
      povOptions: ["第三人称有限视角"],
      techniqueTags: ["动作外化情绪", "物件锚点复现"],
    },
    taboos: ["超光速通讯", "无代价跃迁", "万能翻译器"],
    promptInjection: "写作时保持冷寂克制的科幻质地：技术细节精确但不炫技；情绪让位于氛围；避免热血化表达。",
    genreConfig: {
      fulfillmentTypes: ["发现真相的瞬间", "沉默中的微小决断", "绝境中的精确操作"],
      chapterTypes: ["场景章（一段航程/一处星域）", "揭示章", "抉择章"],
      pacingRules: ["每章至少一个变化", "每三章一次小揭示"],
      fatigueWords: ["突然", "瞬间", "仿佛"],
    },
    storyArcTemplates: [
      { id: "arc-signal", name: "追寻弧线", description: "收到信号，就一定要走到信号的尽头。", beats: ["收到信号", "出发", "找到源头", "代价与选择"] },
      { id: "arc-mirror", name: "镜像弧线", description: "以为在找别人，其实在找自己。", beats: ["接到信号", "镜像事件", "自我揭示", "和解"] },
    ],
    isPreset: true,
  };

  return { project, volumes, tree, chapter, readiness, volumeDetail, genreSetting, genreDef };
})();

// parity 只取免费态：PRO 态右栏续写/润色/扩写为产品真实工具行（换皮不减功能），
// 原型标「规划中」——已登记 ADJUSTMENTS.md（PR 3「未动原型」清单，parity 态取免费版）。
// screen：workbench=默认章工作台 / volume=卷纲面板 / settings=设定视图 / preview=预览视图。
// PR 5 追加弹窗三态（免费态）：modal-delete=树删章分级确认 / modal-prefs=本书偏好 /
// modal-upgrade=右栏 locked 卡升级 PRO；两侧同路径打开弹窗后整页比对（遮罩+弹窗）。
const CASES = [
  { state: "free", pro: false, screen: "workbench" },
  { state: "volume", pro: false, screen: "volume" },
  { state: "settings", pro: false, screen: "settings" },
  { state: "preview", pro: false, screen: "preview" },
  { state: "modal-delete", pro: false, screen: "modal-delete" },
  { state: "modal-prefs", pro: false, screen: "modal-prefs" },
  { state: "modal-upgrade", pro: false, screen: "modal-upgrade" },
] as const;

test.describe("design-parity 书工作台屏（book.html）", () => {
  test.skip(
    !RUN_PARITY || !fs.existsSync(PROTO_FILE),
    !RUN_PARITY ? "仅 design:check 运行（DESIGN_PARITY=1）" : "原型缺失：docs/design-c/ 为本地资产"
  );

  for (const c of CASES) {
    test(`${c.state} · ${c.screen}`, async ({ browser }) => {
      // ── 原型侧（设计真值；free=默认种子，pro=LS 覆写）──────────
      const protoCtx = await browser.newContext({ viewport: VIEWPORT });
      await protoCtx.addInitScript((pro) => {
        if (pro) localStorage.setItem("ainovel.book.v2", JSON.stringify({ pro: true }));
        else localStorage.removeItem("ainovel.book.v2");
      }, c.pro);
      const protoPage = await protoCtx.newPage();
      await protoPage.goto(`file://${PROTO_FILE}`);
      await protoPage.evaluate(() => document.fonts.ready);
      await protoPage.waitForTimeout(700);
      // 屏内交互（原型 LS 仅还原 settings/outline 视图 → 统一运行时点击，两侧对称）
      if (c.screen === "volume") {
        await protoPage.locator(".vol-head .vt").first().click();
      } else if (c.screen === "settings") {
        await protoPage.locator('.mtab[data-view="settings"]').click();
      } else if (c.screen === "preview") {
        await protoPage.locator('.mtab[data-view="preview"]').click();
      } else if (c.screen === "modal-delete") {
        // 树首个章行（c1 锚点：confirmed + 正文）hover → 删除 → 分级确认弹窗
        const row = protoPage.locator(".ch").first();
        await row.hover();
        await row.locator('[data-act="del"]').click();
      } else if (c.screen === "modal-prefs") {
        // 面板「本书偏好」项（c-account-control-center：appbar 设置按钮已收敛）
        await protoPage.locator("#btnAcct").click();
        await protoPage.locator("#amBookPrefs").click();
      } else if (c.screen === "modal-upgrade") {
        // 免费态右栏 AI locked 卡的「升级 PRO」——默认选中章 → 章栏 #btnUpgrade3
        // （#btnUpgrade2 在卷选中栏 #railVolume 内，默认 hidden 不可点）
        await protoPage.locator("#btnUpgrade3").click();
      }
      await protoPage.waitForTimeout(400);
      const protoShot = await protoPage.screenshot();
      await protoCtx.close();

      // ── 应用侧（打桩固定数据；默认写作视图 + 初次自动选中第一章·章纲）──
      const appCtx = await browser.newContext({ viewport: VIEWPORT });
      await appCtx.addInitScript(() => {
        localStorage.setItem("auth_token", "parity-stub-token");
        localStorage.setItem("auth_username", "modoojunko"); // 与原型头像首字一致（像素级比对）
      });
      const appPage = await appCtx.newPage();
      stubBookAPI(appPage, c.pro, c.screen === "volume");
      // 原型常显更新提示条（ADJUSTMENTS #15）→ 应用侧同文案打桩（沉浸全宽变体）
      await stubUpdateNotice(appPage, "update");
      // /auth/config（portal_url 公开地址）在新栈 backend 会 401 并触发全局跳 /#/login，就地打桩防弹离
      await appPage.route("**/api/auth/config", (r) => r.fulfill({ json: { portal_url: "" } }));
      await appPage.goto(`/#/novel/${PID}`);
      await appPage.waitForSelector(".chtab", { timeout: 10000 });
      if (c.screen === "volume") {
        const volLoaded = appPage.waitForResponse(`**/api/novels/${PID}/volumes/vol-1`);
        await appPage.locator(".vol-head .vt").first().click();
        await volLoaded;
        await appPage.waitForSelector(".col-middle .panel-head h2");
      } else if (c.screen === "settings") {
        // 等待须先于点击注册：挂载即发请求，响应可能先于 await 返回。
        // tasks 2.1 起设定视图默认落「简介」（SETTINGS_ITEMS[0]）→ 等 story
        const storyLoaded = appPage.waitForResponse(`**/api/novels/${PID}/story`);
        await appPage.locator(".modnav button", { hasText: "设定" }).click();
        await storyLoaded;
        await appPage.waitForSelector(".settings-v main h2");
      } else if (c.screen === "preview") {
        const proseLoaded = appPage.waitForResponse(
          `**/api/novels/${PID}/chapters/vol-1-ch-1`,
        );
        await appPage.locator(".modnav button", { hasText: "预览" }).click();
        await proseLoaded;
        await appPage.waitForSelector(".pv-title");
      } else if (c.screen === "modal-delete") {
        // 首章（vol-1-ch-1 锚点，confirmed + 793 字）hover → 删除 → 删除确认弹窗
        const row = appPage.locator(".col-tree .ch").first();
        await row.hover();
        await row.getByTitle("删除章节").click();
        await appPage.waitForSelector(".modal .mcard");
      } else if (c.screen === "modal-prefs") {
        // 触发钮 → 面板「本书偏好」→ 本书偏好弹窗（verify 打桩为免费态）
        await appPage.locator('[data-od-id="acct-trigger"]').click();
        await appPage.locator('[data-od-id="acct-menu-bookprefs"]').click();
        await appPage.waitForSelector(".modal .mcard");
      } else if (c.screen === "modal-upgrade") {
        // 免费态右栏 ai-locked 卡「升级 PRO」→ 升级弹窗
        await appPage.locator(".ai-locked .btn-primary").click();
        await appPage.waitForSelector(".modal .mcard");
      }
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
      const base = `book.${c.state}`;
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.proto.png`), protoShot);
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.app.png`), appShot);
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.diff.png`), PNG.sync.write(diff));
      const ratio = diffCount / (a.width * a.height);
      if (c.screen === "settings") {
        // tasks 9.3.6：题材/简介面板改六格后，原型 book.html 的设定段尚未转正
        // （设计事实源已迁 docs/design-c/prototypes/genre-signup.html）——
        // 基线重生成随 1.1 原型转正，本 change 的 e2e 不以 parity 为门禁。
        test.skip(
          true,
          `设定屏 parity 基线待随原型转正重生成（当前差异 ${(ratio * 100).toFixed(3)}%）`,
        );
        return;
      }
      expect(
        ratio,
        `像素差异率 ${(ratio * 100).toFixed(3)}%（阈值 0.2%）— 三张对比图见 docs/design-c/baselines/${base}.*`
      ).toBeLessThan(MAX_DIFF_RATIO);
    });
  }
});

/** 打桩书工作台全量 API（先注册兜底，后注册具体 → 具体优先）。 */
// PR6 信息差对齐：章纲面板新增只读信息差块（原型未建模的功能增强，ADJUSTMENTS
// 登记，parity 不覆盖）。volume case 的卷纲面板本身有信息差字段需保留值；
// 其余 case（章工作台可见/半可见于遮罩下）用 gapless 变体 → 块不渲染，与原型一致。
const volumeDetailGapless = {
  ...SEED.volumeDetail,
  info_gap_start: "",
  info_gap_end: "",
  chapter_plans: SEED.volumeDetail.chapter_plans.map((p) => ({
    ...p,
    info_gap: "",
  })),
};

function stubBookAPI(page: Page, pro: boolean, volumeGap = false) {
  page.route("**/api/**", (r) => r.fulfill({ json: {} })); // 兜底：未预期请求静默空对象
  page.route(
    "**/api/auth/verify",
    (r) =>
      r.fulfill({
        json: pro
          ? { tier: "monthly", is_member: true, expired: false, trial_remaining_days: 0 }
          : { tier: "none", is_member: false, expired: false, trial_remaining_days: 0 },
      }),
  );
  page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
  page.route(`**/api/novels/${PID}`, (r) => r.fulfill({ json: SEED.project }));
  page.route(`**/api/novels/${PID}/volumes`, (r) => r.fulfill({ json: SEED.volumes }));
  page.route(`**/api/novels/${PID}/volumes/vol-1`, (r) =>
    r.fulfill({ json: volumeGap ? SEED.volumeDetail : volumeDetailGapless }),
  );
  page.route(`**/api/novels/${PID}/tree`, (r) => r.fulfill({ json: SEED.tree }));
  page.route(`**/api/novels/${PID}/readiness`, (r) => r.fulfill({ json: SEED.readiness }));
  page.route(`**/api/novels/${PID}/chapters/vol-1-ch-1`, (r) => r.fulfill({ json: SEED.chapter }));
  // 设定视图·题材面板（默认面板）：已设定题材 = 原型 SET_GENRE（深空探索）
  page.route(`**/api/novels/${PID}/settings/genre`, (r) => r.fulfill({ json: SEED.genreSetting }));
  // 题材候选源（面板挂载即拉）+ 本书 AI 就绪态（D13，SettingsView 取 ai_state）
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
  // PRO 态：非 all-pending（不弹 OnboardingCard；原型 pro 态无催促卡）
  page.route(`**/api/novels/${PID}/workflow/phase-status`, (r) =>
    r.fulfill({
      json: {
        phases: {
          settings: "in_progress",
          outline: "in_progress",
          prompt: "pending",
          write: "pending",
          archive: "pending",
        },
      },
    })
  );
}
