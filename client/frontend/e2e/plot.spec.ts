import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick, writeConfigAtomic } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// c-plot-split 章内剧情 e2e：剧情区手写编辑（加/写/删＋自动保存落库）／
// 右栏「剧情抽卡」三版抽卡（打桩；角标＋共用首尾）／采纳整表替换＋回执窗口内撤销／
// 免费锁定（rail-locked 置灰＋升级出口，手写剧情照常可用）。
// AI 端点 page.route 打桩；剧情真落库；断言走「不落库」后端直查。
// =========================================================================

// 隔离栈可参数化（per-session 规则：自己的 S端端口/数据目录）
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
  "config.json",
);

async function sRegisterAndLogin() {
  const name = `e2e_plot_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!";
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password, security_question: "最喜欢的颜色", security_answer: "蓝色" }),
  });
  const rb = await reg.json();
  if (rb.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(rb)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const lb = await login.json();
  if (lb.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(lb)}`);
  return { token: lb.data.token as string, username: name };
}

async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const fs = await import("fs");
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
  cfg.expires_at = tier === "none" ? "" : "2099-12-31";
  // 会话三件套（既有 spec 同款）：fresh last_login_at＋随机 pc_hash——真设备哈希会 401
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  // 后端会用内存态回写 config.json（既有 spec 的稳定轮询：写到自己这版连续两次不被覆盖）
  const mine = JSON.stringify(cfg, null, 2);
  const writeMine = () => writeConfigAtomic(CONFIG_PATH, mine);
  writeMine();
  for (let stable = 0, tries = 0; stable < 2 && tries < 10; tries++) {
    await new Promise((r) => setTimeout(r, 300));
    if (fs.readFileSync(CONFIG_PATH, "utf-8") === mine) stable += 1;
    else {
      writeMine();
      stable = 0;
    }
  }
  return { restore: async () => fs.writeFileSync(CONFIG_PATH, original) };
}

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const { restore } = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    await restore();
  };
  return { restore: restoreAndCleanup, token };
}

/** 建书 → 建第一卷（四问手写）→ 手写拆下一章（四段，顺带把门槛字段落库）→ 开章纲 */
async function createNovelWithChapter(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  await page.getByRole("button", { name: /^写作/ }).click();
  await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 15000 });
  await page.getByTestId("plan-first-volume").click();
  await expect(
    page.getByTestId("pick-modal").or(page.getByTestId("volume-plan-modal")),
  ).toBeVisible({ timeout: 10000 });
  if (await page.getByTestId("pick-modal").count()) {
    await page.getByText("自己答四个问题").first().click();
  }
  await expect(page.getByTestId("volume-plan-modal")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("q-what").fill("沉舟捡到一枚不属于人类纪元的导航信标");
  await page.getByTestId("q-conflict").fill("想自己查清，与得靠船队");
  await page.getByTestId("q-ant-type").selectOption("环境");
  await page.getByTestId("q-ant-line").fill("母港制度——信标要登记");
  await page.getByTestId("q-ending").fill("船头转向母港旧址");
  await page.getByTestId("desk-create").click();
  await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("landing-open-outline").click();
  // 手写拆下一章：四段落库（outline.summary/challenge/ladder_exit——AI 写剧情的门槛三样；c-og-slim-v2 去「本章行动」）
  // 拆章入口已迁本卷章节页签（c-split-to-chapters-tab）
  await page.getByRole("tab", { name: "本卷章节" }).click();
  await page.getByTestId("volume-split-manual").click();
  await expect(page.getByTestId("chapter-plan-modal")).toBeVisible({ timeout: 5000 });
  await page.getByTestId("d-title").fill("信标进舱");
  await page.getByTestId("d-plot").fill("沉舟在废弃星港捡到信标，先藏了下来");
  await page.getByTestId("d-obstacle").fill("没人相信一个见习导航员");
  await page.getByTestId("d-ending").fill("她把信标藏进舱底夹层");
  await page.getByTestId("split-adopt").click();
  await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("chapter-landing-outline").click();
  // 章纲页签就位：默认查看态载入完成 → 进编辑态（剧情区表单交互面；c-ch-og-readonly）
  await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("og-edit").click();
  await expect(page.locator('[data-od-id="plot-section"]')).toBeVisible({ timeout: 10000 });
  // 等章数据真载入（概要格子出现服务端值）再动键盘——慢栈上 load 响应可能晚于
  // 首帧 2s，占位态输入会在 load 完成时被 setOgForm 整表覆盖（存量竞态），白打
  await expect(page.locator("#wf-summary")).not.toHaveValue("", { timeout: 15000 });
  return m[1];
}

const ENTRY = "起——气闸合拢，她把信标藏进舱底夹层";
const EXIT = "止——船身一震，航向母港旧址（这一章到此收住）";
const THREE = {
  ok: true,
  versions: [
    { items: [ENTRY, "中段甲：稽查艇抵近，她交出半张禁航图换夜航窗口", EXIT] },
    { items: [ENTRY, "中段乙：她不理呼叫硬闯潮汐口，磁钩连脱两次", EXIT] },
    { items: [ENTRY, "中段丙：她把信标信号调上公共频道，反手谈条件", EXIT] },
  ],
  grades: ["S", "", "A"],
  warnings: [],
};

