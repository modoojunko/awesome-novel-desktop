// 封面/头像上传型工坊 E2E（c-cover-avatar-ui 4.2）：
//   上传 → 候选列表 → 采用 → 书架刷新可见封面 → 8s 撤销回到无图。
// 环境隔离（本会话自查规则）：
//   · E2E_BASE_URL  走本会话专属 vite（5174）
//   · E2E_API_BASE  走本会话专属 C端 后端（18000，DATA_ROOT 在 /tmp）
//   · 不依赖 S端 / config.json 注入：会话 token 由本 spec 经
//     E2E_TOKEN_FILE（隔离后端 DATA_ROOT 下的 config.json）写入后端本地 OAuth 会话
import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { stubUpdateNotice } from "./helpers";

const ORIGIN = process.env.E2E_BASE_URL || "http://127.0.0.1:5174";
const API = process.env.E2E_API_BASE || "http://127.0.0.1:18000";
// 隔离后端的 DATA_ROOT/config.json（e2e 启动脚本注入；缺省按隔离 tmp 约定）
const TOKEN_FILE =
  process.env.E2E_TOKEN_FILE || "/tmp/ai-novel-e2e-iso/data/config.json";

const TOKEN = `e2e-img-${randomUUID().hex ?? randomUUID().slice(0, 8)}-${Date.now()}`;
const USER = `e2e_img_${Date.now().toString(36)}`;

function pngBytes(w = 900, h = 700): Buffer {
  // 最小合法 PNG（1x1 白底）放大交给后端 Pillow 处理；尺寸断言走响应宽高
  // （后端会裁到 768×1024），这里只要求「是张能解码的图」。
  const b64 =
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
  return Buffer.from(b64, "base64");
}

/** 把会话写进隔离后端的 config.json（auth_local.get_local_config 按 mtime 失效）。 */
async function writeBackendSession() {
  let cfg: Record<string, unknown> = {};
  try {
    cfg = JSON.parse(fs.readFileSync(TOKEN_FILE, "utf-8"));
  } catch {
    /* 首次无文件 */
  }
  cfg.token = TOKEN;
  cfg.username = USER;
  cfg.tier = "trial";
  cfg.last_login_at = new Date().toISOString();
  const tmp = `${TOKEN_FILE}.tmp`;
  fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true });
  fs.writeFileSync(tmp, JSON.stringify(cfg, null, 2));
  fs.renameSync(tmp, TOKEN_FILE);
  // 后端按文件签名缓存；写后留 200ms 让 get_local_config 失效重读
  await new Promise((r) => setTimeout(r, 200));
}

/** 浏览器层钉死登录态壳层请求：check-auth/verify/门户/拆书角标。 */
async function stubShell(page: Page) {
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), TOKEN);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  await page.route("**/api/auth/verify", (r) =>
    r.fulfill({
      json: { tier: "trial", is_member: true, expired: false, trial_remaining_days: 7 },
    }),
  );
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { has_api_key: false, portal_url: "" } }),
  );
  await page.route("**/api/deconstruct/tasks", (r) =>
    r.fulfill({ json: { tasks: [], heartbeat: { running: 0, queued: 0 }, badge: 0 } }),
  );
  // 写作能力探测钉成 dev 已装态（source=dev 静默），避免首装弹窗锁死书架
  await page.route("**/api/prompt-pack/probe", (r) =>
    r.fulfill({
      json: { installed_version: "2026.10.23-1", latest_version: "2026.10.23-1", update_available: false, source: "dev" },
    }),
  );
}

