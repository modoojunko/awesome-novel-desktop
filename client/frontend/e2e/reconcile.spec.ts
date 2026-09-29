import fs from "fs";
import http from "http";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";

// =========================================================================
// 归档收尾提案 E2E（archive-reconcile，本地桩 AI 全链）：
//   ① PRO：绑定桩模型 → 归档 → 后台收尾产出提案（世界要素/伏笔登记）
//      → 各归各的页签（c-ops-tab-progress-only）：世界要素在「设定」页签采纳
//      （真写回世界设定）、伏笔登记在「伏笔」页签驳回；已决行折叠只显计数；
//      「操作」页签无任何提案行且归档卡提供「重新归档」入口
//   ② 免费档：归档后任何页签不渲染收尾区，且不发 /reconcile 请求
// 桩：node http 服务（容器经 host.docker.internal 访问），OpenAI 兼容
//    /v1/models + /v1/chat/completions，按 prompt 关键词回预置 JSON。
// =========================================================================

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);
const TEST_PASSWORD = ["TestPass", "789!"].join("");
const STUB_PORT = 45871;
const STUB_BASE = `http://host.docker.internal:${STUB_PORT}/v1`;

// ── 桩 AI：按 prompt 关键词回各收尾类别的预置 JSON ─────────────────────────
// c-chapter-dossier：本章变化提取（一次调用四域）——本地桩秒回，即提取提速桩
function stubContent(prompt: string): string {
  if (prompt.includes("只输出一个 JSON 对象，四键齐全")) {
    return JSON.stringify({
      settings: [{ area: "地理", content: "临江渡口夜里封航", evidence: "临江渡口的风裹着湿气" }],
      relations: [{ owner: "林晚", other: "老聋", rel_type: "盟友", change_note: "同舟共济", evidence: "雾里传来第二个呼吸声" }],
      items: [{ name: "残页", change_type: "obtain", holder: "林晚", detail: "残页与火痕吻合", evidence: "残页按在胸口" }],
      knowledge: [{ character: "林晚", fact: "残页的来历", learned: true, evidence: "火痕与纸上的纹路" }],
    });
  }
  if (prompt.includes("世界观/设定事实")) {
    return JSON.stringify({
      items: [{ key: "静默带", value: "无信号的深空航段", set: "extra" }],
    });
  }
  if (prompt.includes("找出角色关系的变化或新关系")) {
    const m = prompt.match(/出场：([^）]+)/);
    const [a, b] = (m?.[1] ?? "").split("、");
    return JSON.stringify({
      items: a && b
        ? [{ owner: a, other: b, rel_type: "同盟", stance: "互信", note: "同舟共济" }]
        : [],
    });
  }
  if (prompt.includes("对既有伏笔的兑现与推进")) {
    // c-hooks-advance-ledger 对账制：台账为空 → ref 未命中跳过，planted 照常入提案
    return JSON.stringify({
      planted: [{ description: "渡口的雾中有第二个人", evidence: "雾里传来第二个呼吸声" }],
      advanced: [{ ref: "#H-0001", note: "雾中人数被清点", evidence: "雾里传来第二个呼吸声" }],
      resolved: [],
    });
  }
  if (prompt.includes("识别新出现或变化的世界要素")) {
    return JSON.stringify({
      items: [{ key: "临江渡口", value: "北境最大的渡口", set: "extra" }],
    });
  }
  if (prompt.includes("状态变化")) {
    const m = prompt.match(/出场角色（([^）]+)）/);
    const who = (m?.[1] ?? "林晚").split("、")[0];
    return JSON.stringify({ items: [{ name: who, state_change: "从迟疑到决意" }] });
  }
  return JSON.stringify({ items: [] });
}

let server: http.Server | null = null;

test.beforeAll(async () => {
  server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      res.setHeader("Content-Type", "application/json");
      if (req.url?.includes("/models")) {
        res.end(JSON.stringify({ object: "list", data: [{ id: "stub-model", object: "model" }] }));
        return;
      }
      if (req.url?.includes("/chat/completions")) {
        let prompt = "";
        try {
          const parsed = JSON.parse(body);
          prompt = parsed.messages?.map((m: { content: string }) => m.content).join("\n") ?? "";
        } catch {
          /* 非 JSON：返回空 items */
        }
        res.end(
          JSON.stringify({
            id: "chatcmpl-stub",
            object: "chat.completion",
            created: 0,
            model: "stub-model",
            choices: [
              {
                index: 0,
                message: { role: "assistant", content: stubContent(prompt) },
                finish_reason: "stop",
              },
            ],
            usage: { prompt_tokens: 30, completion_tokens: 12, total_tokens: 42 },
          }),
        );
        return;
      }
      res.statusCode = 404;
      res.end("{}");
    });
  });
  await new Promise<void>((r) => server!.listen(STUB_PORT, () => r()));
});

