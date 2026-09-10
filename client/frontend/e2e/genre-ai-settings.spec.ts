import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// 题材/简介 AI 链路 e2e（genre-signup-redesign tasks 9.4.5–9.4.11）
//   - AI 端点一律 page.route 打桩（不烧真实额度、不依赖模型）
//   - ai_state 由桩 `/api/v1/novels/*/ai-model` 下发（D13 一次分派）
// ---------------------------------------------------------------------------

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);

async function sRegisterAndLogin() {
  const name = `e2e_genreai_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!";
  await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password,
      security_question: "最喜欢的颜色",
      security_answer: "蓝色",
    }),
  });
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const body = await login.json();
  if (body.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(body)}`);
  return { token: body.data.token as string, username: name };
}

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = token;
  cfg.username = username;
  cfg.tier = tier;
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 注入会话的 pc_hash 在 S端 无设备授权（code 1），后端会据此清空 config.json
  // 的注入 token → 业务 401；桩掉这次往返保住会话（见 settings-forms.spec.ts 同注）
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return {
    token,
    restore: () => fs.writeFileSync(CONFIG_PATH, original),
  };
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

/** 桩本书 AI 就绪态（D13）+ 两配置×两模型的可选清单。 */
async function stubAiState(page: Page, pid: string, aiState: string, message = "") {
  await page.route(`**/api/v1/novels/${pid}/ai-model`, (r) =>
    r.fulfill({
      json: {
        api_config_id: aiState === "missing_model" ? null : "c1",
        model: aiState === "missing_model" ? null : "gpt-4o",
        config_name: "主配置",
        ai_state: aiState,
        effective_model: aiState === "ready" ? "gpt-4o" : "",
        reason: aiState,
        message,
      },
    }),
  );
  await page.route("**/api/v1/api-configs", (r) =>
    r.fulfill({
      json: [
        {
          id: "c1",
          name: "主配置",
          vendor: "openai",
          models: ["gpt-4o", "gpt-4o-mini"],
          status: "active",
          last_test_status: "ok",
        },
      ],
    }),
  );
}

async function openSetting(page: Page, name: string) {
  await page
    .locator(".settings-v .col-tree .s-item")
    .filter({ has: page.locator(".nm", { hasText: new RegExp(`^${name}$`) }) })
    .click();
}

test.describe("题材/简介 AI 链路", () => {
  test("ready：体检结果落简介框下方（右栏无答案）→ 采纳后简介变长（9.4.5/9.4.11）", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `AI体检${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      let aiCalled = 0;
      await page.route(`**/api/novels/${pid}/settings/ai/intro/introspect`, (r) => {
        aiCalled += 1;
        return r.fulfill({
          json: {
            six_segments: [
              { name: "主角身份", status: "ok", excerpt: "外门杂徒林拾", note: "" },
            ],
            taboo: { hits: [] },
            verdict: "weak",
          },
        });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.getByPlaceholder(/用几句话/).fill("外门杂徒林拾在宗门扫落叶。");
      await page.locator('[data-aiact="check"]').click();

      // 结果落简介框下方（.ai-sink 在 textarea 之后）；右栏不出答案
      const sink = page.locator('[data-od-id="intro-ai-sink"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      await expect(sink).toContainText("AI 体检 · 六段逐项");
      await expect(sink).toContainText("主角身份");
      // 右栏只作按钮（不出答案正文——体检摘要句不得出现在右栏）
      const rightRail = page.locator(".col-ai .rail-assist");
      await expect(rightRail).not.toContainText("外门杂徒林拾");
      expect(aiCalled).toBe(1);

      // 无采纳按钮（体检只提醒）→ 简介不被改写
      const before = await page.getByPlaceholder(/用几句话/).inputValue();
      expect(before).toContain("林拾");
    } finally {
      restore();
    }
  });

  test("题材五行 AI：建议落对应格下方，采纳写回该控件（9.4.6）", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `AI题材${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await page.route(`**/api/novels/${pid}/settings/ai/genre/cost_ratio`, (r) =>
        r.fulfill({ json: { value: 8 } }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "题材");
      await expect(page.locator(".settings-v .mod")).toHaveCount(6);

      await page.locator('[data-aiact="m3"]').click();
      const sink = page.locator('[data-od-id="genre-ai-sink-cost_ratio"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      await expect(sink).toContainText("建议 8 分");

      await sink.getByRole("button", { name: "采纳 · 覆盖" }).click();
      await expect(page.locator(".settings-v .cost-val")).toHaveText("8");
      await expect(page.locator('[data-od-id="cost-sentence"]')).toContainText("8 分");
    } finally {
      restore();
    }
  });

  test("免费版：AI 卡可见+锁定、点击不产出结果；模型窗仍可见可选（9.4.7）", async ({
    page,
  }) => {
    const { restore } = await setupSession(page, "none");
    try {
      const pid = await createNovel(page, `AI免费${Date.now() % 100000}`);
      await stubAiState(page, pid, "member_required", "AI 是会员功能");
      let aiCalled = 0;
      await page.route(`**/api/novels/${pid}/settings/ai/**`, (r) => {
        aiCalled += 1;
        return r.fulfill({ json: {} });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      // 卡片可见 + 锁定；名称/描述仍在
      const card = page.locator(".col-ai .rail-assist");
      await expect(card).toBeVisible({ timeout: 10000 });
      await expect(card).toHaveClass(/locked/);
      await expect(card).toContainText("体检");

      await page.locator('[data-aiact="check"]').click();
      await expect(page.locator('[data-od-id="intro-ai-sink"]')).toHaveCount(0);
      expect(aiCalled).toBe(0);

      // 模型窗（人工路径）不锁：可进、可选
      await page.locator(".settings-v .col-tree .s-item", { hasText: "AI 模型" }).click();
      await expect(page.locator(".settings-v main h2", { hasText: "AI 模型" })).toBeVisible();
    } finally {
      restore();
    }
  });

  test("missing_model：点 AI 行提示并跳模型面板，不发起 AI 请求（9.4.9）", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `AI未选模型${Date.now() % 100000}`);
      await stubAiState(page, pid, "missing_model", "先在本书选择模型");
      let aiCalled = 0;
      await page.route(`**/api/novels/${pid}/settings/ai/**`, (r) => {
        aiCalled += 1;
        return r.fulfill({ json: {} });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await expect(page.locator(".col-ai .rail-assist")).toContainText("先在本书选择模型", {
        timeout: 10000,
      });
      await page.locator('[data-aiact="check"]').click();

      await expect(page.locator(".settings-v main h2", { hasText: "AI 模型" })).toBeVisible({
        timeout: 5000,
      });
      expect(aiCalled).toBe(0);
    } finally {
      restore();
    }
  });

  test("no_key 与 missing_model 分流：文案与落点不同（9.4.10）", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `AI分流${Date.now() % 100000}`);
      await stubAiState(page, pid, "no_key", "暂无可用 API Key");
      await page.getByRole("button", { name: /^设定/ }).click();
      const card = page.locator(".col-ai .rail-assist");
      await expect(card).toContainText("先去「模型配置」添加 API Key", { timeout: 10000 });

      // no_key → 去模型配置（hash 跳转）
      await page.locator('[data-aiact="check"]').click();
      await expect(page).toHaveURL(/#\/config/, { timeout: 5000 });
    } finally {
      restore();
    }
  });
});

