import { chromium } from "@playwright/test";
import fs from "node:fs";

const OUT = "/tmp/walkthrough";
fs.mkdirSync(OUT, { recursive: true });
const port = JSON.parse(fs.readFileSync("/Users/modoojunko/Library/Application Support/AwesomeNovel/port.json", "utf-8")).port;
const token = JSON.parse(fs.readFileSync("/Users/modoojunko/Library/Application Support/AwesomeNovel/data/config.json", "utf-8")).token;
const S = "http://127.0.0.1:19001/api/web";
const API = `http://127.0.0.1:${port}`;
const hdr = (t) => ({ "Content-Type": "application/json", Authorization: `Bearer ${t}` });

// ── 准备：注册用户＋建书＋绑桩 ──
const uname = `walk-all-${Date.now()}`;
await fetch(`${S}/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: uname, password: "walk-test-1" }) });
const lg = await (await fetch(`${S}/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: uname, password: "walk-test-1" }) })).json();
const wt = lg.data.token;

const bk = await (await fetch(`${API}/api/novels`, { method: "POST", headers: hdr(wt), body: JSON.stringify({ name: "全场景走查", source: "manual" }) })).json();
const bid = bk.id;
await fetch(`${API}/api/novels/${bid}/volumes`, { method: "POST", headers: hdr(wt), body: JSON.stringify({ title: "第一卷·暗流" }) });
// 绑桩模型
const rc = await fetch(`${API}/api/v1/api-configs`, { method: "POST", headers: hdr(wt), body: JSON.stringify({ name: `stub-${Date.now()}`, vendor_id: "openai-compat", base_url: "http://host.docker.internal:45991/v1", api_key: "sk-stub" }) });
const rcBody = await rc.json();
const configId = rcBody.id ?? rcBody.data?.id;
await fetch(`${API}/api/v1/novels/${bid}/ai-model`, { method: "PUT", headers: hdr(wt), body: JSON.stringify({ api_config_id: configId, model: "stub-model" }) });

// ── 浏览器 ──
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.addInitScript((t) => localStorage.setItem("auth_token", t), wt);
await p.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
await p.goto(`http://127.0.0.1:5199/#/novel/${bid}`);
await p.locator(".mtab", { hasText: "写作" }).click();
await p.waitForSelector('[data-testid="aui2-dock"]', { timeout: 20000 });
await p.waitForTimeout(1500);

let n = 0;
const SHOT = async (name) => {
  n += 1;
  await p.screenshot({ path: `${OUT}/w${String(n).padStart(2, "0")}-${name}.png` });
  console.log(`[✓] w${n}-${name}`);
};
const type = async (text) => {
  const box = p.getByTestId("aui2-dock").getByRole("textbox");
  await box.fill(text);
  await box.press("Enter");
};

// ══ A. 布局与开场 ══
await SHOT("A1-dock-greeting");
// 开场白——空书还没卷所以 greeting 是空书版

// ══ B. 授权芯片 ══
await p.click('[data-testid="aui2-mode-chip"]');
await p.waitForTimeout(300);
await SHOT("B1-mode-dropdown");
await p.click('[data-testid="aui2-mode-item-allow_book"]');
await p.waitForTimeout(500);
await SHOT("B2-mode-switched-book");
// 切回
await p.click('[data-testid="aui2-mode-chip"]');
await p.waitForTimeout(200);
await p.click('[data-testid="aui2-mode-item-confirm_each"]');
await p.waitForTimeout(300);

// ══ C. 自由对话 ══
await type("你是谁");
await p.waitForTimeout(5000);
await SHOT("C1-identity-reply");

// ══ D. 产卡流：铺卷 ══
await p.click('[data-testid="aui2-chip-draft_volume_expand"]');
await p.waitForTimeout(12000);
await SHOT("D1-volume-card");
// 采纳
const adoptBtn = await p.$('[data-testid="chat-adopt"]');
if (adoptBtn) {
  await adoptBtn.click();
  await p.waitForTimeout(3000);
  await SHOT("D2-adopt-result");
}

// ══ E. 世界观三件 ══
// 切到设定
await p.locator(".mtab", { hasText: "设定" }).click();
await p.waitForTimeout(1000);
await SHOT("E1-settings-tab");

// ══ F. 跨页签记忆 ══
// 回到写作，发一条记忆
await p.locator(".mtab", { hasText: "写作" }).click();
await p.waitForTimeout(800);
const box2 = p.getByTestId("aui2-dock").getByRole("textbox");
await box2.fill("记住：这本书全程第一人称，主角叫林野");
await box2.press("Enter");
await p.waitForTimeout(6000);
await SHOT("F1-remember-done");

// 切设定再切回来——记忆还在
await p.locator(".mtab", { hasText: "设定" }).click();
await p.waitForTimeout(800);
await p.locator(".mtab", { hasText: "写作" }).click();
await p.waitForTimeout(800);
await SHOT("F2-cross-tab-memory");

// ══ G. 停止 ══
await p.click('[data-testid="aui2-chip-draft_chapter_split"]');
await p.waitForTimeout(2000);
const stop = await p.$('[data-testid="chat-stop"]');
if (stop) {
  await stop.click();
  await p.waitForTimeout(2000);
  await SHOT("G1-stopped");
} else {
  await SHOT("G1-no-stop-btn");
}

// ══ H. 系统行为 ══
await box.fill("/new");
await box.press("Enter");
await p.waitForTimeout(2000);
await SHOT("H1-new-clear");

// ══ I. 容量条 ══
// 多发几条让容量条出现
for (const msg of ["测试一", "测试二", "测试三"]) {
  await box.fill(msg);
  await box.press("Enter");
  await p.waitForTimeout(2000);
}
await SHOT("I1-capacity-bar");

// ══ J. 错误卡 ══
// 用一个不存在的模型触发错误
await box.fill("触发一个错误");
await box.press("Enter");
await p.waitForTimeout(3000);
await SHOT("J1-error-card");

await b.close();
console.log("ALL DONE —", n, "screenshots");
