import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { addFirstChapterViaTree, cleanupSessionNovels, stableClick } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// 剧情推演 + 提示词六来源 E2E（storyline.html 四期尾，打桩 AI）：
//   ① PRO：章纲「剧情推演」→ 回合推进需先选走法 → 收进章纲追加一条剧情 → 刷新回读
//   ② 免费态：推演入口不渲染
//   ③ 提示词页签：六来源 chips + 只读清单（含未填标注）
// 手法与 outline-ai-draft.spec.ts 一致：S端 真注册登录 + config.json 注入；
// simulate / prompt-sources 端点 page.route fulfill。
// =========================================================================

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
  "config.json",
);
const TEST_PASSWORD = ["TestPass", "789!"].join("");
const FAKE_KEY = ["sk-e2e", "-not-real"].join("");

async function sRegisterAndLogin() {
  const name = `e2e_sim_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password: TEST_PASSWORD,
      security_question: "最喜欢的颜色",
      security_answer: "蓝色",
    }),
  });
  const regBody = await reg.json();
  if (regBody.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: TEST_PASSWORD }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  return { token: loginBody.data.token as string, username: name };
}

/** 写 config.json 带竞态守卫（与 outline-ai-draft.spec.ts 同配方）。 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  const mine = JSON.stringify(cfg, null, 2);
  const writeMine = () => fs.writeFileSync(CONFIG_PATH, mine);
  writeMine();
  for (let stable = 0, tries = 0; stable < 2 && tries < 10; tries++) {
    await new Promise((r) => setTimeout(r, 300));
    if (fs.readFileSync(CONFIG_PATH, "utf-8") === mine) stable += 1;
    else {
      writeMine();
      stable = 0;
    }
  }
  return () => fs.writeFileSync(CONFIG_PATH, original);
}

async function setupSession(
  page: Page,
  tier = "trial",
): Promise<{ restore: () => void; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restoreConfig = await writeOAuthSession(token, username, tier);
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    restoreConfig();
  };
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：e2e 注入的 pc_hash 在 S端 无设备授权（code 1），后端会
  // 据此清空 config.json 的注入 token → 业务请求 401（已知环境阻塞）。桩掉这次
  // 往返即可保住注入会话；会员判定仍走后端 check_permission()（读 config.json tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore, token };
}

async function ensurePromptAccess(request: APIRequestContext, token: string) {
  const r = await request.post(`${ORIGIN}/api/v1/api-configs`, {
    data: {
      name: `e2e-sim-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: "http://127.0.0.1:1",
      api_key: FAKE_KEY,
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
}

/** 建书 + 树底「＋ 新增一章」垫卷排章 → 点章 → 停在「章纲」页签 */
async function setupFirstChapter(page: Page, name: string) {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  await page.locator(".mtab", { hasText: "写作" }).click();
  await expect(page.locator(".mtab.on")).toContainText("写作");
  await addFirstChapterViaTree(page);
}

const SIM = {
  ok: true,
  source: "ai",
  entry: "她解开了最后一根系泊。",
  exit: "她把信交给了陌生人",
  prev_label: "开书",
  cast: ["林晚"],
  rounds: [
    {
      n: 1,
      beat: "匿名信被尾随",
      who: "林晚",
      place: "渡口",
      time: "清晨",
      at: "承上：她解开了最后一根系泊。",
      shift: "她决定不再等船",
      moves: [
        { k: "顺", tone: "ok", label: "林晚顺着当前节奏动手", out: "顺线落地" },
        { k: "拗", tone: "warn", label: "林晚先被外力打断一下", out: "被船夫叫住" },
      ],
    },
    {
      n: 2,
      beat: "渡口对质",
      who: "林晚",
      place: "渡口",
      time: "清晨",
      at: "推向本章结尾",
      shift: "信到了陌生人手里",
      moves: [
        { k: "顺", tone: "ok", label: "林晚顺着当前节奏动手", out: "对质完成" },
        { k: "拗", tone: "warn", label: "林晚先被外力打断一下", out: "对质被打断" },
      ],
    },
  ],
};

const STRATEGY_WARN = "推演走法 · 中途先接一次意外，再拉回主线";

