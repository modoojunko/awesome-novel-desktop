import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";

// =========================================================================
// /config API Key 管理 E2E（补测非 AI 功能：CRUD + 连接测试）
//   ① 空态 + 表单顺序校验（配置名称 → 供应商 → Base URL → API Key）
//   ② 添加（连接测试网络错误：127.0.0.1:1 立即 ConnectError → network_error）
//     + 删除 + 撤销真实恢复（后端软删 restore，同 id 复活）
// =========================================================================

const S_API = "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
// docker C端 后端的 config.json（bind mount .docker-data/client → /app/data）
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);

/** S端 注册并登录，返回 JWT（免费用户，套餐 none）。 */
async function sRegisterAndLogin() {
  const name = `e2e_cfg_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!"; // 测试口令运行时拼装（门禁：源码不落明文口令）
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password,
      security_question: "最喜欢的颜色",
      security_answer: "蓝色",
    }),
  });
  const regBody = await reg.json();
  if (regBody.code !== 0) {
    throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  }
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) {
    throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  }
  return { token: loginBody.data.token as string, username: name };
}

/** 把 S端 会话写入 config.json，返回恢复函数。
 * 竞态守卫：上一测试 teardown 残留页面的 check-auth（真实 pc_hash 命中 grant）
 * 会在服务端异步回写 config.json 冲掉注入 token → 401；写入后观察，被冲掉
 * 即重写，连续两轮稳定才放行。
 */
async function writeOAuthSession(t: string, u: string) {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = "trial";
  cfg.last_login_at = new Date().toISOString();
  // 关键：随机 pc_hash 使 S端 check-auth 无该设备 grant（返回 code 1），useAuthHeal 不覆盖
  // config.json，注入 token 保持有效。保留真实 pc_hash 会命中 modoojunko 已授权设备 → 401。
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

/** 每测试独立会话：S端 注册登录 → 写 config.json → 注入 localStorage。 */
async function setupSession(page: Page): Promise<{ restore: () => void }> {
  const { token, username } = await sRegisterAndLogin();
  const restore = await writeOAuthSession(token, username);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：e2e 注入的 pc_hash 在 S端 无设备授权（code 1），后端会
  // 据此清空 config.json 的注入 token → 业务请求 401（已知环境阻塞）。桩掉这次
  // 往返即可保住注入会话；会员判定仍走后端 check_permission()（读 config.json tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore };
}

// -------------------------------------------------------------------------
// ① 空态 + 表单顺序校验
// -------------------------------------------------------------------------

test("模型配置：空态 + 表单顺序校验（名称→供应商→Base URL→API Key）", async ({
  page,
}) => {
  const { restore } = await setupSession(page);
  try {
    await page.goto(`${ORIGIN}/#/config`);

    // 空态：h1 + 空态文案（header 与空态各有「添加 API Key」按钮 → .first()）
    await expect(
      page.getByRole("heading", { name: "模型配置", exact: true }),
    ).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("还没有模型配置")).toBeVisible();

    // 打开表单
    await page.getByRole("button", { name: "添加 API Key" }).first().click();
    await expect(
      page.getByRole("heading", { name: "添加 API Key" }),
    ).toBeVisible();

    // 顺序校验：空表单 → 配置名称
    // （name/baseUrl/apiKey 输入带 required → 浏览器原生校验先于 handleSubmit 拦截；
    //   移除 required 让 JS 校验错误按顺序可达，见 ApiConfigForm.handleSubmit）
    await page
      .locator("form input[required]")
      .evaluateAll((els) => els.forEach((el) => el.removeAttribute("required")));
    await page.getByRole("button", { name: "保存并测试连接" }).click();
    await expect(page.getByText("请输入配置名称")).toBeVisible();

    // 填名称 → 供应商
    await page.getByPlaceholder("例如：主线 · OpenAI").fill("e2e配置");
    await page.getByRole("button", { name: "保存并测试连接" }).click();
    await expect(page.getByText("请选择供应商")).toBeVisible();

    // 选供应商 → Base URL（openai-compat 无默认 URL，需手填）
    await page.getByRole("button", { name: "OpenAI 兼容" }).click();
    await page.getByRole("button", { name: "保存并测试连接" }).click();
    await expect(page.getByText("请输入 Base URL")).toBeVisible();

    // 填 Base URL → API Key
    await page.getByPlaceholder("https://api.openai.com").fill("http://127.0.0.1:1");
    await page.getByRole("button", { name: "保存并测试连接" }).click();
    await expect(page.getByText("请输入 API Key")).toBeVisible();

    // 取消关闭表单 → 空态回归
    await page.getByRole("button", { name: "取消" }).click();
    await expect(page.getByText("还没有模型配置")).toBeVisible();
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ② 添加 + 删除 + Undo toast 展示
// -------------------------------------------------------------------------

