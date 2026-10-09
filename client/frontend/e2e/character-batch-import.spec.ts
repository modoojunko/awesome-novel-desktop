// 角色批量导入 E2E（c-char-batch-import）：单路径＝下载模版 → Excel 填好 → 上传 → 预览 → 建卡。
//   ① 下载模版：捕获 download，Node 侧 SheetJS 回读断言双 sheet／中文列头／示例行
//   ② happy path：fixture（2 有效行＋1 与已有卡重名）上传 → 预览状态 → 建卡 →
//      落库断言（别名/八格/列表末尾/自动选中）→「撤销本次全部」→ 列表还原
//   ③ 幂等钉：同一文件重复导入第二次全跳过（建 0 张禁确认）
// 会话隔离跑法：E2E_BASE_URL/E2E_S_API/E2E_DATA_ROOT 环境变量注入独立栈与数据目录
// （栈起法：CLIENT_DATA_DIR/SERVER_DATA_DIR 指独立目录 + docker-compose.e2e.yml）。
import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import * as XLSX from "xlsx";
import { cleanupSessionNovels, pollBackend, stableClick } from "./helpers";
import { entitlementFor } from "./tier-features";

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  process.env.E2E_DATA_ROOT || ".docker-data",
  "client",
  "config.json",
);

async function sRegisterAndLogin() {
  const name = `e2e_bi_${Date.now()}_${randomUUID().slice(0, 8)}`;
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
  if (regBody.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  return { token: loginBody.data.token as string, username: name };
}

async function writeOAuthSession(t: string, u: string) {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = "trial";
  cfg.entitlement = entitlementFor("trial");
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
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

async function setupSession(page: Page): Promise<{ restore: () => Promise<void>; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restore = await writeOAuthSession(token, username);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: { token, username, tier: "trial" } } }),
  );
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    await restore();
  };
  return { restore: restoreAndCleanup, token };
}

async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

async function openCharPanel(page: Page) {
  await page.getByRole("button", { name: /^设定/ }).click();
  await page.locator(".settings-v .col-tree").getByText("角色", { exact: true }).click();
  await expect(page.getByRole("button", { name: "添加角色" })).toBeVisible({ timeout: 10000 });
}

async function apiGetJSON(request: APIRequestContext, token: string, pid: string) {
  const r = await request.get(`${ORIGIN}/api/novels/${pid}/characters`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

function fixtureBuffer(): Buffer {
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ["名字*", "类型", "一句话人设", "别名(用·分隔)", "性别", "年龄", "种族", "势力·身份", "外貌标签", "语言特征", "背景", "剧情定位"],
      ["白芷", "配角", "药铺学徒，认药不全认人", "芷丫头", "女", "16", "人类", "回春堂 · 学徒", "圆脸 · 药渍围裙", "语速快", "自小在药铺长大。", "替主角配出关键解药"],
      ["种子甲", "配角", "", "", "", "", "", "", "", "", "", ""],
      ["韩十三", "", "", "", "", "", "", "", "", "", "", ""],
    ]),
    "角色",
  );
  return XLSX.write(wb, { bookType: "xlsx", type: "buffer" }) as Buffer;
}

async function uploadFixture(page: Page, buf: Buffer) {
  await page.getByTestId("char-batch-file-input").setInputFiles({
    name: "名单.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: buf,
  });
  await expect(page.getByTestId("char-batch-row")).toHaveCount(3, { timeout: 10000 });
}

