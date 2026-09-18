// 下载成稿链路 E2E（manuscript-download，c-manuscript-download）：
//   预览右栏「下载成稿…」→ 弹层 → 选格式 → 发起 → 完成页 → 打开文件夹被调用；
//   另覆盖 409（备份在跑）文案区分、未选格式禁用。
//   手法：addInitScript 注入 pywebview 桥桩（pick_folder/default_dirs/open_folder 记录调用）
//   + page.route 全量打桩（同 design-parity 桩法，不依赖真实后端数据）。
import fs from "fs";
import path from "path";
import { test, expect, type Page } from "@playwright/test";

const PROTO_DIR = path.resolve(process.cwd(), "../../docs/design-c");
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const PID = "p1";

/** 注入桥桩：pick_folder 返回固定目录，open_folder 记录调用，default_dirs 给常用项。 */
async function stubBridge(page: Page, tmpDir: string) {
  await page.addInitScript((dir: string) => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: {
        pick_folder: async () => dir,
        default_dirs: async () => [
          { label: "文稿", path: "/tmp" },
          { label: "桌面", path: "/Users/stub/Desktop" },
        ],
        open_folder: async (p: string) => {
          const w = window as unknown as { __dlOpens?: string[] };
          w.__dlOpens = [...(w.__dlOpens ?? []), p];
          return true;
        },
      },
    };
  }, tmpDir);
}

function stubBookApi(
  page: Page,
  opts: { fail409?: boolean; failTask?: boolean; runningPolls?: number } = {},
) {
  let statusCalls = 0;
  page.route("**/api/**", (r) => r.fulfill({ json: {} }));
  page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  page.route("**/api/auth/verify", (r) =>
    r.fulfill({ json: { tier: "none", is_member: false, expired: false, trial_remaining_days: 0 } }),
  );
  page.route(`**/api/novels/${PID}`, (r) =>
    r.fulfill({ json: { id: PID, name: "星海拾遗", type: "科幻", genre: "科幻", genre_label: "科幻", source: "manual" } }),
  );
  page.route(`**/api/novels/${PID}/volumes`, (r) =>
    r.fulfill({
      json: [
        {
          ref: "vol-1",
          title: "星海初航",
          chapters: [
            { chapter: 1, title: "锚点", word_count: 70, status: "confirmed", has_prose: true, archived: true },
            { chapter: 2, title: "跃迁", word_count: 54, status: "confirmed", has_prose: true, archived: true },
          ],
        },
      ],
    }),
  );
  page.route(`**/api/novels/${PID}/readiness`, (r) =>
    r.fulfill({ json: { missing: [{ key: "world" }, { key: "hooks" }, { key: "characters" }, { key: "antiAI" }] } }),
  );
  page.route("**/api/manuscript/download/start", (r) => {
    if (opts.fail409) {
      return r.fulfill({
        status: 409,
        json: { detail: { message: "已有备份任务在进行中", running_kind: "backup" } },
      });
    }
    return r.fulfill({
      json: { code: 0, data: { state: "running", phase: "render", pct: 0, steps: [] } },
    });
  });
  page.route("**/api/manuscript/download/status", (r) => {
    if (opts.runningPolls) {
      // 先回 N 次 running（进度态可观察、后台运行有时序窗口），之后 done
      statusCalls += 1;
      const running = statusCalls <= opts.runningPolls;
      return r.fulfill({
        json: {
          code: 0,
          data: running
            ? { state: "running", phase: "render", pct: statusCalls * 10, steps: [], current: "正在下载 x.md" }
            : {
                state: "done",
                phase: "finalize",
                pct: 100,
                files: ["星海拾遗 · 主线全稿.md", "星海拾遗 · 主线全稿.docx"],
                steps: [
                  { format: "md", state: "完成", error: null },
                  { format: "docx", state: "完成", error: null },
                ],
                target_dir: "/tmp/dl-e2e",
                current: "",
              },
        },
      });
    }
    if (opts.failTask) {
      return r.fulfill({
        json: {
          code: 0,
          data: {
            state: "error",
            phase: "render",
            error: { code: "permission_denied", message: "无法写入所选目录：/tmp/dl-e2e" },
            steps: [{ format: "md", state: "失败", error: "无法写入所选目录：/tmp/dl-e2e" }],
          },
        },
      });
    }
    return r.fulfill({
      json: {
        code: 0,
        data: {
          state: "done",
          phase: "finalize",
          pct: 100,
          files: ["星海拾遗 · 主线全稿.md", "星海拾遗 · 主线全稿.docx"],
          steps: [
            { format: "md", state: "完成", error: null },
            { format: "docx", state: "完成", error: null },
          ],
          target_dir: "/tmp/dl-e2e",
          current: "",
        },
      },
    });
  });
}

