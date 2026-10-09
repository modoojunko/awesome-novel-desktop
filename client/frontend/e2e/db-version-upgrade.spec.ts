import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, rmSync, statSync, utimesSync } from "node:fs";
import { join } from "node:path";
import { test, expect, type Page } from "@playwright/test";

/**
 * UP-11/UP-17 版本升级 e2e（c-db-per-version → c-lossless-upgrade）：
 * 首启告知卡四步（告知→同意→锁定进度→完成确认）＋队列让位。
 *
 * 与其余 e2e 的差别：本文件**不打桩候选/搬运端点**——候选扫描/密文转接/计数都走真
 * 后端。数据目录由 `UP11_DATA_DIR` 指定（会话私有 docker 栈的宿主侧挂载点），spec 在
 * 宿主侧往该目录播种旧版库；未设置该变量则整组 skip（避免误连别人的共享栈）。
 *
 * 断言判据：①无候选＝首装态：无卡无常驻行，「从备份包恢复」出口恒在；②播种
 * `novel-v1.db` 后**告知卡自动出现**（两块清单，角落小字让位）；③同意→进度锁定
 * （无取消/收起按钮）→结果确认→书架落书；④宿主侧直读当前版本库核对；⑤队列让位：
 * 未点完成确认前写作能力弹窗不入场，确认后入场（UP-18，探测/下载不延迟的呈现面）。
 */
const DATA_DIR = process.env.UP11_DATA_DIR || "";
// 种子 id 每轮唯一：迁移是 INSERT OR IGNORE——固定 id 在「同库已被上一次全量跑
// 写过」时会插入 0 行，结果页如实报「已带回 0 本书」而断言写死 2 就会假红（实测踩过）
const SEED_PY = `
import sqlite3, sys
p, tag = sys.argv[1], sys.argv[2]
con = sqlite3.connect(p)
con.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT,"
            " slug TEXT, root_path TEXT, current_phase TEXT, status TEXT,"
            " total_volumes INTEGER, total_chapters INTEGER, created_at TIMESTAMP,"
            " updated_at TIMESTAMP)")
for i in range(2):
    con.execute("INSERT INTO novels (id, user_id, name, slug, root_path, current_phase,"
                " status, total_volumes, total_chapters, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"up11-{tag}-{i}", "up11", f"上一版的书{i}", f"up11-{tag}-{i}",
                 f"./data/up11-{tag}-{i}",
                 "write", "active", 1, 1, "2026-01-01 00:00:00", "2026-01-02 00:00:00"))
con.commit()
con.close()
`;

/** 只清「旧版数据」：**绝不动应用自己的当前库**（删了它后端连接会指向已删除 inode，
 *  后续迁移会以 `no such table` 失败——实测踩过）。当前库由 CLIENT_VERSION 派生。 */
// 当前库文件名＝CLIENT_VERSION 派生（db-generation）：dev 构建＝固定哨兵 novel-dev.db，
// 发布版＝novel-v{版本}.db。**不得写死**——曾写死 novel-v0.25，dev 栈上
// clearLibraries 把活跃库 novel-dev.db 当旧库删掉：迁移对空库 INSERT 报
// `no such table: main.novels`，且删文件时后端仍持已删 inode，全 suite 级联超时。
const CLIENT_VERSION_FOR_LIB = process.env.CLIENT_VERSION || "dev";
const ACTIVE_BASE =
  CLIENT_VERSION_FOR_LIB === "dev" ? "novel-dev" : `novel-v${CLIENT_VERSION_FOR_LIB}`;
const ACTIVE_FILES = [
  `${ACTIVE_BASE}.db`,
  `${ACTIVE_BASE}.db-wal`,
  `${ACTIVE_BASE}.db-shm`,
];

function clearLibraries(): void {
  for (const f of readdirSync(DATA_DIR)) {
    if (!f.startsWith("novel") || ACTIVE_FILES.includes(f)) continue;
    rmSync(join(DATA_DIR, f), { recursive: true, force: true });
  }
}

function seedLegacyLibrary(): string {
  const p = join(DATA_DIR, "novel-v1.db");
  execFileSync(process.env.PYTHON || "python3",
               ["-c", SEED_PY, p, String(Date.now()).slice(-9)]);
  // mtime 拉开：确保候选扫描把这份遗留库当“刚写过的旧版数据”
  const t = new Date();
  utimesSync(p, t, t);
  return p;
}

async function stubSession(page: Page, username = "up11"): Promise<void> {
  await page.addInitScript((u) => {
    localStorage.setItem("auth_token", "up11-stub");
    localStorage.setItem("auth_username", u);
  }, username);
  await page.route("**/api/auth/verify", (r) =>
    r.fulfill({ json: { tier: "member", is_member: true, expired: false, trial_remaining_days: 0 } }),
  );
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { has_api_key: true, portal_url: "" } }),
  );
  // 书架恒空：被测的是空态出口行与搬运链（候选端点走真后端）
  await page.route("**/api/novels", (r) => r.fulfill({ json: [] }));
}