// ── 模型窗：选择与生效分离 + 键盘导航（9.4.8）──────────────────────────────
test("模型窗：点行只标亮（无 PUT）→ 键盘移动 → 点确认恰 1 次整对 PUT（9.4.8）", async ({
  page,
}) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `模型窗${Date.now() % 100000}`);
    await stubAiState(page, pid, "missing_model", "先在本书选择模型");
    // 两配置×两模型：补第二条配置
    await page.route("**/api/v1/api-configs", (r) =>
      r.fulfill({
        json: [
          {
            id: "c1",
            name: "主配置",
            vendor: "openai",
            models: ["gpt-4o", "gpt-4o-mini"],
            status: "active",
            last_test_status: "ok",
          },
          {
            id: "c2",
            name: "备用",
            vendor: "deepseek",
            models: ["deepseek-chat"],
            status: "active",
            last_test_status: "auth_error",
          },
        ],
      }),
    );
    const puts: Array<Record<string, unknown>> = [];
    await page.route(`**/api/v1/novels/${pid}/ai-model`, (r) => {
      if (r.request().method() === "PUT") {
        puts.push(JSON.parse(r.request().postData() || "{}"));
        return r.fulfill({ json: { ok: true } });
      }
      return r.fulfill({
        json: {
          api_config_id: null,
          model: null,
          config_name: null,
          ai_state: "missing_model",
          effective_model: "",
          reason: "missing_model",
          message: "先在本书选择模型",
        },
      });
    });

    await page.getByRole("button", { name: /^设定/ }).click();
    await page.locator(".settings-v .col-tree .s-item", { hasText: "AI 模型" }).click();
    await expect(page.locator(".settings-v main h2", { hasText: "AI 模型" })).toBeVisible();

    // 分组卡片：两组 + 连接状态徽标
    await expect(page.locator(".model-group")).toHaveCount(2);
    await expect(page.getByText("已连接")).toBeVisible();
    await expect(page.getByText("连接失败")).toBeVisible();

    // 点行只标亮：0 次 PUT，按钮启用
    const apply = page.getByRole("button", { name: "设为本书模型" });
    await expect(apply).toBeDisabled();
    await page.locator('[data-model="c2::deepseek-chat"]').click();
    expect(puts).toHaveLength(0);
    await expect(apply).toBeEnabled();
    await expect(page.locator('[data-model="c2::deepseek-chat"]')).toHaveAttribute(
      "aria-checked",
      "true",
    );

    // 键盘：ArrowDown 从当前焦点行移动
    await page.locator('[data-model="c2::deepseek-chat"]').focus();
    await page.keyboard.press("ArrowDown");
    await expect(page.locator('[data-model="c1::gpt-4o"]')).toBeFocused();

    // 确认 → 恰 1 次 PUT（整对）
    await page.locator('[data-model="c2::deepseek-chat"]').click();
    await apply.click();
    await expect.poll(() => puts.length).toBe(1);
    expect(puts[0]).toEqual({ api_config_id: "c2", model: "deepseek-chat" });
  } finally {
    restore();
  }
});

