// 角色库 E2E（c-character-library）：UI 桩模式——所有 /api/* 由 page.route 打桩，
// 不依赖真实后端/拆书任务；覆盖：工具菜单入口 → 库页筛选/搜索/双视图 → 编辑保存 → 用到新书。
// 书内落卡（含认知 30 格/头像拷贝）由后端 pytest 覆盖（test_character_library.py），
// 前端契约以 apply-to-book 请求参数断言。
import { test, expect, type Page } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL || "http://localhost:5298";

interface StubCard {
  id: string;
  name: string;
  aliases: string[];
  role: string;
  genre: string;
  kind: string;
  persona: string;
  dossier: Record<string, string>;
  cog: Record<string, string>;
  src: { kind: string; novel_name: string; ref: string; character_id: string };
  avatar: { has: boolean; url: string; thumb_url: string };
  rev: number;
  updated_at: string;
}

function card(over: Partial<StubCard> = {}): StubCard {
  return {
    id: "c1",
    name: "秦重霄",
    aliases: ["大当家"],
    role: "反派",
    genre: "武侠",
    kind: "敌人",
    persona: "黑风寨大当家，记仇",
    dossier: { gender: "男", age: "42", speech: "骂人先问候对方娘亲" },
    cog: { b1: "暴躁" },
    src: { kind: "book", novel_name: "剑照山河", ref: "n1", character_id: "ch1" },
    avatar: { has: false, url: "", thumb_url: "" },
    rev: 1,
    updated_at: "",
    ...over,
  };
}

async function stubApi(page: Page, opts: { items?: StubCard[] } = {}) {
  const state = { items: opts.items ?? [card(), card({ id: "c2", name: "苏晚晴", role: "配角", kind: "挚友", dossier: { gender: "女", age: "17" }, cog: {}, src: { kind: "manual", novel_name: "", ref: "", character_id: "" } })] };
  const applied: { url: string; body: unknown }[] = [];
  const toLibraryBodies: unknown[] = [];
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes("/library-candidates")) {
      return route.fulfill({
        json: {
          can_import: true,
          reason: "",
          items: [
            { key: "沈青崖", name: "沈青崖", role: "主角", persona: "看山人独子", gender: "男", age: "16", collected: false },
            { key: "秦重霄", name: "秦重霄", role: "反派", persona: "暴躁记仇", gender: "男", age: "42", collected: true },
          ],
        },
      });
    }
    if (url.includes("/to-library")) {
      toLibraryBodies.push(route.request().postDataJSON());
      return route.fulfill({ json: { created: 1, skipped: 1, library_ids: ["x"] } });
    }
    if (url.includes("/api/deconstruct/tasks/") && method === "GET") {
      // 任务详情（裸形状）：完成态，最小产物清单
      return route.fulfill({
        json: {
          id: "t1",
          status: "completed",
          book_name: "剑照山河",
          encoding: "utf-8",
          source_name: "剑照山河.txt",
          total_chars: 11280,
          chapter_count: 5,
          volume_count: 2,
          parse_warnings: [],
          ai_model: "glm-4.7",
          api_config_id: "",
          selected_dims: ["characters"],
          dims: { characters: { state: "completed", seg_done: 5, seg_total: 5, error: "" } },
          products: [{ filename: "角色设定.md", size: 100, dim: "角色设定" }],
          error: "",
          book_id: null,
          created_at: null,
          finished_at: null,
        },
      });
    }
    if (url.includes("/api/deconstruct/tasks")) {
      // 拆书任务列表是裸形状（非 {ok,data} 信封）
      return route.fulfill({ json: { tasks: [], badge: 0, heartbeat: { running: 0, queued: 0 } } });
    }
    // 这些端点回裸形状（非 {ok,data} 信封）：auth / prompt-pack / 拆书任务列表
    if (url.includes("/prompt-pack/probe")) {
      // 探测＝已装且无更新（source=dev）：书架挂载静默，不弹首装引导
      return route.fulfill({ json: { installed_version: "e2e", latest_version: "e2e", update_available: false, source: "dev" } });
    }
    if (url.includes("/prompt-pack/status")) {
      return route.fulfill({ json: { phase: "ready", version: "e2e" } });
    }
    if (url.includes("/api/auth/check-auth") || url.includes("/api/auth/verify")) {
      // 能力包 ready：否则首登引导弹窗（正在准备写作能力）会盖住整页
      return route.fulfill({
        json: {
          tier: "max",
          is_member: true,
          expired: false,
          entitlement: { features: [], limits: {} },
          prompt_pack: { phase: "ready", version: "e2e" },
        },
      });
    }
    if (url.includes("/api/auth/")) {
      return route.fulfill({ json: { has_api_key: true, portal_url: "", has_token: true, tier: "max" } });
    }
    if (url.includes("/api/novels") && method === "GET") {
      return route.fulfill({ json: [{ id: "n1", name: "剑照山河", current_phase: "settings", status: "active" }] });
    }
    if (url.endsWith("/api/character-library") && method === "GET") {
      return route.fulfill({ json: { ok: true, data: { count: state.items.length, items: state.items } } });
    }
    if (url.endsWith("/api/character-library") && method === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const created = card({ id: "new1", name: String(body.name), rev: 1 });
      state.items = [...state.items, created];
      return route.fulfill({ json: { ok: true, data: created } });
    }
    if (url.includes("/apply-to-book")) {
      applied.push({ url, body: route.request().postDataJSON() });
      return route.fulfill({
        json: { ok: true, data: { character_id: "x1", name: "秦重霄", role: "配角", renamed: false, demoted: false, avatar: false } },
      });
    }
    if (url.includes("/random-name")) {
      return route.fulfill({ json: { ok: true, data: { name: "霍青山", age: 30, source: "local" } } });
    }
    return route.fulfill({ json: { ok: true, data: {} } });
  });
  return { state, applied, toLibraryBodies };
}