test("模型配置：添加（网络错误）→ 删除 → Undo toast 展示", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await page.goto(`${ORIGIN}/#/config`);
    await expect(page.getByText("还没有模型配置")).toBeVisible({
      timeout: 10000,
    });

    // 添加：填写完整 → 保存并测试连接
    await page.getByRole("button", { name: "添加 API Key" }).first().click();
    await page.getByPlaceholder("例如：主线 · OpenAI").fill("e2e测试配置");
    await page.getByRole("button", { name: "OpenAI 兼容" }).click();
    await page.getByPlaceholder("https://api.openai.com").fill("http://127.0.0.1:1");
    await page.getByPlaceholder("sk-...").fill("sk-e2e-invalid");

    // POST /api/v1/api-configs（创建；随后自动连接测试，127.0.0.1:1 → network_error）
    const created = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().includes("/api/v1/api-configs") &&
        r.url().endsWith("/api-configs"),
    );
    await page.getByRole("button", { name: "保存并测试连接" }).click();
    await created;

    // 卡片出现（表单弹窗无该文本 → hasText 只命中配置卡片）+ 网络错误徽标
    const card = page.locator(".cfg-card", { hasText: "e2e测试配置" });
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.getByText("网络错误")).toBeVisible({ timeout: 10000 });

    // 删除 → 确认对话框
    await card.getByRole("button", { name: "删除" }).click();
    await expect(
      page.getByRole("heading", { name: "删除配置" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "确认删除" }).click();

    // 卡片消失 → 空态回归
    await expect(card).toHaveCount(0);
    await expect(page.getByText("还没有模型配置")).toBeVisible({
      timeout: 5000,
    });

    // Undo toast 展示 + 点撤销 → 配置真实恢复（软删 restore 同 id 复活，卡片回来）
    await expect(page.getByText("已删除「e2e测试配置」")).toBeVisible();
    await page.getByRole("button", { name: "撤销" }).click();
    await expect(card).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("已删除「e2e测试配置」")).toHaveCount(0);
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ③ 接口格式（c-api-format）：默认 OpenAI、GLM 可切、官方卡锁定、
//    URL 不预填（拍板）、编辑态持久化
// -------------------------------------------------------------------------
test("模型配置：接口格式——默认/切换/锁定/URL 不预填/编辑持久化", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await page.goto(`${ORIGIN}/#/config`);
    await expect(page.getByText("还没有模型配置")).toBeVisible({ timeout: 10000 });

    await page.getByRole("button", { name: "添加 API Key" }).first().click();
    const seg = page.getByRole("group", { name: "接口格式" });
    const openaiBtn = seg.getByRole("button", { name: "OpenAI 格式" });
    const anthropicBtn = seg.getByRole("button", { name: "Anthropic 格式" });

    // 默认 OpenAI 格式 on
    await expect(openaiBtn).toHaveClass(/on/);

    // 选 GLM：URL 不预填（拍板），placeholder 维持 openai 示例
    await page.getByRole("button", { name: "GLM", exact: true }).click();
    await expect(page.locator("#cfBase")).toHaveValue("");
    await expect(openaiBtn).toHaveClass(/on/);

    // 切 Anthropic 格式：URL 仍为空，placeholder 随格式切换
    await anthropicBtn.click();
    await expect(anthropicBtn).toHaveClass(/on/);
    const urlInput = page.locator("#cfBase");
    await expect(urlInput).toHaveAttribute("placeholder", "https://api.anthropic.com");

    // 手填 URL 后切回 OpenAI 格式：值不被覆盖
    await urlInput.fill("https://my-relay.example.com/v1");
    await openaiBtn.click();
    await expect(urlInput).toHaveValue("https://my-relay.example.com/v1");

    // OpenAI 官方卡：单格式厂商 → seg 锁定在 OpenAI 格式
    await page.getByRole("button", { name: "OpenAI", exact: true }).click();
    await expect(seg).toHaveClass(/lock/);
    await expect(anthropicBtn).toBeDisabled(); // 非锁定格式置灰
    await expect(openaiBtn).toBeEnabled(); // 锁定格式本身可点（锁定态禁的是切换）
    await expect(openaiBtn).toHaveClass(/on/);

    // GLM + Anthropic 格式完整走一遍创建（127.0.0.1:1 → 网络错误照常入库）
    await page.getByRole("button", { name: "GLM", exact: true }).click();
    await anthropicBtn.click();
    await page.getByPlaceholder("例如：主线 · OpenAI").fill("e2e格式配置");
    await urlInput.fill("http://127.0.0.1:1");
    await page.getByPlaceholder("sk-...").fill("sk-e2e-fmt");
    const created = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().includes("/api/v1/api-configs") &&
        r.url().endsWith("/api-configs"),
    );
    await page.getByRole("button", { name: "保存并测试连接" }).click();
    const resp = await created;
    expect(await resp.json()).toMatchObject({ api_format: "anthropic" });

    // 编辑重开：格式持久化为 Anthropic、URL 原值保留
    const card = page.locator(".cfg-card", { hasText: "e2e格式配置" });
    await expect(card).toBeVisible({ timeout: 10000 });
    await card.getByRole("button", { name: "编辑" }).click();
    await expect(page.getByRole("heading", { name: "编辑配置" })).toBeVisible();
    await expect(anthropicBtn).toHaveClass(/on/);
    await expect(urlInput).toHaveValue("http://127.0.0.1:1");
    await page.getByRole("button", { name: "取消" }).click();
  } finally {
    restore();
  }
});