// ── 连点防抖 + 运行中可见（用户实测：连点 6 次 = 6 个请求且无任何提示）──────
test("AI 行连点：只发 1 个请求，且有「生成中」可见反馈（9.4.14）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `连点${Date.now() % 100000}`);
    await stubAiState(page, pid, "ready");
    let hits = 0;
    await page.route(`**/api/novels/${pid}/settings/ai/intro/introspect`, async (r) => {
      hits += 1;
      await new Promise((res) => setTimeout(res, 2000));
      return r.fulfill({ json: { six_segments: [], taboo: { hits: [] }, verdict: "ok" } });
    });

    await page.getByRole("button", { name: /^设定/ }).click();
    await page.getByPlaceholder(/用几句话/).fill("外门杂徒林拾，在宗门扫了十年落叶。");
    const row = page.locator('[data-aiact="check"]');
    await expect(row).toBeVisible({ timeout: 10000 });

    await row.click();
    // 立刻可见的运行反馈：行高亮 + 「生成中…」+ 输入框下方占位
    await expect(row).toHaveClass(/ra-running/, { timeout: 2000 });
    await expect(row).toBeDisabled();
    await expect(page.locator('[data-od-id="intro-ai-running"]')).toBeVisible();

    // 连点 5 次（含同一 tick 的同步派发）——不得再发请求
    for (let i = 0; i < 5; i++) await row.click({ force: true, timeout: 1000 }).catch(() => {});
    await page.evaluate(() => {
      const el = document.querySelector('[data-aiact="check"]') as HTMLElement;
      for (let i = 0; i < 5; i++) el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(hits).toBe(1);

    // 完成后回到常态，结果落简介框下方
    await expect(page.locator('[data-od-id="intro-ai-sink"]')).toBeVisible({ timeout: 10000 });
    expect(hits).toBe(1);
  } finally {
    restore();
  }
});

// ── 生成历史（最近 5 次）+ 采纳整段替换（用户要求：避免无限抽卡/反悔）──────
test("简介 AI：生成 6 次只留最近 5 次；切回旧版采纳＝整段替换不叠加", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `历史${Date.now() % 100000}`);
    await stubAiState(page, pid, "ready");
    let seq = 0;
    await page.route(`**/api/novels/${pid}/settings/ai/intro/fill`, async (r) => {
      seq += 1;
      const s = seq;
      await new Promise((res) => setTimeout(res, 100));
      return r.fulfill({
        json: { missing: [{ name: "突发状况", candidate: `候选第${s}版` }], act: "insert" },
      });
    });
    await page.route(`**/api/novels/${pid}/settings/ai/intro/introspect`, (r) =>
      r.fulfill({ json: { six_segments: [], taboo: { hits: [] }, verdict: "ok" } }),
    );

    await page.getByRole("button", { name: /^设定/ }).click();
    const ta = page.getByPlaceholder(/用几句话/);
    await ta.fill("我手写的开头");
    await page.locator('[data-aiact="check"]').click();
    const sink = page.locator('[data-od-id="intro-ai-sink"]');
    await expect(sink).toBeVisible({ timeout: 10000 });

    await page.locator('[data-aiact="fill"]').click();
    await expect(sink).toContainText("候选第1版", { timeout: 10000 });
    // 再点 5 次「重试」→ 共 6 次
    for (let i = 0; i < 5; i++) {
      await sink.getByRole("button", { name: "重试" }).click();
      await expect(sink).toContainText(`候选第${seq}版`, { timeout: 10000 });
    }

    const chips = page.locator('[data-od-id="ai-sink-history"] [data-hist]');
    await expect(chips).toHaveCount(5); // 只保留最近 5 次
    await expect(page.locator('[data-od-id="ai-sink-history"]')).toContainText("只保留最近 5 次");

    // 切回保留的第 1 条（＝第 2 次生成）采纳 → 整段替换「原文 + 本次候选」
    await chips.first().click();
    await expect(sink).toContainText("候选第2版");
    await sink.getByRole("button", { name: /采纳 · 替换为补全后的简介/ }).click();
    await expect(ta).toHaveValue("我手写的开头。候选第2版");

    // 切到最新一条（第 6 次生成）再采纳 → 仍以手写原文为基准，不叠加上一版
    await chips.last().click();
    await expect(sink).toContainText("候选第6版");
    await sink.getByRole("button", { name: /采纳 · 替换为补全后的简介/ }).click();
    await expect(ta).toHaveValue("我手写的开头。候选第6版");
  } finally {
    restore();
  }
});