async function gotoPreview(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("auth_token", "dl-stub-token");
    localStorage.setItem("auth_username", "m");
  });
  await page.goto(`/#/novel/${PID}`);
  await page.locator(".mtab", { hasText: "预览" }).click();
  await expect(page.locator('[data-od-id="download-open-card"]')).toBeVisible();
  await page.locator('[data-od-id="download-open"]').click();
  await expect(page.locator(".mcard")).toBeVisible();
}

test.describe("下载成稿链路", () => {
  test("下载链路：常用位置填充→格式勾选→发起→完成页→打开文件夹", async ({ browser }) => {
    test.skip(!fs.existsSync(PROTO_DIR), "仅本地（打桩链路）");
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await stubBridge(page, "/tmp/dl-e2e");
    stubBookApi(page);
    await gotoPreview(page);

    // 常用位置 chip 一键填充
    await page.locator(".ex-dirs .chip", { hasText: "文稿" }).click();
    await expect(page.locator('[data-od-id="download-dir"]')).toHaveValue("/tmp");
    // 取消 docx（默认 md+docx）再勾回——勾选交互
    await page.locator('[data-od-id="download-fmt-docx"]').click();
    await expect(page.locator('[data-od-id="download-fmt-docx"]')).toHaveAttribute("aria-checked", "false");
    await page.locator('[data-od-id="download-fmt-docx"]').click();
    await page.locator('[data-od-id="download-start"]').click();
    // 轮询到 done → 完成页
    await expect(page.getByText("下载完成", { exact: true })).toBeVisible({ timeout: 10000 });
    // 打开文件夹：走壳桥且收到保存目录
    await page.getByRole("button", { name: "打开文件夹" }).click();
    const opens = await page.evaluate(() => (window as unknown as { __dlOpens?: string[] }).__dlOpens);
    expect(opens).toEqual(["/tmp/dl-e2e"]);
    await ctx.close();
  });

  test("409：备份在跑时发起下载，提示区分任务类型", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await stubBridge(page, "/tmp/dl-e2e");
    stubBookApi(page, { fail409: true });
    await gotoPreview(page);
    await page.locator(".ex-dirs .chip", { hasText: "文稿" }).click();
    await page.locator('[data-od-id="download-start"]').click();
    // toast 提示备份在跑（区分任务类型），且不进入完成态
    await expect(page.locator(".toast", { hasText: "已有备份任务在进行中" })).toBeVisible();
    await expect(page.getByText("下载完成")).toHaveCount(0);
    await ctx.close();
  });

  test("下载失败：err 文案 + 返回修改/重试出口", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await stubBridge(page, "/tmp/dl-e2e");
    stubBookApi(page, { failTask: true });
    await gotoPreview(page);
    await page.locator(".ex-dirs .chip", { hasText: "文稿" }).click();
    await page.locator('[data-od-id="download-start"]').click();
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible({ timeout: 10000 });
    expect(await alert.textContent()).toContain("无法写入所选目录");
    await expect(page.getByRole("button", { name: "返回修改" })).toBeVisible();
    await expect(page.getByRole("button", { name: "重试" })).toBeVisible();
    await ctx.close();
  });

  test("切视图保活：运行中切写作再切回，完成态可读回", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await stubBridge(page, "/tmp/dl-e2e");
    stubBookApi(page, { runningPolls: 6 });
    await gotoPreview(page);
    await page.locator(".ex-dirs .chip", { hasText: "文稿" }).click();
    await page.locator('[data-od-id="download-start"]').click();
    await expect(page.getByText("后台运行")).toBeVisible({ timeout: 10000 });
    // 后台运行收起弹层 → 切去写作再切回预览（轮询在壳层不中断）
    await page.getByText("后台运行").click();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.locator(".mcard")).toHaveCount(0);
    await page.locator(".mtab", { hasText: "预览" }).click();
    await page.locator('[data-od-id="download-open"]').click();
    await expect(page.getByText("下载完成", { exact: true })).toBeVisible({ timeout: 10000 });
    await ctx.close();
  });

  test("未选任何格式：主按钮禁用", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await stubBridge(page, "/tmp/dl-e2e");
    stubBookApi(page);
    await gotoPreview(page);
    await page.locator('[data-od-id="download-fmt-md"]').click();
    await page.locator('[data-od-id="download-fmt-docx"]').click();
    await expect(page.locator('[data-od-id="download-start"]')).toBeDisabled();
    await ctx.close();
  });
});
