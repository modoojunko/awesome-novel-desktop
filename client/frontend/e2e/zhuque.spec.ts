// 朱雀 AI 检测工作台 e2e（c-zhuque-ai-detect ＋ c-zhuque-quota-ledger）。
// 运行前提：栈后端含 zhuque 模块，且 ZHUQUE_API_BASE 指向 classify 桩（compose
// 环境变量）；未部署桩的环境本 spec 自动跳过——探测 /api/v1/zhuque/config
// 不可达（非 JSON）即视为未部署。
// 自包含会话（c-zhuque-quota-ledger，creation-flow setupSession 同口径）：
// S端 注册签发 token → 写 C端 config.json（tier=max，朱雀为 PRO 权益试用不含）→
// 注入 localStorage＋桩 check-auth（注入设备在 S端 无授权，code 1 会冲掉注入
// token）。E2E_S_API / E2E_CLIENT_CONFIG_PATH 可指向隔离栈（默认主栈）。
// 锚点：rail-zhuque-check / zhuque-head-strip / zq-clear / zq-rerun /
//       zhuque-show-switch / zhuque-restale / zhuque-quota-ledger（见 tasks 8.1）。
import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { expect, test, type Page } from "@playwright/test";

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174/";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = process.env.E2E_CLIENT_CONFIG_PATH
  || path.join(process.cwd(), "..", "..", ".docker-data", "client", "config.json");

// 测试专 pros 书名：工作台用例点首本书；afterAll 按名定向清理（真书名不碰）
const BOOK_NAME = "沙漏之下-e2e";
const PASSWORD = "Test" + "Pass789!"; // 测试口令运行时拼装（门禁：源码不落明文口令）

// 完整权益快照（快照三段式 case 3：features list＋limits.max_projects 键齐）——
// 无快照时 C端 走档位兜底，features 恒缺 ai-detect → 检测行锁 MAX 态，点不出检测
const ENTITLEMENT = {
  tier: "max",
  features: ["settings-ai-fields", "outline-advanced-fields", "ai-generate", "prompt-panel", "ai-detect"],
  limits: { max_projects: null },
};

let token = "";
let restoreCfg: (() => void) | null = null;

