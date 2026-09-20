import { test, expect, type Page } from "@playwright/test";
import { stubUpdateNotice } from "./helpers";

/**
 * 完本链路（works-finish-flow）：待完本徽章/页脚、待完本分组头完本入口（提示条已退役，
 * c-works-toolbar）、完本清单弹窗（伏笔留白勾选）、完结、⋯菜单撤完本。
 * 全打桩 spec（runbook ③：/api/** 全部 route 拦截，不起真后端）；
 * 请求头守卫（runbook #17）：完本/撤完本必须带 Bearer（先例 manuscript-download）。
 */

const H = 3600_000;

const readyNovel = {
  id: "fin-ready",
  name: "沙漏之下",
  slug: "fin-ready",
  current_phase: "write",
  total_volumes: 2,
  total_chapters: 6,
  total_archives: 6, // 全归档未完结 → 待完本
  word_count: 21400,
  genre: "玄幻",
  synopsis: "时间在城外的沙丘上倒流，捡贝壳的少年成了唯一记得明天的人。",
  updated_at: new Date(Date.now() - 24 * H).toISOString(),
  finished_at: null,
};

const doneNovel = {
  ...readyNovel,
  id: "fin-done",
  name: "雾中法庭",
  slug: "fin-done",
  total_volumes: 3,
  total_chapters: 9,
  total_archives: 9,
  word_count: 12842,
  genre: "都市",
  synopsis: "律所新人姜序被卷入一场横跨十二年的旧案，迷雾散去时，法槌落下。",
  updated_at: new Date(Date.now() - 72 * H).toISOString(),
  finished_at: new Date(Date.now() - 72 * H).toISOString(), // → 已完结
};

const activeHook = {
  id: "hook-1",
  novel_id: "fin-ready",
  seq: 1,
  code: "#H-0001",
  description: "旧航图缺口上的摩挲痕迹",
  type: "mystery",
  priority: 2,
  status: "active",
  introduced_chapter_id: "ch-uuid-2",
  planned_chapter_id: null,
  resolved_chapter_id: null,
  mentioned_chapter_id: null,
  payoff_note: "",
  created_at: null,
  updated_at: null,
};

async function stubShell(page: Page, novels: unknown[]) {
  await page.addInitScript(() => {
    localStorage.setItem("auth_token", "finish-flow-stub");
    localStorage.setItem("auth_username", "finisher");
  });
  await page.route("**/api/novels", (r) => r.fulfill({ json: novels }));
  await page.route("**/api/auth/verify", (r) =>
    r.fulfill({ json: { tier: "monthly", is_member: true, expired: false, trial_remaining_days: 0 } }),
  );
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { has_api_key: true, portal_url: "" } }),
  );
  await stubUpdateNotice(page, "none");
  await page.route(/awesomenovel\.com\//, (r) => r.fulfill({ body: "stubbed" }));
}

/** 完本弹窗数据源：1 条 active 伏笔（第 2 章埋下）＋卷章树换算表 */
async function stubFinishData(page: Page, novelId: string) {
  await page.route(`**/api/novels/${novelId}/hooks`, (r) =>
    r.fulfill({ json: { ok: true, data: { count: 1, items: [activeHook] } } }));
  await page.route(`**/api/novels/${novelId}/volumes`, (r) =>
    r.fulfill({ json: [{ ref: "vol-1", chapters: [{ id: "ch-uuid-2", chapter: 2 }] }] }));
}