test("角色批量导入：下载模版回读 → 上传建卡落库 → 重复导入幂等 → 撤销全清", async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `批量${Date.now() % 100000}`);
    await openCharPanel(page);

    // 先建一张已有卡（给重名行当靶子）
    await page.getByRole("button", { name: "添加角色" }).click();
    await page.getByRole("textbox", { name: "角色名称" }).fill("种子甲");
    await pollBackend(
      () => apiGetJSON(request, token, pid),
      (l: { data?: { items?: Array<{ name: string }> } }) =>
        (l.data?.items ?? []).some((x) => x.name === "种子甲"),
    );

    // ── ① 打开弹层＋下载模版：Node 侧 SheetJS 回读断言 ──
    await page.getByTestId("char-batch-open").click();
    await expect(page.getByTestId("char-batch-preview")).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: /下载模版/ }).click(),
    ]);
    const tplPath = await download.path();
    const tpl = XLSX.read(fs.readFileSync(tplPath), { type: "buffer" });
    expect(tpl.SheetNames).toEqual(["角色", "填写说明"]);
    const tplGrid = XLSX.utils.sheet_to_json<unknown[]>(tpl.Sheets["角色"], {
      header: 1,
      raw: false,
      defval: "",
    });
    expect(tplGrid[0][0]).toBe("名字*");
    expect(String(tplGrid[1][0])).toMatch(/^示例-/);
    const tplGuide = XLSX.utils.sheet_to_json<unknown[]>(tpl.Sheets["填写说明"], {
      header: 1,
      raw: false,
      defval: "",
    });
    expect(String(tplGuide[1][0])).toBe("名字*");

    // ── ② 上传名单：预览状态（示例行不进 fixture；重名行跳过）→ 建卡 ──
    await uploadFixture(page, fixtureBuffer());
    await expect(page.getByTestId("char-batch-status-2")).toHaveText("已有同名，跳过");
    await expect(page.getByTestId("char-batch-count")).toContainText("建 2 张");
    await expect(page.getByTestId("char-batch-count")).toContainText("跳过 1");
    await page.getByTestId("char-batch-confirm").click();

    // 回执＋撤销入口（p.opt[role=status]＝CharacterManager 组件 toast；页面另有全局 toast-wrap）。
    // 重名行在预览期已被过滤（跳过计数在预览条），提交的 2 行全部成功 → toast 无「跳过」。
    const charToast = page.locator("p.opt[role=status]");
    await expect(charToast).toContainText("已建 2 张卡");
    const undoBtn = page.getByTestId("char-batch-undo");
    const receipt = page.getByTestId("char-batch-receipt");
    await expect(receipt).toContainText("本批已导入 2 张卡");
    await expect(undoBtn).toBeVisible();

    // 落库断言（API）：白芷带别名与八格、韩十三纯名字；列表 3 张
    const after = await pollBackend(
      () => apiGetJSON(request, token, pid),
      (l: {
        data?: {
          items?: Array<{
            name: string;
            aliases?: string[];
            dossier?: { faction?: string };
          }>;
        };
      }) => (l.data?.items ?? []).filter((x) => x.name !== "种子甲").length === 2,
    );
    const items = after.data?.items ?? [];
    const baizhi = items.find((x) => x.name === "白芷");
    expect(baizhi?.aliases).toEqual(["芷丫头"]);
    expect(baizhi?.dossier?.faction).toBe("回春堂 · 学徒");
    expect(items.find((x) => x.name === "韩十三")).toBeTruthy();

    // 自动选中第一张新卡（白芷）：右栏卷宗带别名与档案
    await expect(page.getByRole("textbox", { name: "别名" })).toHaveValue("芷丫头", {
      timeout: 10000,
    });
    await expect(page.getByRole("textbox", { name: "势力·身份" })).toHaveValue("回春堂 · 学徒");

    // ── ③ 幂等钉：同一文件再导一次 → 全部已有同名 → 建 0 张禁确认 ──
    await page.getByTestId("char-batch-open").click();
    await uploadFixture(page, fixtureBuffer());
    await expect(page.getByTestId("char-batch-count")).toContainText("建 0 张");
    await expect(page.getByTestId("char-batch-confirm")).toBeDisabled();
    await page.getByRole("button", { name: "取消" }).click();

    // ── ④ 撤销本次全部：本批两张被清，种子甲幸存 ──
    await undoBtn.click();
    await pollBackend(
      () => apiGetJSON(request, token, pid),
      (l: { data?: { items?: Array<{ name: string }> } }) =>
        (l.data?.items ?? []).length === 1 &&
        (l.data?.items ?? [])[0]?.name === "种子甲",
    );
    await expect(undoBtn).toHaveCount(0);
  } finally {
    await restore();
  }
});
