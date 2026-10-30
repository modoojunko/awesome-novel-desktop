// 建书异步阶段 E2E（c-deconstruct-import-async）：UI 桩模式——所有 /api/* 由 page.route
// 打桩，不依赖真实后端/拆书任务（仿 character-library.spec.ts 先例）。
// 覆盖：确认建书 → 202 关弹窗＋toast → 详情建书中 → 轮询翻已建书 → 打开这本书；
// 以及取消建书回退、清单未知状态不崩。后端语义由 pytest 覆盖。
import { test, expect, type Page } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL || "http://localhost:5199";

type Phase = "completed" | "importing" | "imported" | "import_failed";

function detail(phase: Phase) {
  return {
    id: "t1",
    status: phase,
    book_name: "星海远征",
    encoding: "utf-8",
    source_name: "星海远征.txt",
    total_chars: 542000,
    chapter_count: 318,
    volume_count: 10,
    parse_warnings: [],
    ai_model: "qwen3-max",
    api_config_id: "cfg-1",
    selected_dims: ["intro", "world"],
    dims: {
      intro: { state: "completed", seg_done: 1, seg_total: 1, error: "" },
      world: { state: "completed", seg_done: 1, seg_total: 1, error: "" },
    },
    products: [{ filename: "简介.md", size: 1200, dim: "简介" }],
    error: "",
    error_kind: "",
    warnings: [],
    model_history: [],
    book_id: phase === "imported" ? "book-9" : null,
    import:
      phase === "completed"
        ? null
        : {
            run_id: "r1",
            items: ["intro", "world"],
            step: phase === "importing" ? "refine" : "done",
            started_at: new Date().toISOString(),
            finished_at: null,
            warnings: [],
            error: { message: "", kind: "", retryable: true },
            attempts: [],
          },
    created_at: null,
    finished_at: null,
    stats: null,
    monitor: null,
  };
}

/** 认证态：UI 桩模式下直接塞 token（同 character-library 先例） */
async function seedAuth(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("auth_token", "e2e-stub-token");
    localStorage.setItem("auth_username", "e2e");
  });
}

async function stubApi(page: Page, opts: { phase?: Phase; listStatus?: string } = {}) {
  const state = { phase: opts.phase ?? ("completed" as Phase), importPosts: 0, cancels: 0, detailHits: 0 };

  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (url.includes("/api/auth/check-auth") || url.includes("/api/auth/verify")) {
      return route.fulfill({
        json: {
          tier: "max",
          is_member: true,
          expired: false,
          entitlement: { features: ["deconstruct", "deconstruct-import"], limits: {} },
          prompt_pack: { phase: "ready", version: "e2e" },
        },
      });
    }
    if (url.includes("/api/auth/")) {
      return route.fulfill({ json: { has_api_key: true, portal_url: "", has_token: true, tier: "max" } });
    }
    if (url.includes("/prompt-pack/status")) return route.fulfill({ json: { phase: "ready", version: "e2e" } });
    if (url.includes("/prompt-pack/probe")) {
      return route.fulfill({ json: { installed_version: "e2e", latest_version: "e2e", update_available: false, source: "dev" } });
    }

    // 建书受理：202 + 转 importing
    if (url.includes("/import-book/cancel")) {
      state.cancels += 1;
      state.phase = "completed";
      return route.fulfill({ json: { status: "completed" } });
    }
    if (url.includes("/import-book") && method === "POST") {
      state.importPosts += 1;
      state.phase = "importing";
      return route.fulfill({
        status: 202,
        json: { status: "importing", book_id: null, name: "星海远征", skipped: [], warnings: [] },
      });
    }
    // 详情：建书中两次后翻已建书（模拟后台跑完）
    if (/\/api\/deconstruct\/tasks\/t1$/.test(url) && method === "GET") {
      // 建书中再读两次就翻「已建书」，模拟后台跑完（详情 1.5s 轮询）
      if (state.phase === "importing") {
        state.detailHits += 1;
        if (state.detailHits >= 2) state.phase = "imported";
      }
      return route.fulfill({ json: detail(state.phase) });
    }
    if (url.includes("/api/deconstruct/tasks")) {
      return route.fulfill({
        json: {
          tasks: [
            {
              id: "t1",
              status: opts.listStatus ?? state.phase,
              book_name: "星海远征",
              total_chars: 542000,
              chapter_count: 318,
              volume_count: 10,
              ai_model: "qwen3-max",
              created_at: "2026-10-30T10:00:00",
              finished_at: null,
              queued_ahead: 0,
              product_count: 1,
              error: "",
            },
          ],
          badge: 0,
          heartbeat: { running: 0, queued: 0 },
        },
      });
    }
    if (url.includes("/api/novels")) {
      return route.fulfill({ json: [{ id: "book-9", name: "星海远征", current_phase: "settings", status: "active" }] });
    }
    if (url.includes("/api/genres") || url.includes("/api/v1/")) return route.fulfill({ json: [] });
    return route.fulfill({ json: {} });
  });

  return state;
}

test("确认建书：202 关弹窗＋toast，详情建书中，翻已建书后出现打开这本书", async ({ page }) => {
  const state = await stubApi(page);
  await seedAuth(page);
  await page.goto(`${BASE}/#/tools/deconstruct/t1`);
  await expect(page.getByText("选择去向")).toBeVisible();

  await page.getByText("选择去向").click();
  await page.getByText("就建这本书").click();

  // 202：弹窗关闭 + toast 交代去向
  await expect(page.getByText(/已开始建书/)).toBeVisible();
  await expect(page.getByText("稍后再说")).toHaveCount(0);
  expect(state.importPosts).toBe(1);

  // 详情进入建书中（步骤面板）
  await expect(page.getByText(/整段在后台执行/)).toBeVisible();

  // 后台跑完 → 已建书（轮询翻面）
  await page.getByText("已建书").first().waitFor({ timeout: 15000 });
  await expect(page.getByRole("button", { name: "打开这本书" })).toBeVisible();

  // 打开这本书 → 进书内（路由变化即可，书内页面本身不在本用例范围）
  await page.getByRole("button", { name: "打开这本书" }).click();
  await expect.poll(() => page.url()).toContain("/novel/book-9");
});

test("取消建书：两步确认后回到已完成，产物与出口仍在", async ({ page }) => {
  const state = await stubApi(page, { phase: "importing" });
  await seedAuth(page);
  await page.goto(`${BASE}/#/tools/deconstruct/t1`);

  await expect(page.getByText(/整段在后台执行/)).toBeVisible();
  await page.getByText("取消建书").click();
  await page.getByText("确认取消建书").click();

  await expect.poll(() => state.cancels).toBe(1);
  await expect(page.getByText("选择去向")).toBeVisible({ timeout: 15000 });
});

test("清单未知状态不白屏（旧版本/脏数据兜底）", async ({ page }) => {
  await stubApi(page, { phase: "completed", listStatus: "weird_state" });
  await seedAuth(page);
  await page.goto(`${BASE}/#/tools`);
  await expect(page.getByText("星海远征")).toBeVisible();
  await expect(page.getByText("weird_state")).toBeVisible();
});
