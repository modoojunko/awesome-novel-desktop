#!/usr/bin/env node
/**
 * verify-kb-proto.cjs —— 写作知识库原型动态验证＋逐场景截图。
 * 用法：node docs/design-c/drafts/kb-captures/verify-kb-proto.cjs
 * 结构：L0 元模型 → L1 六概念（文风/文笔/世界设定/角色设定/手法/情节）
 *       → L2 题材实例（21 个题材目录）→ L3 库 → L4 消费；全局图默认＋Lab。
 * 断言：题材左栏、六概念筛选、搜索、库页（文风 2 / 文笔 4 / 角色 2）、
 *       抽屉、派生流程已移除、书内双来源行、无报错/无横向溢出。
 */
const path = require("path");
const { pathToFileURL } = require("url");
const CAPS = __dirname;
const DRAFTS = path.dirname(CAPS);
const ROOT = path.dirname(path.dirname(path.dirname(DRAFTS)));
const FILE = path.join(DRAFTS, "ai-novel-c端-写作知识库-原型.html");
const { chromium } = require(path.join(ROOT, "client/frontend/node_modules/playwright"));

const fails = [];
function check(name, cond, detail) {
  console.log((cond ? "ok   " : "FAIL ") + name + (detail ? " · " + detail : ""));
  if (!cond) fails.push(name);
}