test("剧情区手写编辑全链：写一条/加一条/删一条，自动保存真落库", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithChapter(page, `剧情手写${Date.now() % 100000}`);
    // 空态＝直接一个空输入框（无引导卡）
    await expect(page.getByLabel("第 1 条剧情")).toHaveValue("");
    await page.getByLabel("第 1 条剧情").fill("她在观测舱认出信标的编号");
    await page.getByRole("button", { name: "加一条" }).click();
    await page.getByLabel("第 2 条剧情").fill("旧档堆不对活人开放，查档本身就要违规");
    // 自动保存（3s 防抖）后直查落库
    const H = { Authorization: `Bearer ${token}` };
    await expect
      .poll(
        async () =>
          (await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json())
            ?.plot_items ?? [],
        { timeout: 12000 },
      )
      .toEqual(["她在观测舱认出信标的编号", "旧档堆不对活人开放，查档本身就要违规"]);
    // 删第一条：留下的内容不丢、落库同步
    await page.getByLabel("删掉这一条").first().click();
    await expect(page.getByLabel("第 1 条剧情")).toHaveValue("旧档堆不对活人开放，查档本身就要违规");
    await expect
      .poll(
        async () =>
          (await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json())
            ?.plot_items ?? [],
        { timeout: 12000 },
      )
      .toEqual(["旧档堆不对活人开放，查档本身就要违规"]);
  } finally {
    await restore();
  }
});

test("抽卡三版：角标＋共用首尾；采纳整表替换（明示 N 条）＋回执窗口内撤销＋3 秒自动消失", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithChapter(page, `剧情抽卡${Date.now() % 100000}`);
    // 先手写 2 条（替换明示 N＝已写非空条数）
    await page.getByLabel("第 1 条剧情").fill("手写第一条");
    await page.getByRole("button", { name: "加一条" }).click();
    await page.getByLabel("第 2 条剧情").fill("手写第二条");
    // AI 端点打桩（真链路其余部分照走：门槛/保存/回执）
    await page.route("**/plot/ai-draw", (r) => r.fulfill({ json: THREE }));
    await page.getByTestId("og-plot-draw").click();
    await expect(page.getByTestId("plot-grid")).toBeVisible({ timeout: 10000 });
    // 三卡；角标只出有名字的（S＋A，缺名次不出）；S 带「最抓人」
    await expect(page.getByTestId("plot-card-0")).toBeVisible();
    await expect(page.getByTestId("plot-card-1")).toBeVisible();
    await expect(page.getByTestId("plot-card-2")).toBeVisible();
    await expect(page.locator(".pk-corner")).toHaveCount(2);
    await expect(page.locator(".pk-corner.g-S")).toContainText("最抓人");
    // 三版共用首尾（entry/exit 各出现 3 次）
    await expect(page.getByTitle(ENTRY)).toHaveCount(3);
    await expect(page.getByTitle(EXIT)).toHaveCount(3);
    // 未选不能采纳；选中后明示「将替换已写的 2 条」
    await expect(page.getByTestId("plot-adopt")).toBeDisabled();
    await page.getByTestId("plot-card-0").click();
    await expect(page.getByTestId("plot-adopt")).toContainText("将替换已写的 2 条");
    await page.getByTestId("plot-adopt").click();
    // 回执只活 3 秒窗口（c-toast-dismiss）：可见后立即点撤销，中间不得插入耗时轮询——
    // 采纳落库由回执可见传递性证明（saveChapter 成功才出回执），不再单独 poll
    await expect(page.getByText("剧情已由 AI 填好（3 条）")).toBeVisible({ timeout: 8000 });
    await page.getByRole("button", { name: "撤销 · 恢复填写前的列表" }).click();
    await expect(page.getByText("已恢复到 AI 填写前的列表")).toBeVisible();
    await expect(page.getByLabel("第 1 条剧情")).toHaveValue("手写第一条");
    // 撤销回写借 3s 自动保存；末尾轮询传递性证明「采纳落库＋撤销＋回写」全链
    const H = { Authorization: `Bearer ${token}` };
    await expect
      .poll(
        async () =>
          (await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json())
            ?.plot_items ?? [],
        { timeout: 12000 },
      )
      .toEqual(["手写第一条", "手写第二条"]);
    // 回执 3 秒自动消失基线：再采纳一版，不动它，等它自己走（× 关闭由 toast.test.tsx 单测钉）
    await page.getByTestId("og-plot-draw").click();
    await expect(page.getByTestId("plot-grid")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("plot-card-0").click();
    await page.getByTestId("plot-adopt").click();
    await expect(page.getByText("剧情已由 AI 填好（3 条）")).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("剧情已由 AI 填好（3 条）")).toBeHidden({ timeout: 6000 });
  } finally {
    await restore();
  }
});

test("免费锁定：剧情卡置灰禁点＋升级出口；手写剧情照常可用", async ({ page, request }) => {
  const { restore, token } = await setupSession(page, "none");
  try {
    const pid = await createNovelWithChapter(page, `剧情免费${Date.now() % 100000}`);
    // 右栏剧情行：行级门控（c-character-intro 起 og 页签行级化，整卡锁退役）置灰禁点不隐藏；
    // 升级出口＝副行「升级套餐」按钮（说明文案已删，锁定行自带需开通/需 PRO/需 MAX hint）
    await expect(page.getByTestId("og-plot-draw")).toBeVisible();
    await expect(page.getByTestId("og-plot-draw")).toBeDisabled();
    await expect(page.getByTestId("og-upgrade-btn")).toBeVisible();
    await expect(page.getByTestId("og-upgrade-btn")).toHaveText("升级套餐");
    // 手写剧情不被锁：加/写照常，且真落库
    await page.getByLabel("第 1 条剧情").fill("免费档也能自己写剧情");
    await page.getByRole("button", { name: "加一条" }).click();
    await page.getByLabel("第 2 条剧情").fill("随便加、随便改");
    const H = { Authorization: `Bearer ${token}` };
    await expect
      .poll(
        async () =>
          (await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json())
            ?.plot_items ?? [],
        { timeout: 12000 },
      )
      .toEqual(["免费档也能自己写剧情", "随便加、随便改"]);
  } finally {
    await restore();
  }
});