test.describe("角色库（UI 桩）", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("auth_token", "e2e-stub-token");
      localStorage.setItem("auth_username", "e2e");
      localStorage.removeItem("charlib.view");
    });
  });

  test("工具菜单第三项进入角色库；筛选/搜索/双视图", async ({ page }) => {
    await stubApi(page);
    await page.goto(`${BASE}/#/novels`);
    await page.locator(".tools-trigger").click();
    await expect(page.locator('[data-od-id="menu-charlib"]')).toBeVisible();
    await page.locator('[data-od-id="menu-charlib"]').click();
    await expect(page).toHaveURL(/#\/tools\/characters/);
    await expect(page.getByRole("heading", { name: "角色库" })).toBeVisible();
    await expect(page.getByTestId("lib-card")).toHaveCount(2);
    // 搜索（隐藏字段回落）
    await page.getByTestId("lib-search").fill("娘亲");
    await expect(page.getByTestId("lib-card")).toHaveCount(1);
    await page.getByTestId("lib-search").fill("");
    // 列表视图
    await page.getByTestId("lib-viewseg").getByText("列表").click();
    await expect(page.getByTestId("lib-row")).toHaveCount(2);
    await page.getByTestId("lib-viewseg").getByText("卡片").click();
    await expect(page.getByTestId("lib-card")).toHaveCount(2);
  });

  test("新建角色：AI 随机填名龄 → 保存 → 列表出现", async ({ page }) => {
    await stubApi(page);
    await page.goto(`${BASE}/#/tools/characters`);
    await page.getByTestId("lib-new").click();
    await page.getByTestId("lib-ai-random").click();
    await expect(page.getByPlaceholder("角色叫什么")).toHaveValue("霍青山");
    await page.getByTestId("lib-genre").fill("武侠");
    await page.getByTestId("lib-save").click();
    await expect(page.getByTestId("lib-card")).toHaveCount(3);
    await expect(page.getByTestId("lib-card").filter({ hasText: "霍青山" })).toHaveCount(1);
  });

  test("用到新书：选书弹出 → 提交参数带目标书", async ({ page }) => {
    const { applied } = await stubApi(page);
    await page.goto(`${BASE}/#/tools/characters`);
    const first = page.getByTestId("lib-card").filter({ hasText: "秦重霄" });
    await first.hover();
    await first.getByText("用到新书").click();
    await expect(page.getByText("放进哪本书")).toBeVisible();
    await page.getByTestId("lib-use-submit").click();
    await expect.poll(() => applied.length).toBe(1);
    expect(applied[0].body).toMatchObject({ novel_id: "n1", rename: true });
  });

  test("拆书完成 → 收进角色库：第三卡→清单（已收录灰态）→提交参数", async ({ page }) => {
    const { toLibraryBodies } = await stubApi(page);
    await page.goto(`${BASE}/#/tools/deconstruct/t1`);
    await expect(page.getByText("选择去向")).toBeVisible();
    await page.getByText("选择去向").click();
    await expect(page.getByTestId("exit-opt-library")).toBeVisible();
    await page.getByTestId("exit-opt-library").click();
    await expect(page.getByTestId("library-row")).toHaveCount(2);
    // 已收录行不可勾且标注
    await expect(page.getByText("已在库里")).toBeVisible();
    await expect(page.getByTestId("library-submit")).toContainText("（1）");
    await page.getByTestId("library-rename").uncheck();
    await page.getByTestId("library-submit").click();
    await expect.poll(() => toLibraryBodies.length).toBe(1);
    expect(toLibraryBodies[0]).toMatchObject({ picks: ["沈青崖"], rename: false });
  });
});