test("MAX：按回合推演 → 收进章纲追加一条剧情 → 刷新回读（推演归 MAX，2026-10-05 拍板）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page, "max");
  try {
    await ensurePromptAccess(request, token);
    await setupFirstChapter(page, `e2e-sim-推演-${Date.now()}`);
    await page.route("**/api/novels/*/chapters/*/simulate", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SIM) }),
    );

    await expect(page.getByTestId("og-simulate")).toBeVisible();
    await page.getByTestId("og-simulate").click();
    await expect(page.getByTestId("sim-round-1")).toContainText("待你定");
    await expect(page.getByTestId("sim-round-2")).toContainText("还没走到");

    // 未选走法不能推进
    await page.getByTestId("sim-next").click();
    await expect(page.getByTestId("sim-round-2")).toContainText("还没走到");
    // 选顺 → 展开末回合（末回合仍待定 + 出现收进章纲）
    await page.getByTestId("sim-pick-1-ok").click();
    await page.getByTestId("sim-next").click();
    await expect(page.getByTestId("sim-round-2")).toContainText("待你定");
    await expect(page.getByTestId("sim-adopt")).toBeVisible();
    // 末回合选拗 → 收进章纲（c-og-slim-v2：追加为一条剧情条目，不再写预期策略）
    await page.getByTestId("sim-pick-2-warn").click();
    await page.getByTestId("sim-adopt").click();
    await expect(page.getByText(/已按推演走法加了一条剧情/)).toBeVisible({
      timeout: 10000,
    });
    // 查看态先看只读行，再进编辑态断言表单值（c-ch-og-readonly）
    await expect(page.getByTestId("og-view")).toContainText(STRATEGY_WARN);
    await page.getByTestId("og-edit").click();
    await expect(page.getByLabel("第 1 条剧情")).toHaveValue(STRATEGY_WARN);

    // 刷新回读
    await page.reload();
    await page.locator(".col-tree .ch", { hasText: "第一章" }).click();
    await page.getByTestId("og-edit").click();
    await expect(page.getByLabel("第 1 条剧情")).toHaveValue(STRATEGY_WARN, {
      timeout: 10000,
    });
  } finally {
    await restore();
  }
});

test("免费态：剧情推演行可见但行级锁定「MAX 专属」（og 页签不整卡锁）", async ({ page }) => {
  const { restore } = await setupSession(page, "none");
  try {
    await setupFirstChapter(page, `e2e-sim-免费-${Date.now()}`);
    // tier-plan-four-tiers：og 页签恒 ready，门在行级——推演行 ra-off＋档位 hint（单源 upgradeHintOf）
    const row = page.getByTestId("og-simulate");
    await expect(row).toBeVisible();
    await expect(row).toBeDisabled();
    await expect(row).toContainText("MAX 专属");
    await expect(page.locator(".rail-assist.locked")).toHaveCount(0);
    // 推演弹窗不出现（disabled 吞点击）
    await expect(page.locator(".modal", { hasText: "剧情推演" })).toHaveCount(0);
  } finally {
    await restore();
  }
});

test("提示词状态：正文页签作用域行显示组装来源统计（chips 详情随页签退役）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    await setupFirstChapter(page, `e2e-sim-来源-${Date.now()}`);
    await page.route("**/api/novels/*/chapters/*/prompt-sources", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sources: [
            { key: "book", label: "全书设定", chars: 12, preview: "故事前提：……", empty: false },
            { key: "volume", label: "大纲 · 卷纲", chars: 0, preview: "", empty: true },
            { key: "outline", label: "本章章纲", chars: 30, preview: "章纲概要：……", empty: false },
            { key: "style", label: "全书文风 ＋ 本章调整", chars: 40, preview: "本章覆盖：……", empty: false },
            { key: "hooks", label: "伏笔进展 · 截至上一章", chars: 10, preview: "谁在暗中跟着她", empty: false },
            { key: "cast", label: "本章涉及角色", chars: 8, preview: "林晚：", empty: false },
          ],
          total_chars: 100,
          cast_count: 1,
        }),
      }),
    );

    // c-prompt-tab-retire：提示词页签退役；组装来源统计收编正文页签作用域行
    await expect(page.getByRole("tab", { name: /^提示词/ })).toHaveCount(0);
    await page.getByRole("tab", { name: /^正文/ }).click();
    const target = page.locator(".ai-target");
    await expect(target).toContainText("组装来源 100 字", { timeout: 10000 });
    await expect(target).toContainText("本章提示词");
  } finally {
    await restore();
  }
});