test.afterAll(async () => {
  await new Promise<void>((r) => (server ? server.close(() => r()) : r()));
});

async function sRegisterAndLogin() {
  const name = `e2e_rc_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
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

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const restoreConfig = await writeOAuthSession(token, username, tier);
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    restoreConfig();
  };
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore, token };
}

/** 建书 + 一卷一章（正文 ≥100 字）+ 桩模型绑定；返回 project id。 */
async function seedAndBindModel(
  page: Page,
  token: string,
  name: string,
): Promise<string> {
  const auth = { Authorization: `Bearer ${token}` };
  // 桩模型配置 → 拉模型表 → 绑定本书
  const rc = await fetch(`${ORIGIN}/api/v1/api-configs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({
      name: `e2e-rc-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: STUB_BASE,
      api_key: "sk-e2e-stub",
    }),
  });
  expect(rc.ok).toBeTruthy();
  const cfg = await rc.json();
  const configId = cfg.id ?? cfg.data?.id;
  // 模型表落库走「测试连接」（refresh-models 是空壳 stub）：桩 /v1/models → models 入库
  const rr = await fetch(`${ORIGIN}/api/v1/api-configs/${configId}/test`, {
    method: "POST",
    headers: auth,
  });
  expect(rr.ok, `test-connection 失败: ${await rr.text()}`).toBeTruthy();

  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const pid = page.url().match(/#\/novel\/([0-9a-fA-F-]+)/)![1];

  const base = `${ORIGIN}/api/novels/${pid}`;
  await fetch(`${base}/volumes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ title: "第一卷" }),
  });
  await fetch(`${base}/volumes/vol-1/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ title: "渡口" }),
  });
  const rb = await fetch(`${ORIGIN}/api/v1/novels/${pid}/ai-model`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ api_config_id: configId, model: "stub-model" }),
  });
  expect(rb.ok, `绑定模型失败: ${await rb.text()}`).toBeTruthy();
  return pid;
}

const PROSE =
  "临江渡口的风裹着湿气，吹得船篷哗哗作响。林晚把残页按在胸口，火痕与纸上的纹路" +
  "恰好吻合，像是有人隔着许多年对她递了个眼色。雾里传来第二个呼吸声，不紧不慢，" +
  "与她隔着半条跳板；她握紧船桨，决定不再等那班不存在的船。渡口的灯一盏盏亮起，" +
  "照出水面下暗藏的漩涡，也照出她对岸那棵枯树新抽的枝条。";

test("PRO：归档 → 后台收尾提案 → 采纳写回/驳回", async ({ page }) => {
  test.setTimeout(120_000);
  const { restore, token } = await setupSession(page);
  const auth = { Authorization: `Bearer ${token}` };
  try {
    const pid = await seedAndBindModel(page, token, `e2e-rc-${Date.now()}`);
    const base = `${ORIGIN}/api/novels/${pid}`;
    await fetch(`${base}/chapters/vol-1-ch-1/prose`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ prose: PROSE }),
    });
    const ra = await fetch(`${base}/chapters/vol-1-ch-1/archive`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ full_text: PROSE, ai_summary: false }),
    });
    expect(ra.ok).toBeTruthy();
    // c-chapter-dossier：受理制——提取成功才归档（本地桩秒回）
    expect((await ra.json()).state).toBe("extracting");
    for (let i = 0; i < 100; i++) {
      const ch = await (await fetch(`${base}/chapters/vol-1-ch-1`, { headers: auth })).json();
      if (ch.status === "archived") break;
      await new Promise((r) => setTimeout(r, 200));
      if (i === 99) throw new Error("提取未在 20s 内完成归档");
    }

    // 打开书 → 该章 → 设定页签：世界要素提案出现（后台线程 + 前端 5s 轮询）
    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.locator(".col-tree .ch").first().click();
    await page.getByRole("tab", { name: /^设定/ }).click();
    const pane = page.locator('[data-od-id="reconcile-pane"]');
    await expect(pane).toBeVisible({ timeout: 15000 });
    await expect(pane.getByText("归档收尾 · 世界要素提案")).toBeVisible();
    await expect(pane.getByText("世界要素")).toBeVisible({ timeout: 25000 });

    // 采纳「世界要素」→ 真写回世界设定（入口带章节来源）；已决行折叠只显计数
    const loreRow = pane.locator(".reconcile-row", { hasText: "世界要素" });
    await loreRow.getByRole("button", { name: "采纳" }).click();
    await expect(
      pane.locator("details.rc-decided summary", { hasText: "已处理 1" }),
    ).toBeVisible({ timeout: 10000 });
    const world = await (
      await fetch(`${base}/settings/world`, { headers: auth })
    ).json();
    const flat = [...(world.extra ?? []), ...(world.history ?? [])];
    const hit = flat.find((e: { key?: string }) => e.key === "临江渡口");
    expect(hit?.origin).toBe("vol-1-ch-1");

    // 伏笔页签：驳回「伏笔登记」；右栏「登记新伏笔」→ run 端点 → toast
    await page.getByRole("tab", { name: /^伏笔/ }).click();
    await expect(pane.getByText("归档收尾 · 伏笔登记提案")).toBeVisible();
    const hookRow = pane.locator(".reconcile-row", { hasText: "伏笔登记" });
    await expect(hookRow).toBeVisible({ timeout: 25000 });
    await hookRow.getByRole("button", { name: "驳回" }).click();
    await expect(
      pane.locator("details.rc-decided summary", { hasText: "已处理 1" }),
    ).toBeVisible({ timeout: 10000 });
    const runBtn = page.locator(".rail-assist").getByRole("button", { name: /登记新伏笔/ });
    await expect(runBtn).toBeEnabled({ timeout: 10000 });
    await runBtn.click();
    await expect(page.getByText(/已开始收尾提取|已有收尾任务在跑/)).toBeVisible({
      timeout: 10000,
    });

    // 操作页签只留生命周期卡：无任何提案行；已归档章归档卡提供「重新归档」
    await page.getByRole("tab", { name: /^操作/ }).click();
    await expect(page.locator('[data-od-id="reconcile-pane"]')).toHaveCount(0);
    await expect(page.locator(".reconcile-row")).toHaveCount(0);
    await expect(page.getByTestId("archive-reextract")).toBeVisible();
  } finally {
    await restore();
  }
});

test("免费档：归档后任何页签不渲染收尾区（不发收尾请求）", async ({ page }) => {
  test.setTimeout(60_000);
  const { restore, token } = await setupSession(page, "none");
  const auth = { Authorization: `Bearer ${token}` };
  let reconcileCalls = 0;
  try {
    await page.route("**/reconcile*", (r) => {
      reconcileCalls += 1;
      return r.fulfill({ json: { rows: [], progress: {} } });
    });
    // 免费档无 AI：普通建书建章归档即可
    await page.goto(`${ORIGIN}/#/novels`);
    await stableClick(page.getByRole("button", { name: "新建作品" }).first());
    await page.locator("input#bkTitle").fill(`e2e-rc-free-${Date.now()}`);
    await page.getByRole("button", { name: "创建，去写简介" }).click();
    await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
    const pid = page.url().match(/#\/novel\/([0-9a-fA-F-]+)/)![1];
    const base = `${ORIGIN}/api/novels/${pid}`;
    await fetch(`${base}/volumes`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ title: "第一卷" }),
    });
    await fetch(`${base}/volumes/vol-1/chapters`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ title: "渡口" }),
    });
    await fetch(`${base}/chapters/vol-1-ch-1/prose`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ prose: PROSE }),
    });
    const ra = await fetch(`${base}/chapters/vol-1-ch-1/archive`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ full_text: PROSE }),
    });
    expect(ra.ok).toBeTruthy();

    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.locator(".col-tree .ch").first().click();
    // 免费档：三个相关页签都不渲染收尾区（c-ops-tab-progress-only：免费档占位退役）
    for (const tab of [/^设定/, /^伏笔/, /^操作/]) {
      await page.getByRole("tab", { name: tab }).click();
      await expect(page.locator('[data-od-id="reconcile-pane"]')).toHaveCount(0);
      await expect(page.locator('[data-od-id="reconcile-pro-free"]')).toHaveCount(0);
    }
    expect(reconcileCalls).toBe(0);
  } finally {
    await restore();
  }
});
