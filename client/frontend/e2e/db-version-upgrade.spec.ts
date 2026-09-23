import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, rmSync, statSync, utimesSync } from "node:fs";
import { join } from "node:path";
import { test, expect, type Page } from "@playwright/test";

/**
 * UP-11 版本升级 e2e（c-db-per-version）：空态双出口 + 「把上一版的作品带过来」全链。
 *
 * 与其余 e2e 的差别：本文件**不打桩候选端点**——候选扫描/搬运/计数都走真后端。
 * 数据目录由 `UP11_DATA_DIR` 指定（会话私有 docker 栈的宿主侧挂载点），spec 在宿主
 * 侧往该目录播种旧版库；未设置该变量则整组 skip（避免误连别人的共享栈）。
 *
 * 断言判据：①无候选时「从备份包恢复」恒在、带回出口不出现；②播种 `novel-v1.db`
 * （遗留代数名）后空态出现「这台电脑上有旧版作品（N 本）」；③走完向导后结果页报
 * 「已带回 N 本书」；④**经真实后端接口核对**书确实落进当前版本的库。
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
    await expect(page.getByText("把上一版的作品带过来")).toHaveCount(0);  // 无候选时不出现

    await restore.click();
    await expect(page.getByText("恢复备份")).toBeVisible();      // RestoreModal 单实例打开
  });

  test("同机升级：遗留库进候选 → 一次确认带回 → 真后端计数落库", async ({ page }) => {
    clearLibraries();
    const seeded = seedLegacyLibrary();
    const before = statSync(seeded);

    await stubSession(page);
    await page.goto("/#/novels");

    // ① 出口行报书数（候选扫描读到遗留库的 2 本）
    await expect(page.getByText("这台电脑上有旧版作品")).toBeVisible();
    // 出口行有两处 `.fr-note`（首启出口行 ＋ 免费额度注记）——按文案定位，别用裸类选择器
    await expect(page.locator(".fr-note").filter({ hasText: "旧版作品" })).toContainText("2");
    const bring = page.getByText("把上一版的作品带过来").first();
    await expect(bring).toBeVisible();

    // ② 一次确认：向导单候选 → 主按钮即搬运
    await bring.click();
    // 出口行按钮与弹窗主按钮同名（这是有意的文案一致性）——确认按钮必须限定在 dialog 内
    const confirm = page.getByRole("dialog").getByRole("button", { name: "把上一版的作品带过来" });
    await expect(confirm).toBeVisible();
    await confirm.click();

    // ③ 结果页回声（计数与预览同源）
    await expect(page.getByText(/已带回 \d+ 本书/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("已带回 2 本书")).toBeVisible();

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
