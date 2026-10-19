import { expect, test } from "@playwright/test";
import { stubUpdateNotice } from "./helpers";

/**
 * A 路导入自有书（c-import-direct）：
 * 书架「导入」→ 选 txt → 确认 42 章/卷 → 直接导入 → 工作台第 43 章待写 →
 * 预览里 42 章标「原文」、完本进度「暂无作者章」。
 *
 * 会话隔离：私有栈（8104/5294）+ 临时 DATA_ROOT/config.json；不连共享 demo/S端。
 */
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const TOKEN = process.env.E2E_IMPORT_TOKEN;

// 需要私有栈预置的 config token（本地 E2E_IMPORT_TOKEN=... 运行）；CI 无此 env 时跳过，
// 避免把私有栈端口/token 假设带进 nightly。
test.skip(!TOKEN, "需要私有栈 E2E_IMPORT_TOKEN");

function sampleText(chapters = 42): string {
  const lines = ["第一卷 风起"];
  for (let i = 1; i <= chapters; i++) {
    lines.push(`第${i}章 第${i}节`);
    lines.push(`第${i}章的正文。张三走进渡口，看见灯还亮着。`.repeat(3));
  }
  return lines.join("\n") + "\n";
}

test.describe("导入自有书 A 路", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((token) => {
      localStorage.setItem("auth_token", token);
      localStorage.setItem("auth_username", "import-e2e");
    }, TOKEN!);
    await page.route("**/api/auth/verify", (r) =>
      r.fulfill({ json: { tier: "pro", is_member: true, expired: false, trial_remaining_days: 0 } }),
    );
    await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
    await page.route("**/api/auth/config", (r) =>
      r.fulfill({ json: { has_api_key: true, portal_url: "" } }),
    );
    await stubUpdateNotice(page, "none");
  });

  test("txt 42 章 → 第 43 章待写 → 预览原文", async ({ page }) => {
    await page.goto(`${ORIGIN}/#/novels`);
    await expect(page.getByRole("heading", { name: "我的作品" })).toBeVisible();
    await page.locator('button[title*="导入我的书"]').click();
    await expect(page.getByText("导入我的书", { exact: true })).toBeVisible();

    await page.locator('input[type="file"]').setInputFiles({
      name: "长夜灯.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(sampleText(42), "utf-8"),
    });
    const next1 = page.getByRole("button", { name: "下一步：确认卷章" });
    await expect(next1).toBeEnabled({ timeout: 15000 });
    await next1.click();

    await expect(page.getByText("书目录 · 按章切分")).toBeVisible();
    const next2 = page.getByRole("button", { name: "下一步：导入方式" });
    await expect(next2).toBeEnabled();
    await next2.click();

    await expect(page.getByText("直接导入（只带正文）")).toBeVisible();
    await page.getByRole("button", { name: "创建并开始写作" }).click();

    await page.waitForURL(/#\/novel\//, { timeout: 30000 });
    await expect(page.locator(".bar-here .bh-t")).toContainText("第 43 章", { timeout: 15000 });
    await expect(page.getByTestId("home-resume")).toContainText("开始写第 43 章");
    await expect(page.getByTestId("import-next-checklist")).toContainText("补主线与当前卷卷纲");
    await expect(page.getByText("原文").first()).toBeVisible();

    // 打开第 10 章：原文正文可读（顶栏「当前主线」仍应是第 43 章，不随历史章回退）
    await page.locator(".tree .ch", { hasText: "第十章" }).first().click();
    await page.getByRole("tab", { name: /^正文/ }).click();
    await expect(page.locator(".ProseMirror")).toContainText("第10章的正文");
    await expect(page.locator(".bar-here .bh-t")).toContainText("第 43 章");

    await page.getByRole("button", { name: /预览/ }).click();
    await expect(page.getByText("全书概览")).toBeVisible();
    await expect(page.locator(".pv-ch .pill", { hasText: "原文" }).first()).toBeVisible();
    await expect(page.locator(".pv-vol", { hasText: "风起" }).first()).toContainText("第一卷 · 风起");
    await expect(page.getByText("第一卷 风起")).toHaveCount(0);
    await expect(page.getByText("暂无作者章")).toBeVisible();
  });
});