test.describe("完本链路（works-finish-flow）", () => {
  test("待完本：徽章/分态页脚；提示条退役；分组头去完本开弹窗", async ({ page }) => {
    await stubShell(page, [readyNovel]);
    await stubFinishData(page, "fin-ready");
    await page.goto("/#/novels");

    const card = page.locator(".book-card");
    await expect(card).toContainText("待完本");
    await expect(card).toContainText("全书 6 章已归档");
    await expect(card.getByRole("button", { name: "回看" })).toBeVisible();
    await expect(card.getByRole("button", { name: "完本" })).toBeVisible();

    // 待完本提示条退役（c-works-toolbar，ADJUSTMENTS 换代 v2 章 #2）：入口＝分组头/卡页脚
    await expect(page.locator('[data-od-id="ready-notice"]')).toHaveCount(0);
    await expect(page.getByText(/主线已收齐/)).toHaveCount(0);

    // 分组头：待完本 chip → 「N 本 · 主线已收齐」＋去完本（同一 FinishModal）
    await page.locator('[data-od-id="filter-ready"]').click();
    const head = page.locator(".bk-group-head");
    await expect(head).toContainText("1 本 · 主线已收齐");
    await page.locator('[data-od-id="group-finish"]').click();
    await expect(page.locator(".modal")).toContainText("完结《沙漏之下》？");
  });

  test("完本清单：三行检查＋伏笔留白（不落库）＋完结转已完结", async ({ page }) => {
    await stubShell(page, [readyNovel]);
    await stubFinishData(page, "fin-ready");
    const finishHeaders: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/finish")) finishHeaders.push(req.headers()["authorization"] ?? "");
    });
    let finishCalled = 0;
    await page.route("**/api/novels/fin-ready/finish", (r) => {
      finishCalled += 1;
      return r.fulfill({
        json: { id: "fin-ready", name: "沙漏之下", finished_at: new Date().toISOString(), updated_at: new Date().toISOString() },
      });
    });
    await page.goto("/#/novels");

    await page.locator(".book-card").getByRole("button", { name: "完本" }).click();
    const modal = page.locator(".modal");
    await expect(modal).toBeVisible();
    await expect(modal).toContainText("完结《沙漏之下》？");
    await expect(modal).toContainText("章节已全部归档");
    await expect(modal).toContainText("还有 1 条伏笔悬着");
    await expect(modal).toContainText("旧航图缺口上的摩挲痕迹");
    await expect(modal).toContainText("第 2 章埋下");
    await expect(modal).toContainText("归档收尾都已清");

    // 留白切换：未收 → 留白（纯弹窗内状态；不产生 PATCH 请求——hooks 路由外无捕获即可证）
    let hookPatched = 0;
    await page.route("**/api/novels/fin-ready/hooks/hook-1", (r) => {
      hookPatched += 1;
      return r.fulfill({ json: { ok: true, data: activeHook } });
    });
    await modal.locator(".fin-hook").click();
    await expect(modal.locator(".fin-hook .mk")).toHaveText("留白");
    expect(hookPatched).toBe(0); // 留白不落库
    await modal.locator(".fin-hook").click();
    await expect(modal.locator(".fin-hook .mk")).toHaveText("未收");

    await modal.getByRole("button", { name: "完结这本书" }).click();
    await expect(modal).toHaveCount(0);
    expect(finishCalled).toBe(1);
    expect(finishHeaders.every((h) => h.startsWith("Bearer "))).toBe(true); // 请求头守卫

    // 卡片转已完结：徽章/页脚（不再有提示条可消失——已退役）
    const card = page.locator(".book-card");
    await expect(card).toContainText("已完结");
    await expect(card).toContainText(/完结于/);
  });

  test("完本守卫 409：toast 透出服务端原因且弹窗不关", async ({ page }) => {
    await stubShell(page, [readyNovel]);
    await stubFinishData(page, "fin-ready");
    await page.route("**/api/novels/fin-ready/finish", (r) =>
      r.fulfill({ status: 409, json: { detail: "还有主线章节未归档，完本前先把主线章节全部归档" } }));
    await page.goto("/#/novels");

    await page.locator(".book-card").getByRole("button", { name: "完本" }).click();
    const modal = page.locator(".modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "完结这本书" }).click();
    // 服务端 detail 透出（errMessage 口径，rider F3.1）——不再是硬编码单一文案
    await expect(page.locator(".toast")).toContainText("还有主线章节未归档，完本前先把主线章节全部归档");
    await expect(modal).toBeVisible(); // 不关闭，可先回去归档
  });

  test("已完结：⋯菜单撤完本 → 回待完本（徽章/页脚复原）", async ({ page }) => {
    await stubShell(page, [doneNovel]);
    const reopenHeaders: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/reopen")) reopenHeaders.push(req.headers()["authorization"] ?? "");
    });
    await page.route("**/api/novels/fin-done/reopen", (r) =>
      r.fulfill({
        json: { id: "fin-done", name: "雾中法庭", finished_at: null, updated_at: new Date().toISOString() },
      }));
    await page.goto("/#/novels");

    const card = page.locator(".book-card");
    await expect(card).toContainText("已完结");
    await expect(card).toContainText(/完结于/);

    await card.getByLabel("更多操作").click();
    await card.getByRole("button", { name: "完本信息 · 撤完本" }).click();
    const modal = page.locator(".modal");
    await expect(modal).toContainText("《雾中法庭》已完结");
    await modal.getByRole("button", { name: "撤完本 · 继续写" }).click();
    await expect(modal).toHaveCount(0);
    expect(reopenHeaders.every((h) => h.startsWith("Bearer "))).toBe(true);

    // 回到待完本（全归档未完结）：徽章/页脚复原
    await expect(card).toContainText("待完本");
    await expect(card).toContainText("全书 9 章已归档");
  });
});