(async () => {
  const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  await page.goto(pathToFileURL(FILE).href);
  await page.waitForTimeout(500);
  const txt = async (s) => (await page.textContent(s)).trim();

  check("① 首页标题", (await page.textContent("h1")).trim() === "知识库");
  check("① 题材栏 22 项", (await page.locator(".grail button").count()) === 22);
  check("① 仙侠/修真 24 条", (await page.locator("#entryRows .erow").count()) === 24);
  check("① 仙侠/修真 5 库", (await page.locator("#libGrid .libcard").count()) === 5);
  check("① 5 张库卡（无新增入口）", (await page.locator("#libGrid .libcard").count()) === 5);
  check("① 无横向溢出", (await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) === 0);
  await page.screenshot({ path: path.join(CAPS, "1-home.png"), fullPage: true });

  await page.click('#typeTabs button[data-type="文笔"]');
  await page.waitForTimeout(120);
  check("① 文笔 4", (await page.locator("#entryRows .erow").count()) === 4);
  await page.click('#typeTabs button[data-type="文风"]');
  await page.waitForTimeout(120);
  check("① 文风 2", (await page.locator("#entryRows .erow").count()) === 2);
  await page.click('#typeTabs button[data-type="角色设定"]');
  await page.waitForTimeout(120);
  check("① 角色 2", (await page.locator("#entryRows .erow").count()) === 2);
  await page.click('#typeTabs button[data-type="全部"]');
  await page.click('.grail button[data-genre="都市"]');
  await page.waitForTimeout(120);
  check("① 都市 2 条", (await page.locator("#entryRows .erow").count()) === 2);
  check("① 都市 2 库", (await page.locator("#libGrid .libcard").count()) === 2);
  await page.click('.grail button[data-genre="全部题材"]');
  await page.waitForTimeout(120);
  check("① 全部题材 28 条", (await page.locator("#entryRows .erow").count()) === 28);
  check("① 全部题材 9 库 4 组", (await page.locator("#libGrid .libcard").count()) === 9 && (await page.locator("#libGrid .libgroup").count()) === 4);
  await page.click('.grail button[data-genre="体育"]');
  await page.waitForTimeout(120);
  check("① 空题材库空态", (await page.locator("#libGrid .libempty").count()) === 1);
  await page.click('.grail button[data-genre="仙侠/修真"]');
  await page.waitForTimeout(120);
  await page.fill("#search", "断剑");
  await page.waitForTimeout(120);
  check("① 搜索 2", (await page.locator("#entryRows .erow").count()) === 2);
  await page.fill("#search", "");
  await page.waitForTimeout(100);

  // 文风库
  await page.click('#libGrid .libcard[data-lib="l5"]');
  await page.waitForTimeout(200);
  check("② 文风库标题", (await txt("#libTitle")) === "文风库");
  check("② 文风库 2 成员", (await page.locator("#libMembers .mrow").count()) === 2);
  await page.screenshot({ path: path.join(CAPS, "2a-wenfeng.png"), fullPage: true });

  // 文笔库
  await page.click("#backHome");
  await page.waitForTimeout(120);
  await page.click('#libGrid .libcard[data-lib="l2"]');
  await page.waitForTimeout(200);
  check("② 文笔库标题", (await txt("#libTitle")) === "文笔库");
  check("② 文笔库 4 成员", (await page.locator("#libMembers .mrow").count()) === 4);
  await page.screenshot({ path: path.join(CAPS, "2-library.png"), fullPage: true });

  await page.click("#libMembers .mrow");
  await page.waitForTimeout(350);
  check("③ 抽屉打开", (await page.locator("#drawer.open").count()) === 1);
  await page.screenshot({ path: path.join(CAPS, "3-drawer.png") });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  check("③ Esc 关闭", (await page.locator("#drawer.open").count()) === 0);

  check("④ 派生已移除", (await page.locator("#deriveModal").count()) === 0 && (await page.locator('[data-scene="derive"]').count()) === 0 && (await page.locator(".libcard.new").count()) === 0);
  await page.click('#demoChips button[data-scene="home"]');
  await page.waitForTimeout(300);

  await page.waitForTimeout(2400);
  await page.click('#libGrid .libcard[data-lib="l4"]');
  await page.waitForTimeout(250);
  check("② 角色设定库 2 成员", (await page.locator("#libMembers .mrow").count()) === 2);
  check("② 起草型按钮", (await txt("#enableBtn span")) === "开启使用");
  await page.screenshot({ path: path.join(CAPS, "2b-role-library.png") });

  await page.click('#demoChips button[data-scene="inbook"]');
  await page.waitForTimeout(250);
  check("⑤ 6 个文风/文笔槽", (await page.locator("#inbookSlots .slotrow").count()) === 6);
  check("⑤ 6 条手法", (await page.locator("#inbookChips .chip").count()) === 6);
  check("⑤ 双来源行", (await page.locator(".srcline .status").count()) === 2);
  await page.screenshot({ path: path.join(CAPS, "5-inbook.png"), fullPage: true });

  // ⑥ 知识星图（单视图星系：黑洞 + 21 题材 + 全部概念/子概念/条目）
  await page.click('#demoChips button[data-scene="home"]');
  await page.waitForTimeout(150);
  await page.click('[data-view="star"]');
  await page.waitForTimeout(400);
  check("⑥ 首页星图切换", await page.isVisible("#sceneStar"));
  await page.click('#demoChips button[data-scene="star"]');
  await page.waitForTimeout(3000);
  check("⑥ 全局图默认", await page.evaluate(() => document.querySelector(".star-shell").classList.contains("graph-mode")) && (await page.locator("#graph2d canvas").count()) === 1);
  check("⑥ 全局图统计", (await txt("#g2dStat")).startsWith("80 节点 · 6 概念 · 21 题材"), await txt("#g2dStat"));
  await page.fill("#g2dSearch", "断剑");
  await page.waitForTimeout(600);
  check("⑥ 全局图搜索", parseInt(await txt("#g2dStat"), 10) < 80 && (await txt("#g2dStat")).includes("节点"), await txt("#g2dStat"));
  await page.fill("#g2dSearch", "");
  await page.waitForTimeout(600);
  check("⑥ 全局图空枝开关", await page.isVisible("#g2dEmpty"));
  await page.screenshot({ path: path.join(CAPS, "6-star.png") });
  await page.click('[data-starview="dandelion"]');
  await page.waitForTimeout(3200);
  check("⑥ 蒲公英视图", await page.isVisible("#star3d") && await page.evaluate(() => document.querySelector(".star-shell").classList.contains("dandelion-mode")));
  check("⑥ 蒲公英 360° 辐条", await page.evaluate(() => {
    const ys = window.__star.nodes().filter((n) => n.level === 0).map((n) => n.y);
    return Math.max(...ys) - Math.min(...ys) > 400;
  }));
  check("⑥ 每个点都有中心辐条", (await page.evaluate(() => window.__star.rays())) === 79);
  await page.screenshot({ path: path.join(CAPS, "6-star.png") });
  await page.click('[data-starview="brain"]');
  await page.waitForTimeout(5200);
  check("⑥ 大脑视图", await page.isVisible("#brainFrame"));
  const bf = page.frameLocator("#brainFrame");
  const bfText = await bf.locator("body").innerText();
  check("⑥ 大脑题材镜头", bfText.includes("仙侠/修真") && bfText.includes("未建树题材"), bfText.slice(0, 40));
  check("⑥ 大脑概念卡", bfText.includes("文风") && bfText.includes("手法"));
  await page.screenshot({ path: path.join(CAPS, "6b-brain.png") });
  const bframe = page.locator("#brainFrame");
  const bbefore = await bframe.screenshot();
  const bbox = await bframe.boundingBox();
  await page.mouse.move(bbox.x + bbox.width * 0.5, bbox.y + bbox.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(bbox.x + bbox.width * 0.5 + 110, bbox.y + bbox.height * 0.5 - 90, { steps: 14 });
  await page.mouse.up();
  await page.waitForTimeout(700);
  check("⑥ 大脑可旋转", !bbefore.equals(await bframe.screenshot()));
  await page.click('[data-starview="relations"]');
  await page.waitForTimeout(2400);
  check("⑥ 切关系图", await page.isVisible("#star3d"));
  await page.screenshot({ path: path.join(CAPS, "6b-relations.png") });
  check("⑥ 全展开统计", (await txt("#starStats")).startsWith("21 题材 · 4 已建树 / 17 空枝 · 10 概念 · 20 子概念 · 28 条目"), await txt("#starStats"));
  check("⑥ 题材下拉 22 项", (await page.locator("#starGenreSelect option").count()) === 22);
  check("⑥ 黑洞核心", await page.evaluate(() => window.__star.hasBlackHole()));
  check("⑥ 80 节点同屏", (await page.evaluate(() => window.__star.nodes().length)) === 80);
  check("⑥ 全部题材同屏", await page.evaluate(() => {
    const ids = window.__star.nodes().map((n) => n.id);
    return ["g:都市", "c:仙侠:文风", "k10"].every((id) => ids.includes(id));
  }));
  check("⑥ 题材不是死层级", await page.evaluate(() => {
    const gs = window.__star.nodes().filter((n) => n.level === 0);
    return new Set(gs.map((n) => Math.round(n.y / 10))).size > 5;
  }));
  check("⑥ 3D 库就位", (await page.evaluate(() => typeof window.ForceGraph3D === "function" && !!window.THREE)));
  check("⑥ 3D canvas 就位", (await page.locator("#star3d canvas").count()) === 1);
  await page.screenshot({ path: path.join(CAPS, "6-star.png") });
  await page.evaluate(() => window.__star.focus("仙侠/修真"));
  await page.waitForTimeout(1400);
  check("⑥ 聚焦题材", (await txt("#starDetail h2")) === "仙侠/修真");
  check("⑥ 聚焦后概念名", (await page.evaluate(() => window.__star.labelsInfo().visible)) === 6);
  await page.screenshot({ path: path.join(CAPS, "6b-star-focus.png") });
  await page.evaluate(() => window.__star.select("k10"));
  await page.waitForTimeout(150);
  check("⑥ 点条目出属性", (await txt("#starDetail h2")) === "叙事身份");
  await page.evaluate(() => window.__star.select("c:仙侠:文风"));
  await page.waitForTimeout(150);
  check("⑥ 点概念出 schema", (await txt("#starDetail h2")) === "文风" && (await page.textContent("#starDetail")).includes("属性 schema"));
  await page.screenshot({ path: path.join(CAPS, "6b-star-node.png") });
  await page.evaluate(() => window.__star.selectEdge(window.__star.firstOntology()));
  await page.waitForTimeout(150);
  check("⑥ 点概念关系", (await page.textContent("#starDetail")).includes("通道") && (await page.textContent("#starDetail")).includes("关系类型"));
  await page.screenshot({ path: path.join(CAPS, "6c-star-edge.png") });
  check("⑥ AI 关系来源", (await page.textContent("#starDetail")).includes("AI 整理") && (await page.textContent("#starDetail")).includes("置信"));
  check("⑥ AI 整理状态", (await txt("#starAiText")).includes("AI 整理"));
  await page.click('[data-ai-open="1"]');
  await page.waitForTimeout(200);
  check("⑥ AI 整理记录", await page.isVisible("#starAiModal"));
  await page.screenshot({ path: path.join(CAPS, "6d-star-ai.png") });
  await page.click("#starAiRun");
  await page.waitForTimeout(2200);
  check("⑥ AI 整理完成", (await txt("#starAiText")).includes("刚刚"));
  await page.click('[data-ai-close="1"]');
  await page.evaluate(() => window.__star.focus("都市"));
  await page.waitForTimeout(900);
  check("⑥ 聚焦都市", (await txt("#starDetail h2")) === "都市");
  await page.evaluate(() => window.__star.focus("体育"));
  await page.waitForTimeout(700);
  check("⑥ 空题材也是空枝", (await txt("#starDetail h2")) === "体育" && (await page.textContent("#starDetail")).includes("还没有建树"));
  await page.evaluate(() => window.__star.reset());
  await page.waitForTimeout(700);
  check("⑥ 回全部题材", (await txt("#starDetail h2")) === "全部题材");
  await page.click('[data-slevel="entries"]');
  await page.waitForTimeout(250);
  check("⑥ 隐条目", (await txt("#starStats")).startsWith("21 题材 · 4 已建树 / 17 空枝 · 10 概念 · 20 子概念 · 0 条目"), await txt("#starStats"));
  await page.click('[data-slevel="entries"]');
  await page.waitForTimeout(200);
  await page.click('[data-sconcept="手法"]');
  await page.waitForTimeout(250);
  check("⑥ 概念筛选生效", !(await txt("#starStats")).startsWith("21 题材 · 4 已建树 · 10 概念"), await txt("#starStats"));
  await page.click('[data-sconcept="手法"]');

  // 镜头：上下左右旋转 + WASD 飞行（来自 Longwind1984/galaxy-view 的 CameraDirector）
  const cam0 = await page.evaluate(() => window.__star.cam());
  const sbox = await page.locator("#star3d").boundingBox();
  const scx = sbox.x + sbox.width * 0.55, scy = sbox.y + sbox.height * 0.55;
  await page.mouse.move(scx, scy);
  await page.mouse.down();
  await page.mouse.move(scx + 100, scy - 100, { steps: 14 });
  await page.mouse.up();
  await page.waitForTimeout(350);
  const cam1 = await page.evaluate(() => window.__star.cam());
  check("⑥ 上下左右可转", Math.hypot(cam1.x - cam0.x, cam1.y - cam0.y, cam1.z - cam0.z) > 40, JSON.stringify({ cam0, cam1 }));
  await page.mouse.click(scx, scy);
  await page.keyboard.down("w");
  await page.waitForTimeout(350);
  await page.keyboard.up("w");
  await page.waitForTimeout(200);
  const cam2 = await page.evaluate(() => window.__star.cam());
  check("⑥ WASD 飞行", Math.hypot(cam2.x - cam1.x, cam2.y - cam1.y, cam2.z - cam1.z) > 8, JSON.stringify({ cam1, cam2 }));
  await page.evaluate(() => window.__star.reset());
  await page.waitForTimeout(1400);

  check("无页面报错", errors.length === 0, errors.join(" | "));
  await browser.close();
  console.log(fails.length ? `\n${fails.length} FAIL` : "\nALL OK");
  process.exit(fails.length ? 1 : 0);
})();
