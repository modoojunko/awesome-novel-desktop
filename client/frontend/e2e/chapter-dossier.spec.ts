// 本章变化（c-chapter-dossier）E2E 全链：归档受理→后台提取→设定/关系页签待确认→采纳→
// 下一章组装来源第七处（缺口标注→采纳后可见）→重写级联（下游「设定待更新」）。
// 本地桩 AI 秒回四域 JSON（提取提速桩）。
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5684";

const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);
const TEST_PASSWORD = ["TestPass", "789!"].join("");
const STUB_PORT = 45873;
const STUB_BASE = `http://host.docker.internal:${STUB_PORT}/v1`;

const EXTRACT_JSON = JSON.stringify({
  settings: [{ area: "地理", content: "临江渡口夜里封航", evidence: "临江渡口的风裹着湿气" }],
  relations: [{ owner: "林晚", other: "阿蓟", rel_type: "盟友", change_note: "同舟共济", evidence: "雾里传来第二个呼吸声" }],
  items: [{ name: "残页", change_type: "obtain", holder: "林晚", detail: "残页与火痕吻合", evidence: "残页按在胸口" }],
  knowledge: [{ character: "阿蓟", fact: "残页的来历", learned: false, evidence: "她并不知道" }],
});

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
        res.end(JSON.stringify({
          id: "chatcmpl-stub", object: "chat.completion", created: 0, model: "stub-model",
          choices: [{ index: 0, message: { role: "assistant", content: EXTRACT_JSON }, finish_reason: "stop" }],
          usage: { prompt_tokens: 30, completion_tokens: 12, total_tokens: 42 },
        }));
        return;
      }
      res.statusCode = 404;
      res.end("{}");
    });
  });
  await new Promise<void>((r) => server!.listen(STUB_PORT, () => r()));
});
test.afterAll(async () => {
  await new Promise<void>((r) => server ? server.close(() => r()) : r());
});

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19610/api/web";