test.describe("UP-11 版本升级：空态双出口与带回全链", () => {
  test.skip(!DATA_DIR, "未设 UP11_DATA_DIR（会话私有栈的数据目录）——整组跳过");

  test.beforeAll(() => {
    if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });
  });

  test("换安装目录：无候选时「从备份包恢复」恒在且可达", async ({ page }) => {
    clearLibraries();
    await stubSession(page);
    await page.goto("/#/novels");

    await expect(page.getByText("开始你的第一本书")).toBeVisible();
    const restore = page.getByText("从备份包恢复");
    await expect(restore).toBeVisible();                      // 第二出口恒在
    // 首装态（c-lossless-upgrade）：告知卡与常驻行完全不出现
    await expect(page.getByTestId("carry-card")).toHaveCount(0);
    await expect(page.getByTestId("carry-strip-later")).toHaveCount(0);
    await expect(page.getByTestId("carry-strip-done")).toHaveCount(0);

    await restore.click();
    await expect(page.getByText("恢复备份")).toBeVisible();      // RestoreModal 单实例打开
  });

  test("同机升级：告知卡四步（自动出现→同意→锁定进度→确认）→ 真后端计数落库", async ({ page }) => {
    clearLibraries();
    const seeded = seedLegacyLibrary();
    const before = statSync(seeded);

    await stubSession(page);
    await page.goto("/#/novels");

    // ① 告知卡自动出现（recommended 候选 → 壳层队列直接放行）：清单含书名＋主按钮覆盖两样
    const card = page.getByTestId("carry-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText("上一版的书0");
    await expect(card).toContainText("立即迁移");
    // 角落小字让位：卡在途不再渲染空态出口行的带回小字
    await expect(page.locator(".fr-note").filter({ hasText: "旧版作品" })).toHaveCount(0);

    // ② 同意（唯一操作）→ 进度锁定：无取消/收起按钮
    await page.getByTestId("carry-start").click();
    await expect(page.getByTestId("carry-progress")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("carry-progress").locator("button")).toHaveCount(0);

    // ③ 完成确认：结果卡 → 点「好，开始写作」收尾
    await expect(page.getByTestId("carry-result")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("carry-result")).toContainText("已迁移 2 本书");
    await page.getByTestId("carry-confirm").click();
    // 完成常驻行
    await expect(page.getByTestId("carry-strip-done")).toBeVisible();

    // ④ 落库核对：直接读**宿主侧的当前版本库文件**（最强证据——不经前端状态，
    //    证明书真的写进了本版本的库；`page.request` 无页面鉴权会话，故不走它）
    const probe = execFileSync(process.env.PYTHON || "python3", ["-c", `
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print(con.execute("SELECT COUNT(*) FROM novels").fetchone()[0],
      "|", ",".join(r[0] for r in con.execute("SELECT name FROM novels ORDER BY id")))
con.close()
`, join(DATA_DIR, `${ACTIVE_BASE}.db`)], { encoding: "utf8" }).trim();
    // 全量跑时同一库被别的 spec 写过——只钉「这两本在」＋计数 ≥ 2，不写死等于 2
    const bookCount = Number(probe.split("|")[0].trim());
    expect(bookCount).toBeGreaterThanOrEqual(2);
    expect(probe).toContain("上一版的书0");
    expect(probe).toContain("上一版的书1");

    // ⑤ 源库零改动（字节级由后端测试钉死；这里钉 mtime/大小不变）
    const after = statSync(seeded);
    expect(after.size).toBe(before.size);
    expect(after.mtimeMs).toBe(before.mtimeMs);
  });
});

test.describe("UP-18 壳层队列让位（c-lossless-upgrade）", () => {
  test.skip(!DATA_DIR, "未设 UP11_DATA_DIR（会话私有栈的数据目录）——整组跳过");

  test.beforeAll(() => {
    if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });
  });

  test("带回未确认：能力包弹窗不入场；完成确认后入场（呈现延迟、探测不延迟）", async ({ page }) => {
    clearLibraries();
    seedLegacyLibrary();

    await stubSession(page);
    // 探测桩：未装包（source=pack）→ 首装弹窗意愿成立（下载本身由后台同步，不在此断言）
    await page.route("**/api/prompt-pack/probe", (r) =>
      r.fulfill({ json: { installed_version: "", latest_version: "9.9",
                          update_available: false, source: "pack" } }));
    // 同步器桩：POST /check 只回状态形状（防真同步打 CDN 拖时/失败噪声）
    await page.route("**/api/prompt-pack/check", (r) =>
      r.fulfill({ json: { started: false, state: "idle", stage: "idle",
                          installed_version: "", latest_version: "9.9", tier: "free" } }));

    await page.goto("/#/novels");
    const card = page.getByTestId("carry-card");
    await expect(card).toBeVisible({ timeout: 15_000 });

    // 队列让位：带回卡在途（未确认）→ 写作能力弹窗 SHALL NOT 入场
    await page.waitForTimeout(1500);
    await expect(page.getByText("正在准备写作能力")).toHaveCount(0);
    await expect(page.getByText("写作能力有更新")).toHaveCount(0);
    await expect(page.getByText("写作能力已就绪")).toHaveCount(0);

    // 走完四步 → 完成确认放行队列 → 能力包弹窗此刻才入场
    await page.getByTestId("carry-start").click();
    await expect(page.getByTestId("carry-result")).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("carry-confirm").click();
    const packTitles = page.getByText(/正在准备写作能力|写作能力有更新|写作能力/, { exact: false });
    await expect(packTitles.first()).toBeVisible({ timeout: 10_000 });
  });
});