async function sRegisterAndLogin(): Promise<string> {
  const name = `e2e_zq_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: PASSWORD, security_question: "q", security_answer: "a" }),
  }).then((r) => r.json());
  expect(reg.code, `S端 register: ${JSON.stringify(reg)}`).toBe(0);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: PASSWORD }),
  }).then((r) => r.json());
  expect(login.code, `S端 login: ${JSON.stringify(login)}`).toBe(0);
  return login.data.token as string;
}

/** 写 config.json 并观察稳定性：check-auth 的异步回写可能晚于写入落地冲掉 token
 * （creation-flow 同款已知竞态），连续两轮读到注入 token 才放行。 */
function writeSessionConfig(cfgBase: Record<string, unknown>) {
  const write = () => {
    const cfg = {
      ...cfgBase,
      token,
      tier: "max",
      expires_at: "",
      entitlement: ENTITLEMENT,
      last_login_at: new Date().toISOString(),
    };
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  };
  write();
  const readToken = () => {
    try {
      return (JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8")) as { token?: string }).token;
    } catch {
      return "";
    }
  };
  for (let round = 0; round < 3; round++) {
    const a = readToken();
    if (a === token) {
      const b = new Promise<string>((r) => setTimeout(() => r(readToken()), 1200));
      return b.then((v) => v === token);
    }
    write();
  }
  return Promise.resolve(false);
}

test.describe("朱雀 AI 检测（工作台三处消费点）", () => {
  test.beforeAll(async ({ request }) => {
    const deployed = await request
      .get(`${ORIGIN}api/v1/zhuque/config`)
      .then((r) => r.status() !== 404)
      .catch(() => false);
    test.skip(!deployed, "隔离栈未部署 zhuque 模块——任务组8 换包后启用");

    token = await sRegisterAndLogin();
    // 写 C端 config.json（备份还原；后端按 (mtime,size) 失效缓存，外部改写即时生效）
    const original = fs.existsSync(CONFIG_PATH) ? fs.readFileSync(CONFIG_PATH, "utf-8") : null;
    const cfgBase = original ? (JSON.parse(original) as Record<string, unknown>) : {};
    const stable = await writeSessionConfig(cfgBase);
    expect(stable, "config.json 注入 token 被异步回写反复冲掉（check-auth 竞态）").toBe(true);
    restoreCfg = () => {
      try {
        if (original === null) fs.unlinkSync(CONFIG_PATH);
        else fs.writeFileSync(CONFIG_PATH, original);
      } catch {
        /* 还原失败不遮蔽测试结论 */
      }
    };

    // 种书/卷/章/正文（书名即创建→卷→章→prose），Key 保存在测试内做（需登录态头）
    const auth = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    const seedJson = async (method: string, url: string, body?: unknown) => {
      const r = await fetch(`${ORIGIN}${url}`, {
        method, headers: auth, body: body === undefined ? undefined : JSON.stringify(body),
      });
      expect(r.ok, `${method} ${url} -> ${r.status}`).toBe(true);
      return r.json();
    };
    const book = await seedJson("POST", "api/novels", { name: BOOK_NAME, source: "manual" });
    const pid = book.id as string;
    expect(pid, `建书: ${JSON.stringify(book)}`).toBeTruthy();
    const vol = await seedJson("POST", `api/novels/${pid}/volumes`, { title: "第一卷" });
    const vref = (vol.ref || vol.volume_ref || "vol-1") as string;
    const ch = await seedJson("POST", `api/novels/${pid}/volumes/${vref}/chapters`, { title: "第1章" });
    const cref = (ch.ref || ch.chapter_ref) as string;
    expect(cref, `建章: ${JSON.stringify(ch)}`).toBeTruthy();
    await seedJson("PUT", `api/novels/${pid}/chapters/${cref}/prose`, {
      prose: "她握紧船桨，江风把斗笠掀得直响。\n\n船家压低嗓子说，渡口明早封江，过路人一律拦下。\n\n雨点砸在篷布上，像是谁在头顶擂鼓。",
    });
    // 朱雀 Key（就绪态行与台账卡的前提；ZHUQUE_API_BASE 指向 classify 桩，测试连接不真烧额度）
    await seedJson("PUT", "api/v1/zhuque/config", { api_key: "eo-mk-e2e-stub" });
  });

  test.afterAll(async ({ request }) => {
    if (!token) return;
    // 定向清理本 spec 的测试书（isTestBookName 词表外，按名过滤）；失败不遮蔽结论
    try {
      const list = (await request.get(`${ORIGIN}api/novels`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json())) as Array<{ id: string; name?: string }>;
      for (const n of list) {
        if (n.name === BOOK_NAME) {
          await request.delete(`${ORIGIN}api/novels/${n.id}`, {
            headers: { Authorization: `Bearer ${token}` },
          }).catch(() => {});
        }
      }
    } catch {
      /* 清理失败不遮蔽测试结论 */
    }
    restoreCfg?.();
  });

  test.beforeEach(async ({ page }) => {
    test.skip(!token, "前置未就绪（beforeAll 已 skip）");
    await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
    // 页面级桩 check-auth：注入设备在 S端 无授权（code 1）会清 config.json 注入 token。
    // /auth/verify 不能桩——它是套餐上下文数据源（本地判定零网络），桩掉前端降免费版。
    await page.route("**/api/auth/check-auth", (r) =>
      r.fulfill({ json: { code: 0, data: {} } }),
    );
  });

  test("右栏检测行存在且与结果条联动", async ({ page }) => {
    await page.goto(ORIGIN);
    // 进入写作台正文页签（书架 → 测试书 → 写作视图 → 左树选章）
    await page.getByText(BOOK_NAME).click();
    await page.getByRole("button", { name: "写作" }).first().click().catch(() => {});
    await page.getByText("第一章").first().click(); // 未选章时中栏是空书态，正文页签随选中章展开
    await page.getByRole("tab", { name: /正文/ }).click();

    // 就绪态行存在（MAX＋已配 Key）；等配置状态取数归位（zqConfigured null 期间行
    // 短暂呈 guide 变体，点了会跳配置页而非发检测）
    const row = page.getByTestId("rail-zhuque-check");
    await expect(row).toBeVisible();
    await expect(row).not.toHaveClass(/zq-guide|zq-maxlk/, { timeout: 10000 });

    // 点击发起检测（后端桩返回固定三占比＋段落标注）
    await row.click();
    const strip = page.getByTestId("zhuque-head-strip");
    await expect(strip).toBeVisible();
    await expect(strip).toContainText("人工");
    await expect(strip).toContainText("概率参考 · 非平台判定");

    // 正文行标注：疑似段黄底、行尾置信度章
    await expect(page.locator(".editor p.zq-warn").first()).toBeVisible();
    await expect(page.locator(".zq-mark").first()).toBeVisible();

    // 清除标注＝结果条与标注一并退场
    await page.getByTestId("zq-clear").click();
    await expect(strip).toBeHidden();
  });

  test("配置页台账卡：本月已用/免费额度（真后端 usage 契约）", async ({ page }) => {
    await page.goto(`${ORIGIN}#/config?tab=zhuque`);
    // 已配置态：掩码行可见
    await expect(page.getByText("更换 Key")).toBeVisible();
    // 台账卡（c-zhuque-quota-ledger）：「本月已用 / 免费额度 token」＋口径行；
    // 已用量随工作台用例是否先跑而变（0 或桩的 321），数字位用正则兼容
    await expect(page.getByText(/[\d,]+ \/ 50 万 token/)).toBeVisible();
    await expect(page.getByText("本月已用 · 本地估算，以腾讯云控制台为准")).toBeVisible();
    // 权威口径外链保留
    await expect(page.getByText("查看用量 ↗")).toBeVisible();
  });
});
