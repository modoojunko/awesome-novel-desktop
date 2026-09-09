import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// =========================================================================
// 主线拆纲 E2E（story-arc-planning）：
// 1. 免费手填主线全流程（一句话 + 结局 + 分卷行含待定）→ 确认完成 → status 绿
// 2. 免费点「AI 帮我拆」→ 后端 403 member_required → 全局升级引导弹窗，手动填写不受影响
// 3. 会员四步向导（AI 响应浏览器侧打桩）：产出逐步落卡 + 自动保存；中途退出可续
// =========================================================================
// 会话注入与 creation-flow.spec.ts 同法（S端 真实签发 + docker config.json）。
// 测试口令为拼接构造（与既有 spec 同源的占位口令，非真实凭据）。

const S_API = "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.cwd(), "..", "..", ".docker-data", "client", "config.json",
);
const TEST_PASSWORD = ["Test", "Pass789", "!"].join("");

async function sRegisterAndLogin() {
  const name = `e2e_arc_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = TEST_PASSWORD;
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name, password,
      security_question: "最喜欢的颜色", security_answer: "蓝色",
    }),
  });
  const regBody = await reg.json();
  if (regBody.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  return { token: loginBody.data.token as string, username: name };
}

function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  return () => fs.writeFileSync(CONFIG_PATH, original);
}

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const restore = writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：e2e 注入的 pc_hash 在 S端 无设备授权（code 1），后端会
  // 据此清空 config.json 的注入 token → 业务请求 401（已知环境阻塞）。桩掉这次
  // 往返即可保住注入会话；会员判定仍走后端 check_permission()（读 config.json tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore, token };
}

async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建并开始写作" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

async function apiGetJSON(request: APIRequestContext, token: string, path: string) {
  const r = await request.get(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function openArcPanel(page: Page) {
  await page.getByRole("button", { name: /^设定/ }).click();
  await page.locator(".settings-v .col-tree").getByText("主线", { exact: true }).click();
}

test.describe("主线卡", () => {
  test("免费手填全流程：一句话 + 结局 + 分卷（含待定行）→ 确认完成", async ({ page, request }) => {
    const { restore, token } = await setupSession(page, "none");
    try {
      const pid = await createNovel(page, `主线免费${Date.now() % 100000}`);
      await openArcPanel(page);

      // 一句话主线
      await page
        .getByPlaceholder(/陆征追查失踪案/)
        .fill("陆征追查苏棠失踪案，越查越深触及警队内部势力");

      // 结局三字段（画面 + 主角结局；基调选择题点「悲」）
      await page.getByPlaceholder("最后一幕画面（例：侦探所里看着旧卷宗）").fill("侦探所里看着旧卷宗");
      await page.getByPlaceholder("主角最终怎样（例：破案但心里装了更多）").fill("破案但心里装了更多");
      await page.getByRole("radio", { name: /^悲/ }).click();

      // 分卷两行：卷 1 实填，卷 2 整行待定
      await page.getByRole("button", { name: "加一卷" }).click();
      await page.getByPlaceholder("卷名").fill("失踪");
      await page.getByPlaceholder("这卷干什么（核心冲突一句话）").fill("追查失踪案发现旧案被压");
      await page.getByPlaceholder("章数").fill("10");
      await page.getByRole("button", { name: "加一卷" }).click();
      // 卷 2 的待定按钮（btn-secondary，与基调 seg 区分）
      await page
        .locator(".field", { hasText: "分卷规划" })
        .getByRole("button", { name: "待定" })
        .last()
        .click();

      // 确认完成（先 save 后 confirm）→ 确认即前进到下一项（tasks 2.2）
      const arcSave = page.waitForResponse(
        (r) => r.request().method() === "PUT" && r.url().includes("/story/arc"),
      );
      await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
      await arcSave;
      await expect(
        page.locator(".settings-v main h2", { hasText: "世界" }),
      ).toBeVisible({ timeout: 5000 });

      // 后端直查：story-arc 可确认 + 卡内容回读一致
      const status = await apiGetJSON(request, token, `/novels/${pid}/settings/status`);
      expect(status["story-arc"]).toBe(true);
      const arc = await apiGetJSON(request, token, `/novels/${pid}/story/arc`);
      expect(arc.premise).toContain("陆征");
      expect(arc.volumes).toHaveLength(2);
      expect(arc.volumes[1].title).toBe("待定");
    } finally {
      restore();
    }
  });

  test("免费跑向导 → 403 升级引导弹窗，手动填写不受影响", async ({ page }) => {
    const { restore } = await setupSession(page, "none");
    try {
      await createNovel(page, `主线拦截${Date.now() % 100000}`);
      await openArcPanel(page);

      // 向导常驻右栏（.col-ai），输入框为右栏里的 textarea
      const wizInput = page.locator(".col-ai").getByRole("textbox");
      await wizInput.fill("我想写一个侦探故事");
      const wizard403 = page.waitForResponse(
        (r) => r.url().includes("/story/arc/wizard/condense") && r.status() === 403,
      );
      await page.locator(".col-ai").getByRole("button", { name: /让 AI 处理/ }).click();
      await wizard403;

      // 全局升级引导弹窗（MemberBlockPrompt）
      await expect(page.getByText(/开通|续费/).first()).toBeVisible({ timeout: 5000 });

      // 手动填写不受影响：仍可填一句话主线
      await page.getByPlaceholder(/陆征追查失踪案/).fill("手填主线不受拦截影响");
    } finally {
      restore();
    }
  });
});

test.describe("AI 四步向导（会员，浏览器侧打桩 AI 响应）", () => {
  test("四步产出逐步落卡 + 自动保存；中途退出重开续步", async ({ page, request }) => {
    const { restore, token } = await setupSession(page, "trial");
    try {
      const pid = await createNovel(page, `主线向导${Date.now() % 100000}`);

      // 打桩四步 AI 响应（浏览器层，绕真实模型；落卡 PUT 走真实后端）
      await page.route(/\/story\/arc\/wizard\/(condense|ending|split|audit)/, (route) => {
        const step = route.request().url().match(/wizard\/(\w+)/)![1];
        const value =
          step === "condense"
            ? { premise: "陆征追查失踪案触及警队保护伞", notes: "抓住了查案主线" }
            : step === "ending"
              ? { ending: { scene: "侦探所旧卷宗", hero: "破案但有余韵", tone: "悲" }, contradiction: "", notes: "结局已按你的描述整理" }
              : step === "split"
                ? { volumes: [
                    { title: "失踪", conflict: "追查失踪案发现旧案被压", chapters: "10" },
                    { title: "深水", conflict: "触及警队内部保护伞", chapters: "12" },
                    { title: "破局", conflict: "与幕后黑手正面交锋", chapters: "8" },
                  ], notes: "按三个断点分卷" }
                : { checks: [{ question: "每卷挂在主线上", passed: true, detail: "三卷均为查案主线子集" }],
                    passed: true, structure: "三卷式：起/承/转合" };
        return route.fulfill({ json: { value } });
      });

      await openArcPanel(page);

      // 第 1 步：说想法 → 浓缩落卡（向导常驻右栏 .col-ai）
      await page.locator(".col-ai").getByRole("textbox").fill("陆征是私家侦探，苏棠姐姐来找他说妹妹失踪了……");
      await page.locator(".col-ai").getByRole("button", { name: /让 AI 处理/ }).click();
      await expect(page.getByPlaceholder(/陆征追查失踪案/)).toHaveValue(/触及警队保护伞/, { timeout: 5000 });

      // 第 2 步：聊结局 → 落结局三字段
      await expect(page.getByRole("button", { name: "2. 聊结局" })).toHaveClass(/on/);
      await page.locator(".col-ai").getByRole("textbox").fill("案子破了但他知道还有很多没挖出来");
      await page.locator(".col-ai").getByRole("button", { name: /让 AI 处理/ }).click();
      await expect(page.getByPlaceholder("最后一幕画面（例：侦探所里看着旧卷宗）")).toHaveValue("侦探所旧卷宗", { timeout: 5000 });

      // 中途离开再回来：切到「世界」再切回「主线」，右栏向导按卡片内容续到第 3 步
      await page.locator(".s-item", { hasText: "世界" }).click();
      await page.locator(".s-item", { hasText: "主线" }).click();
      await expect(page.getByRole("button", { name: "3. 倒推分卷" })).toHaveClass(/on/, { timeout: 5000 });

      // 第 3 步：倒推分卷 → 落分卷表
      await page.locator(".col-ai").getByRole("textbox").fill("按三个大转折分");
      await page.locator(".col-ai").getByRole("button", { name: /让 AI 处理/ }).click();
      await expect(page.getByPlaceholder("卷名").first()).toHaveValue("失踪", { timeout: 5000 });

      // 第 4 步：自查 → 三问结果 + 结构归纳
      await page.locator(".col-ai").getByRole("textbox").fill("自查一下");
      await page.getByRole("button", { name: "开始自查" }).click();
      await expect(page.getByText(/三卷式/)).toBeVisible({ timeout: 5000 });

      // 向导产出已随每步自动落卡（后端直查）
      const arc = await apiGetJSON(request, token, `/novels/${pid}/story/arc`);
      expect(arc.premise).toContain("保护伞");
      expect(arc.volumes).toHaveLength(3);
      expect(arc.ending.scene).toBe("侦探所旧卷宗");
    } finally {
      restore();
    }
  });
});