test.describe("封面/头像上传型工坊", () => {
  test("上传 → 候选 → 采用 → 书架刷新可见 → 撤销回无图", async ({ page }) => {
    await writeBackendSession();
    await stubShell(page);
    await stubUpdateNotice(page, "none");

    // 建书走 API（UI 只做工坊链路；e2e 建书向导另有 creation-flow 钉）
    const bookName = `e2e封面${Date.now().toString(36)}`;
    const created = await fetch(`${API}/api/novels`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ name: bookName, source: "manual" }),
    });
    expect(created.ok).toBeTruthy();
    const book = (await created.json()) as { id: string; name: string };

    await page.goto(`${ORIGIN}/#/novels`);
    const card = page.locator(".book-card", { hasText: bookName });
    await expect(card).toBeVisible({ timeout: 15000 });

    // 无图态：打开封面工坊
    await card.getByRole("button", { name: "添加封面" }).click();
    await expect(page.getByRole("heading", { name: new RegExp(`^封面 · ${bookName}$`) })).toBeVisible();
    await expect(page.getByText("还没有封面")).toBeVisible();

    // 上传 → 候选出现
    await page.setInputFiles('input[type="file"]', {
      name: "cover.png",
      mimeType: "image/png",
      buffer: pngBytes(),
    });
    const uploaded = page.waitForResponse(
      (r) => r.request().method() === "POST" && r.url().includes("/image-assets"),
    );
    await uploaded;
    const candidateCard = page.locator(".img-candidate");
    await expect(candidateCard).toHaveCount(1, { timeout: 15000 });
    // 未采用前当前图仍是空态（占位与候选并存是有意设计）

    // 采用 → 当前图出现；8s 撤销条出现；空态占位消失
    await candidateCard.getByRole("button", { name: "使用" }).click();
    await expect(page.locator(".img-undo")).toBeVisible({ timeout: 15000 });
    await expect(page.locator(".img-current-img")).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("还没有封面")).toHaveCount(0);

    // 同一会话内撤销（8s 窗口；首次采用撤销＝无 previous 可回）→ 空态回归
    await page.locator(".img-undo").getByRole("button", { name: "撤销" }).click();
    await expect(page.getByText("还没有封面")).toBeVisible({ timeout: 15000 });

    // 撤销后书架无封面缩略图
    await page.keyboard.press("Escape");
    await page.goto(`${ORIGIN}/#/novels`);
    await expect(
      page.locator(".book-card", { hasText: bookName }).locator(".book-cover-img"),
    ).toHaveCount(0, { timeout: 15000 });

    // 重开工坊再采用 → 书架刷新可见封面缩略图（采用已外化到书卡）
    await page
      .locator(".book-card", { hasText: bookName })
      .getByRole("button", { name: "添加封面" })
      .click();
    await expect(page.getByRole("heading", { name: new RegExp(`^封面 · ${bookName}$`) })).toBeVisible();
    await page.setInputFiles('input[type="file"]', {
      name: "cover2.png",
      mimeType: "image/png",
      buffer: pngBytes(700, 900),
    });
    const candidate2 = page.locator(".img-candidate");
    await expect(candidate2).toHaveCount(1, { timeout: 15000 });
    await candidate2.getByRole("button", { name: "使用" }).click();
    await expect(page.locator(".img-current-img")).toBeVisible({ timeout: 15000 });
    await page.keyboard.press("Escape");
    await page.goto(`${ORIGIN}/#/novels`);
    await expect(
      page.locator(".book-card", { hasText: bookName }).locator(".book-cover-img"),
    ).toBeVisible({ timeout: 15000 });

    // teardown：产品路径删书（软删；封面资产级联清）
    await fetch(`${API}/api/novels/${book.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
  });

  // c-image-config-ux-fix：配置面板「测试连接」失败呈现供应商摘要（全桩，不依赖
  // 真实供应商/权益——测试端点的真拦面由后端 pytest 与档位矩阵覆盖）。
  test("图像配置：测试连接失败呈现摘要", async ({ page }) => {
    await writeBackendSession();
    await stubShell(page);
    await stubUpdateNotice(page, "none");
    await page.route("**/api/image-configs**", async (r) => {
      const url = r.request().url();
      if (url.includes("/image-configs/test")) {
        return r.fulfill({
          json: {
            ok: true,
            data: {
              ok: false, model: "doubao-seedream-5-0-260128", elapsed_ms: 320,
              error: { kind: "auth", message: "API Key 无效或无权限" },
            },
          },
        });
      }
      return r.fulfill({
        json: {
          ok: true,
          data: [{
            id: "cfg-e2e", name: "封面主力", provider: "volcengine",
            base_url: "https://ark.cn-beijing.volces.com/api/v3",
            api_key_masked: "ark-****e2e", default_model: "doubao-seedream-5-0-260128",
            models: ["doubao-seedream-5-0-260128"], declared_capabilities: {},
            is_default: true, status: "active", last_test_status: null,
          }],
        },
      });
    });
    // 大模型页签与用量的噪声（页签隐藏但挂载即拉）：桩成空，免真实后端依赖
    await page.route("**/api/api-configs*", (r) =>
      r.fulfill({ json: { ok: true, data: [] } }));
    await page.route("**/api/usage*", (r) =>
      r.fulfill({ json: { ok: true, data: { all: 0, month: 0, today: 0, by_config: [] } } }));

    await page.goto(`${ORIGIN}/#/config?tab=image`);
    await expect(page.getByText("封面主力")).toBeVisible({ timeout: 15000 });
    // 单模型格改版：卡片以「模型：{id}」呈现，不再有清单 chips
    await expect(page.getByText("模型：doubao-seedream-5-0-260128")).toBeVisible();
    await expect(page.locator(".m-chip")).toHaveCount(0);

    await page.getByRole("button", { name: "添加图像模型" }).click();
    await page.getByPlaceholder("模型 id").fill("doubao-seedream-5-0-260128");
    await page.locator(".mcard-foot").getByRole("button", { name: "测试连接" }).click();
    const bad = page.locator(".tresult.bad");
    await expect(bad).toBeVisible({ timeout: 10000 });
    await expect(bad).toContainText("测试失败");
    await expect(bad).toContainText("API Key 无效或无权限");
  });
});