async function sRegisterAndLogin() {
  const name = `e2e_ds_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  // 会话文件形状与 reconcile.spec 同源：token（非 access_token）＋随机 pc_hash
  // （设备指纹），expires_at 清空；last_login_at 刷新。
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = token;
  cfg.username = username;
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
    else { writeMine(); stable = 0; }
  }
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  return {
    token,
    restore: async () => {
      await cleanupSessionNovels(ORIGIN, token);
      fs.writeFileSync(CONFIG_PATH, original);
    },
  };
}

async function bindStubModel(request: APIRequestContext, token: string, pid: string) {
  const rc = await request.post(`${ORIGIN}/api/v1/api-configs`, {
    data: { name: `e2e-ds-${Date.now()}`, vendor_id: "openai-compat", base_url: STUB_BASE, api_key: "sk-e2e-stub" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(rc.ok()).toBeTruthy();
  const cfg = await rc.json();
  const configId = cfg.id ?? cfg.data?.id;
  await request.post(`${ORIGIN}/api/v1/api-configs/${configId}/test`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const rb = await request.put(`${ORIGIN}/api/v1/novels/${pid}/ai-model`, {
    data: { api_config_id: configId, model: "stub-model" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(rb.ok(), `绑定模型失败: ${await rb.text()}`).toBeTruthy();
}

const PROSE =
  "临江渡口的风裹着湿气，吹得船篷哗哗作响。林晚把残页按在胸口，火痕与纸上的纹路" +
  "恰好吻合，像是有人隔着许多年对她递了个眼色。雾里传来第二个呼吸声，不紧不慢，" +
  "与她隔着半条跳板；她握紧船桨，决定不再等那班不存在的船。渡口的灯一盏盏亮起，" +
  "照出水面下暗藏的漩涡，也照出她对岸那棵枯树新抽的枝条。";

/** 建书＋一卷一章（写正文）＋绑桩模型；返回 pid。
 *  排队门禁（workbench-frontier）：ch-2 须等 ch-1 归档后才可建写——由调用方在
 *  归档后按需 addChapter2。 */
async function seed(page: Page, request: APIRequestContext, token: string, name: string) {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const pid = page.url().match(/#\/novel\/([0-9a-fA-F-]+)/)![1];
  const base = `${ORIGIN}/api/novels/${pid}`;
  const auth = { Authorization: `Bearer ${token}` };
  await request.post(`${base}/volumes`, { data: { title: "第一卷" }, headers: auth });
  const rc = await request.post(`${base}/volumes/vol-1/chapters`, {
    data: { title: "第1章" }, headers: auth,
  });
  expect(rc.ok()).toBeTruthy();
  const rp = await request.put(`${base}/chapters/vol-1-ch-1/prose`, {
    data: { prose: PROSE }, headers: auth,
  });
  expect(rp.ok(), `prose ch1: ${await rp.text()}`).toBeTruthy();
  await bindStubModel(request, token, pid);
  return pid;
}

/** 第 1 章归档后补建第 2 章＋正文（frontier 已前移）。 */
async function addChapter2(request: APIRequestContext, token: string, pid: string) {
  const base = `${ORIGIN}/api/novels/${pid}`;
  const auth = { Authorization: `Bearer ${token}` };
  const rc = await request.post(`${base}/volumes/vol-1/chapters`, {
    data: { title: "第2章" }, headers: auth,
  });
  expect(rc.ok()).toBeTruthy();
  const rp = await request.put(`${base}/chapters/vol-1-ch-2/prose`, {
    data: { prose: PROSE }, headers: auth,
  });
  expect(rp.ok(), `prose ch2: ${await rp.text()}`).toBeTruthy();
}

async function waitArchived(base: string, auth: Record<string, string>) {
  for (let i = 0; i < 100; i++) {
    const ch = await (await fetch(`${base}/chapters/vol-1-ch-1`, { headers: auth })).json();
    if (ch.status === "archived") return;
    await new Promise((r) => setTimeout(r, 200));
    if (i === 99) throw new Error("提取未在 20s 内完成归档");
  }
}

test("变化分区全链：归档受理提取→设定/关系页签待确认→采纳→下章来源第七处→重写级联", async ({ page, request }) => {
  test.setTimeout(150_000);
  const { restore, token } = await setupSession(page);
  const auth = { Authorization: `Bearer ${token}` };
  try {
    const pid = await seed(page, request, token, `e2e-dossier-${Date.now()}`);
    const base = `${ORIGIN}/api/novels/${pid}`;

    // ① 归档第 1 章：受理 → 桩秒回 → 归档落地＋四域 pending
    const ra = await request.post(`${base}/chapters/vol-1-ch-1/archive`, {
      data: { full_text: PROSE, ai_summary: false },
      headers: auth,
    });
    expect(ra.ok()).toBeTruthy();
    expect((await ra.json()).state).toBe("extracting");
    await waitArchived(base, auth);
    await addChapter2(request, token, pid);

    // ②′ 操作页签：三段进度条（c-ops-archive-stages）＝提取✓＋待确认计数＋完成✓
    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.locator(".col-tree .ch").first().click();
    await page.getByRole("tab", { name: /^操作/ }).click();
    const stages = page.getByTestId("archive-stages");
    await expect(stages).toBeVisible();
    await expect(stages).toContainText("待确认");
    await expect(stages).toContainText("完成");

    // ② 设定页签：设定/物品/认知变化（按子领域分组）＋证据展开＋一键采纳
    await page.getByRole("tab", { name: /^设定/ }).click();
    const pane = page.getByTestId("setting-changes-section");
    await expect(pane).toBeVisible({ timeout: 15000 });
    await expect(pane.getByTestId("changes-area").first()).toBeVisible({ timeout: 15000 });
    await expect(pane.getByText(/临江渡口夜里封航/)).toBeVisible();
    await expect(pane.getByText(/仍不知道「残页的来历」/)).toBeVisible();
    // 证据句展开（点内容首行——行中心落在 .ds-actions stopPropagation 区）
    const row = pane.getByTestId("change-row").first();
    const rowHead = row.locator("div").first();
    for (let i = 0; i < 3 && !(await row.getAttribute("class"))!.includes("open"); i++) {
      await rowHead.click();
      await page.waitForTimeout(250);
    }
    await expect(row).toHaveClass(/open/);
    await expect(pane.getByText(/证据：「临江渡口的风裹着湿气」/)).toBeVisible();
    // 一键采纳全部（设定区块不含关系行）
    await pane.getByTestId("changes-accept-all").click();
    await expect(pane.getByText(/全部采纳（0）/)).toBeVisible({ timeout: 10000 });
    const d = await (await fetch(`${base}/chapters/vol-1-ch-1/dossier`, { headers: auth })).json();
    // 批量只波及设定/物品/认知三域；关系行留给「角色关系」页签确认（跨域误采纳防线）
    expect(d.progress.pending).toBe(1);
    expect(d.progress.accepted).toBeGreaterThanOrEqual(3);

    // ②′ 角色关系页签（c-chapter-relations-graph）：图为主表达——图在前、工作流在后；
    // 待确认关系行画虚线提案边；本书无角色卡 → 占位节点也上图
    await page.getByRole("tab", { name: /^角色关系/ }).click();
    const rg = page.locator('[data-od-id="relations-graph"]');
    await expect(rg).toBeVisible({ timeout: 15000 });
    await expect(rg.locator(".rg-edge.pending .rg-line")).toHaveCount(1);
    await expect(rg.locator(".rg-node.ghost")).toHaveCount(2); // 林晚/阿蓟 均无卡 → 占位
    await expect(rg.locator(".rg-legend")).toContainText(/剧情演变 0 · 待确认 1/);
    const relSection = page.getByTestId("relation-changes-section");
    await expect(relSection).toBeVisible();
    await expect(relSection.getByTestId("change-row").first()).toContainText("林晚 → 阿蓟：盟友");
    const rgBox = await rg.boundingBox();
    const relBox = await relSection.boundingBox();
    expect(rgBox!.y).toBeLessThan(relBox!.y);
    // 工作流采纳 → 图即时翻面（虚线→高亮实线；事件重拉沿用旧渲染不闪「加载中」）
    await relSection.getByRole("button", { name: "采纳", exact: true }).click();
    await expect(rg.locator(".rg-edge.hit .rg-line")).toHaveCount(1);
    await expect(rg.locator(".rg-edge.pending .rg-line")).toHaveCount(0);
    await expect(rg.locator(".rg-legend")).toContainText(/剧情演变 1 · 待确认 0/);
    // 箭头＋极性：盟友＝友好绿，箭头 marker 同色挂在路径末端
    await expect(rg.locator(".rg-edge.hit.p-friendly .rg-line").first()).toHaveAttribute("marker-end", /friendly/);
    // ③ 第 2 章组装来源：第七处「故事状态」含已采纳内容
    await page.locator(".col-tree .ch").nth(1).click();
    await page.getByRole("tab", { name: /^章纲/ }).click();
    const ps = await (
      await fetch(`${base}/chapters/vol-1-ch-2/prompt-sources`, { headers: auth })
    ).json();
    const ss = ps.sources.find((x: { key: string }) => x.key === "story_state");
    expect(ss).toBeTruthy();
    expect(ss.empty).toBe(false);
    expect(ss.preview).toContain("临江渡口夜里封航"); // preview 截 120 字，认知段走 preview 端点断言
    const pv = await (await fetch(`${base}/dossier/preview?up_to_ref=vol-1-ch-1`, { headers: auth })).json();
    expect(pv.counts.knowledge).toBeGreaterThanOrEqual(1);
    expect(pv.domains.knowledge[0].learned).toBe(false); // 防泄底基线：阿蓟仍不知

    // ③′ 第 2 章也归档（出变化行）——级联只标「有变化行」的下游章
    const ra2 = await request.post(`${base}/chapters/vol-1-ch-2/archive`, {
      data: { full_text: PROSE, ai_summary: false },
      headers: auth,
    });
    expect((await ra2.json()).state).toBe("extracting");
    for (let i = 0; i < 100; i++) {
      const ch = await (await fetch(`${base}/chapters/vol-1-ch-2`, { headers: auth })).json();
      if (ch.status === "archived") break;
      await new Promise((r) => setTimeout(r, 200));
      if (i === 99) throw new Error("第 2 章提取未在 20s 内完成归档");
    }

    // ③″ 第 2 章关系页签：往章演变边＋本章待确认虚线边同向并存（待确认优先展示）
    await page.getByRole("tab", { name: /^角色关系/ }).click();
    const rg2 = page.locator('[data-od-id="relations-graph"]');
    await expect(rg2).toBeVisible({ timeout: 15000 });
    await expect(rg2.locator(".rg-edge.pending .rg-line")).toHaveCount(1);
    await expect(rg2.locator(".rg-legend")).toContainText(/剧情演变 1 · 待确认 1/);
    await expect(page.getByTestId("relation-changes-section").getByTestId("change-row").first())
      .toContainText("林晚 → 阿蓟：盟友");

    // ④ 重写第 1 章 → 第 2 章树角标「设定待更新」＋设定页签 stale 横幅
    const rw = await request.post(`${base}/chapters/vol-1-ch-1/rewrite`, { data: {}, headers: auth });
    expect(rw.ok()).toBeTruthy();
    expect((await rw.json()).dossier_stale_marked).toBe(1);
    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByTestId("ch-dossier-stale")).toBeVisible({ timeout: 15000 });
    await page.locator(".col-tree .ch").nth(1).click();
    await page.getByRole("tab", { name: /^设定/ }).click();
    await expect(page.getByTestId("changes-stale-banner").first()).toBeVisible({ timeout: 15000 });

    // ⑤ 消费侧跳过 stale 章（重写后第 1 章变化已清空，第 2 章 stale → 状态块无内容）
    const ps2 = await (
      await fetch(`${base}/chapters/vol-1-ch-2/prompt-sources`, { headers: auth })
    ).json();
    const ss2 = ps2.sources.find((x: { key: string }) => x.key === "story_state");
    expect(ss2.empty).toBe(true);
  } finally {
    await restore();
  }
});

test("逃生阀：提取失败→跳过仍归档（未提取态＋补提取）", async ({ page, request }) => {
  test.setTimeout(120_000);
  // 桩只对提取调用返回烂输出：用独立桩端口 45874 在本用例内起
  const badPort = 45874;
  const bad = http.createServer((req, res) => {
    res.setHeader("Content-Type", "application/json");
    if (req.url?.includes("/models")) {
      res.end(JSON.stringify({ object: "list", data: [{ id: "stub-model", object: "model" }] }));
      return;
    }
    res.end(JSON.stringify({
      id: "x", object: "chat.completion", created: 0, model: "stub-model",
      choices: [{ index: 0, message: { role: "assistant", content: "这不是 JSON" }, finish_reason: "stop" }],
      usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
    }));
  });
  await new Promise<void>((r) => bad.listen(badPort, () => r()));
  const { restore, token } = await setupSession(page);
  const auth = { Authorization: `Bearer ${token}` };
  try {
    const pid = await seed(page, request, token, `e2e-ds-skip-${Date.now()}`)
      .then(async (p) => {
        // 重绑到坏桩（seed 已绑 45873 好桩——本用例重绑坏桩验证失败路径）
        const rc = await request.post(`${ORIGIN}/api/v1/api-configs`, {
          data: { name: `e2e-bad-${Date.now()}`, vendor_id: "openai-compat", base_url: `http://host.docker.internal:${badPort}/v1`, api_key: "sk-e2e-stub" },
          headers: auth,
        });
        const cfg = await rc.json();
        await request.post(`${ORIGIN}/api/v1/api-configs/${cfg.id ?? cfg.data?.id}/test`, { headers: auth });
        const rb = await request.put(`${ORIGIN}/api/v1/novels/${p}/ai-model`, {
          data: { api_config_id: cfg.id ?? cfg.data?.id, model: "stub-model" },
          headers: auth,
        });
        expect(rb.ok()).toBeTruthy();
        return p;
      });
    const base = `${ORIGIN}/api/novels/${pid}`;

    const ra = await request.post(`${base}/chapters/vol-1-ch-1/archive`, {
      data: { full_text: PROSE, ai_summary: false },
      headers: auth,
    });
    expect((await ra.json()).state).toBe("extracting");
    // 等提取失败（章不归档）
    let failed = false;
    for (let i = 0; i < 100; i++) {
      const d = await (await fetch(`${base}/chapters/vol-1-ch-1/dossier`, { headers: auth })).json();
      if (d.extraction?.state === "failed") { failed = true; break; }
      await new Promise((r) => setTimeout(r, 200));
    }
    expect(failed).toBeTruthy();

    // UI：操作页签归档卡失败态 → 跳过提取仍归档
    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.locator(".col-tree .ch").first().click();
    await page.getByRole("tab", { name: /^操作/ }).click();
    await expect(page.getByTestId("archive-skip")).toBeVisible({ timeout: 15000 });
    // 三段进度条（c-ops-archive-stages）：提取段标失败
    await expect(page.getByTestId("archive-stages")).toContainText("失败");
    page.once("dialog", (dlg) => dlg.accept());
    await page.getByTestId("archive-skip").click();
    // 归档落地＋未提取态
    let archived = false;
    for (let i = 0; i < 50; i++) {
      const ch = await (await fetch(`${base}/chapters/vol-1-ch-1`, { headers: auth })).json();
      if (ch.status === "archived") { archived = true; break; }
      await new Promise((r) => setTimeout(r, 200));
    }
    expect(archived).toBeTruthy();
    // 未提取态：归档卡出现补提取入口
    await expect(page.getByTestId("archive-backfill")).toBeVisible({ timeout: 15000 });
  } finally {
    await restore();
    await new Promise<void>((r) => bad.close(() => r()));
  }
});
