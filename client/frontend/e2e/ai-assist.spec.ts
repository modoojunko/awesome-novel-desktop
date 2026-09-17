import fs from "fs";
import http from "http";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";

// =========================================================================
// AI 辅助·检测/精修族 E2E（workbench-ai-acts 补货批次，本地桩 AI 全链）：
//   ① 检测族六类（就地弹窗）：章纲「与卷纲冲突检测」→ 文风「文风一致性检查」
//      「标记偏离段落」（空态）→ 关系「关系冲突检测」「建议补边」→ 伏笔「伏笔冲突检测」
//   ② 章纲「补全缺失字段」：还缺清单 → AI 回填表单（含段落规划）→ 缺口清零
//   ③ 提示词「精简提示词」：精修弹窗 → 采纳并保存 → 走既有提示词保存链
//   ④ 免费档：检测/精修动作整体锁定，且不发 /ai-check 请求
// 桩：node http（容器经 host.docker.internal 访问），OpenAI 兼容；按 system 指令
//    关键词回预置 JSON（findings / fills / 精修稿）。
// =========================================================================

const S_API = "http://127.0.0.1:19000/api/web";
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
const STUB_PORT = 45872;
const STUB_BASE = `http://host.docker.internal:${STUB_PORT}/v1`;

/** 桩内容：按各端点 system 提示词的关键指令分支。 */
function stubContent(prompt: string): string {
  if (prompt.includes("你是长篇小说的连贯性审校")) {
    if (prompt.includes("找出本章正文中明显偏离")) {
      return JSON.stringify({ findings: [] }); // 偏离段落：空态路径
    }
    return JSON.stringify({
      findings: [
        { title: "第3段", detail: "人称从第三人称滑到第一人称，与基线不符" },
        { title: "渡口封江时间", detail: "与卷纲的「次日封江」表述冲突" },
      ],
    });
  }
  if (prompt.includes("你是长篇小说章纲编辑")) {
    return JSON.stringify({
      fills: {
        current_task: "问出货源的来路",
        state: "读者以为船家可信",
        strategy: "顺着章纲推进，不提前揭破",
        changes: ["主角与师父决裂"],
        mood: "紧张",
        segments: [
          { summary: "上船前讨价", target_words: 900 },
          { summary: "雾中第二人", target_words: 900 },
        ],
      },
    });
  }
  if (prompt.includes("你是小说写作提示词的编辑")) {
    return "```\n## 任务指示\n精简后的提示词（保留全部红线）\n```";
  }
  return JSON.stringify({ findings: [], items: [] });
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
          /* 非 JSON：回空结构 */
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
  const name = `e2e_ai_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/** 建书 + 一卷一章 + 桩模型绑定；返回 project id。 */
async function seedAndBindModel(
  page: Page,
  token: string,
  name: string,
): Promise<string> {
  const auth = { Authorization: `Bearer ${token}` };
  const rc = await fetch(`${ORIGIN}/api/v1/api-configs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({
      name: `e2e-ai-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: STUB_BASE,
      api_key: "sk-e2e-stub",
    }),
  });
  expect(rc.ok).toBeTruthy();
  const cfg = await rc.json();
  const configId = cfg.id ?? cfg.data?.id;
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

test("PRO：检测族六类弹窗＋章纲补缺＋提示词精修采纳", async ({ page }) => {
  test.setTimeout(180_000);
  const { restore, token } = await setupSession(page);
  const auth = { Authorization: `Bearer ${token}` };
  try {
    const pid = await seedAndBindModel(page, token, `e2e-ai-${Date.now()}`);
    const base = `${ORIGIN}/api/novels/${pid}`;
    await fetch(`${base}/chapters/vol-1-ch-1/prose`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ prose: PROSE }),
    });

    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.locator(".col-tree .ch").first().click();

    // ── 章纲页签：还缺清单 → 与卷纲冲突检测（体积素材分支）─────────────
    const rail = page.locator(".rail-assist");
    await expect(rail.getByText("还缺")).toBeVisible({ timeout: 15000 });
    await rail.getByRole("button", { name: /与卷纲冲突检测/ }).click();
    const modal = page.locator(".modal", { hasText: "卷纲冲突检测" });
    const list = modal.getByTestId("ai-check-list");
    await expect(list).toBeVisible({ timeout: 20000 });
    await expect(list.getByText("渡口封江时间")).toBeVisible();
    await modal.locator(".mcard-foot").getByRole("button", { name: "关闭" }).click();

    // ── 章纲补缺：AI 回填表单（含段落规划），缺口清零 ────────────────────
    await rail.getByRole("button", { name: /补全缺失字段/ }).click();
    await expect(page.getByText(/已补 \d+ 项/)).toBeVisible({ timeout: 20000 });
    await expect(page.locator("textarea#wf-task")).toHaveValue(
      "问出货源的来路",
      { timeout: 10000 },
    );
    // 六项必填补齐 → 「还缺」清单消失（右栏随表单刷新）
    await expect(rail.getByText("还缺")).toHaveCount(0, { timeout: 10000 });

    // ── 文风页签：一致性检查（有 findings）＋标记偏离段落（空态）────────
    await page.getByRole("tab", { name: /^文风/ }).click();
    await rail.getByRole("button", { name: /文风一致性检查/ }).click();
    const styleModal = page.locator(".modal", { hasText: "文风一致性检查" });
    await expect(styleModal.getByTestId("ai-check-list")).toBeVisible({ timeout: 20000 });
    await expect(styleModal.getByText("人称从第三人称滑到第一人称")).toBeVisible();
    await styleModal.locator(".mcard-foot").getByRole("button", { name: "关闭" }).click();

    await rail.getByRole("button", { name: /标记偏离段落/ }).click();
    const devModal = page.locator(".modal", { hasText: "标记偏离段落" });
    await expect(devModal.getByTestId("ai-check-empty")).toBeVisible({ timeout: 20000 });
    await devModal.locator(".mcard-foot").getByRole("button", { name: "关闭" }).click();

    // ── 关系页签：冲突检测（真表素材分支）＋建议补边 ─────────────────────
    await page.getByRole("tab", { name: /^角色关系/ }).click();
    await rail.getByRole("button", { name: /关系冲突检测/ }).click();
    await expect(
      page.locator(".modal", { hasText: "关系冲突检测" }).getByTestId("ai-check-list"),
    ).toBeVisible({ timeout: 20000 });
    await page
      .locator(".modal", { hasText: "关系冲突检测" })
      .locator(".mcard-foot")
      .getByRole("button", { name: "关闭" })
      .click();

    await rail.getByRole("button", { name: /建议补边/ }).click();
    await expect(
      page.locator(".modal", { hasText: "建议补边" }).getByTestId("ai-check-list"),
    ).toBeVisible({ timeout: 20000 });
    await page
      .locator(".modal", { hasText: "建议补边" })
      .locator(".mcard-foot")
      .getByRole("button", { name: "关闭" })
      .click();

    // ── 伏笔页签：伏笔冲突检测（台账素材分支）───────────────────────────
    await page.getByRole("tab", { name: /^伏笔/ }).click();
    await rail.getByRole("button", { name: /伏笔冲突检测/ }).click();
    await expect(
      page.locator(".modal", { hasText: "伏笔冲突检测" }).getByTestId("ai-check-list"),
    ).toBeVisible({ timeout: 20000 });
    await page
      .locator(".modal", { hasText: "伏笔冲突检测" })
      .locator(".mcard-foot")
      .getByRole("button", { name: "关闭" })
      .click();

    // ── 提示词页签：精简提示词 → 采纳并保存（走既有保存链）───────────────
    await page.getByRole("tab", { name: /^提示词/ }).click();
    await rail.getByRole("button", { name: /精简提示词/ }).click();
    const refineModal = page.locator(".modal", { hasText: "精简提示词" });
    await expect(refineModal.getByTestId("refine-preview")).toContainText(
      "精简后的提示词",
      { timeout: 20000 },
    );
    await refineModal.getByTestId("refine-adopt").click();
    await expect(page.getByText("已采纳并保存为本章提示词")).toBeVisible({ timeout: 15000 });

    // 落库实证：提示词链路读到采纳稿（polished=true）
    const stored = await (
      await fetch(`${base}/chapters/vol-1-ch-1/write/prompt`, { headers: auth })
    ).json();
    expect(stored.polished).toBe(true);
    expect(String(stored.prompt)).toContain("精简后的提示词");
  } finally {
    await restore();
  }
});

test("免费档：检测/精修动作整体锁定且不发 ai-check 请求", async ({ page }) => {
  test.setTimeout(60_000);
  const { restore, token } = await setupSession(page, "none");
  const auth = { Authorization: `Bearer ${token}` };
  let checkCalls = 0;
  try {
    await page.route("**/ai-check*", (r) => {
      checkCalls += 1;
      return r.fulfill({ json: { ok: true, findings: [] } });
    });
    await page.goto(`${ORIGIN}/#/novels`);
    await stableClick(page.getByRole("button", { name: "新建作品" }).first());
    await page.locator("input#bkTitle").fill(`e2e-ai-free-${Date.now()}`);
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

    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.locator(".col-tree .ch").first().click();
    await page.getByRole("tab", { name: /^文风/ }).click();
    const acts = page.locator(".rail-acts");
    await expect(acts).toHaveClass(/rail-locked/, { timeout: 15000 });
    const btn = page.locator(".rail-assist").getByRole("button", { name: /文风一致性检查/ });
    await expect(btn).toBeDisabled();
    // 锁定＝禁点（pointer-events:none → 点击到不了处理器）；静置复核零请求
    await page.waitForTimeout(1000);
    expect(checkCalls).toBe(0);
  } finally {
    await restore();
  }
});
