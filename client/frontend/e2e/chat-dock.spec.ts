import fs from "fs";
import { execSync } from "node:child_process";
import http from "http";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// c-writing-agent 批G——右栏对话写作助手 界面测试（14 场景）。
//
// 两类证据并存：
//   A. 全链场景（②③⑧⑩⑪⑫）：书的模型绑定指向**本 spec 的桩模型**（node http，
//      OpenAI 兼容，host.docker.internal 可达），assistant/chat 走**真实后端
//      agent 循环**（真工具执行＋真写回链 PUT /volumes）；桩按提示词内容分支
//      返回动作协议 JSON/卷纲草案 JSON/发散角色 JSON，延迟用例支持「停止」窗口。
//   B. 契约场景（①④⑤⑥⑦⑨⑬）：page.route 桩 SSE/会话（门控卡/流中断/HTTP 错误/
//      历史渲染等**界面契约**——事件形态即契约本身）。
//
// 场景清单：①空书开场白 ②铺卷全链（草案→采纳→真写回＋回执）③采纳后新卡 stale
// ④门控卡在对话流 ⑤跨页对话保留 ⑥流中断错误卡 ⑦HTTP 500 可读错误 ⑧工具轨迹
// 折叠 ⑨多卡并出 ⑩停止可再发 ⑪采纳与 run 并发 ⑫发散过目不自动建卡
// ⑬长会话历史 40 条 ⑭窄屏 FAB（批F-2 步⑤未落地——skip 挂账）
// ⑮思考/工具各自单行过程泡泡（c-agent-thinking-bubbles）
// =========================================================================

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19001/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5176";
const pageUrl = (hash: string) => `${ORIGIN}/#${hash}`;
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", "docker-data-e2e", "client"),
  "config.json",
);
const TEST_PASSWORD = ["TestPass", "789!"].join("");
// 桩模型端口可覆盖：并行会话/残留进程各用各的，避免 45991 被占即整轮挂
const STUB_PORT = Number(process.env.E2E_STUB_PORT || 45991);
const STUB_BASE = `http://host.docker.internal:${STUB_PORT}/v1`;

const EXPAND_DRAFT = {
  name: "逃出船坞",
  summary: "林晚押着坐标出逃，补给站全线收网。",
  conflict: "她要拿到名单，补给站要让她消失",
  ending: "名单上她的名字被注销",
  antagonist_type: "势力",
  antagonist_line: "补给站·撤离名单",
  plants: [],
  reveals: [],
  chapter_target: 4,
  checks: [],
};

// ── 桩模型：按提示词内容分支（真实 agent 循环的每一步都会打到这）────────────
function stubContent(prompt: string, userText = ""): string {
  const hasToolResult = prompt.includes("[tool result]");
  fs.appendFileSync(
    "/tmp/stub-trace.log",
    `--- protocol=${prompt.includes("动作协议")} expandCall=${prompt.includes("她逃出船坞")} toolResult=${hasToolResult} len=${prompt.length}\n`,
  );
  // ── A. 动作循环调用（system 含协议标记）：按作家指令分派工具/收口 ──
  if (prompt.includes("动作协议")) {
    const userLine = userText;
    const toolResults = (prompt.match(/\[tool result\]/g) ?? []).length;
    // 两步轨迹：第一个工具结果后，按指令再查设定（优先于收口——两步链）
    if (prompt.includes("看看设定") && toolResults === 1) {
      return JSON.stringify({
        thought: "再看一眼设定",
        action: "tool",
        tool: "read_settings",
        args: { area: "cast" },
        reply: "",
      });
    }
    if (hasToolResult) {
      return JSON.stringify({
        thought: "查完了，收口。",
        action: "final",
        tool: "",
        args: {},
        reply: "结合刚才查到的信息，给你答复：草案已经出来，过目采纳就行。",
      });
    }
    // 发散判定先于 铺/卷纲（工具目录文案含「铺」字，顺序颠倒会吞掉发散指令）
    if (userLine.includes("大胆") || userLine.includes("发散")) {
      return JSON.stringify({
        thought: "交给发散工具",
        action: "tool",
        tool: "diverge_character_group",
        args: { premise: userLine.slice(-160), count: 1 },
        reply: "",
      });
    }
    if (userLine.includes("慢慢来")) {
      return JSON.stringify({
        thought: "先查进度（这步故意慢——给「停止」留窗口）",
        action: "tool",
        tool: "read_progress",
        args: {},
        reply: "",
      });
    }
    if (userLine.includes("铺") || userLine.includes("卷纲")) {
      return JSON.stringify({
        thought: "铺这一卷",
        action: "tool",
        tool: "draft_volume_expand",
        args: { line: "她逃出船坞，补给站全线收网", vol_no: 1 },
        reply: "",
      });
    }
    if (userLine.includes("查") || userLine.includes("进度")) {
      return JSON.stringify({
        thought: "查进度",
        action: "tool",
        tool: "read_progress",
        args: {},
        reply: "",
      });
    }
    if (userLine.includes("大胆") || userLine.includes("发散")) {
      return JSON.stringify({
        thought: "交给发散工具",
        action: "tool",
        tool: "diverge_character_group",
        args: { premise: userLine, count: 1 },
        reply: "",
      });
    }
    return JSON.stringify({ thought: "收口", action: "final", tool: "", args: {}, reply: "收到。" });
  }
  // ── B. 发散核心调用（system 含发散契约专有字段 origin_note）──
  if (prompt.includes("origin_note")) {
    return JSON.stringify({
      characters: [
        {
          name: "柯克",
          role: "反派",
          persona: "补给站清点撤离名单的官，收账时先笑后翻脸。",
          origin_note: "派生自主线：撤离阴谋需要一枚执行用的棋子。",
          traits: ["记性好", "手上有旧茧"],
        },
      ],
    });
  }
  // ── C. 卷纲草案核心调用（user 含作者那一句）──
  if (prompt.includes("她逃出船坞")) {
    return JSON.stringify(EXPAND_DRAFT);
  }
  // ── D. 画像总结调用 ──
  if (prompt.includes("近期行为记录")) {
    return "{}";
  }
  // ── 兜底 ──
  return "收到。";
}

let stubServer: http.Server | null = null;

test.beforeAll(async () => {
  stubServer = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", async () => {
      res.setHeader("Content-Type", "application/json");
      if (req.url?.includes("/models")) {
        res.end(JSON.stringify({ object: "list", data: [{ id: "stub-model", object: "model" }] }));
        return;
      }
      if (req.url?.includes("/chat/completions")) {
        let prompt = "";
        let userText = "";
        let wantStream = false;
        try {
          const parsed = JSON.parse(body);
          const msgs = parsed.messages ?? [];
          prompt = msgs.map((m: { content: string }) => m.content).join("\n");
          const users = msgs.filter((m: { role: string }) => m.role === "user");
          // L2 注入（页面/画像）随消息同行、画像段以空格拼在页面段后——分支判定
          // 取作家实际指令行：从首个换行方括号段起整体截断（页名「卷纲」/画像词
          // 都不得误触工具分支）
          userText = String(users.at(-1)?.content ?? "").split("\n［")[0].trim();
          wantStream = Boolean(parsed.stream);
        } catch {
          /* 非 JSON 忽略 */
        }
        if (prompt.includes("慢慢来")) {
          // 「停止」窗口：延迟 3s 才回动作（测试在此窗口点停止/断言生成中态）
          await new Promise((r) => setTimeout(r, 3000));
        }
        // 流式响应（agent 循环走 chat_stream：SSE delta 格式——非流式体会被
        // 流式解析器读成空输出）
        const content = stubContent(prompt, userText);
        // 双模：循环走流式（chat_stream）／生成核心走非流式（client.chat）——按 stream 标志
        if (!wantStream) {
          res.setHeader("Content-Type", "application/json");
          res.end(
            JSON.stringify({
              id: "chatcmpl-stub",
              object: "chat.completion",
              created: 0,
              model: "stub-model",
              choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
              usage: { prompt_tokens: 40, completion_tokens: 16, total_tokens: 56 },
            }),
          );
          return;
        }
        res.setHeader("Content-Type", "text/event-stream");
        const chunk = (c: string) =>
          `data: ${JSON.stringify({
            id: "chatcmpl-stub",
            object: "chat.completion.chunk",
            created: 0,
            model: "stub-model",
            choices: [{ index: 0, delta: { content: c }, finish_reason: null }],
          })}\n\n`;
        res.write(chunk(content));
        res.write(
          `data: ${JSON.stringify({
            id: "chatcmpl-stub",
            object: "chat.completion.chunk",
            created: 0,
            model: "stub-model",
            choices: [{ index: 0, delta: {}, finish_reason: "stop" }],
            usage: { prompt_tokens: 40, completion_tokens: 16, total_tokens: 56 },
          })}\n\n`,
        );
        res.write("data: [DONE]\n\n");
        res.end();
        return;
      }
      res.statusCode = 404;
      res.end("{}");
    });
  });
  // bind 0.0.0.0: container reaches host stub via IPv4 gateway (IPv6 any unreachable)
  await new Promise<void>((r) => stubServer!.listen(STUB_PORT, "0.0.0.0", () => r()));
});

test.afterAll(async () => {
  await new Promise<void>((r) => (stubServer ? stubServer.close(() => r()) : r()));
});

async function registerAndLogin() {
  const name = `e2e_agt_${Date.now()}_${randomUUID().slice(0, 6)}`;
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: TEST_PASSWORD, security_question: "颜色", security_answer: "蓝" }),
  });
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: TEST_PASSWORD }),
  });
  const body = await login.json();
  if (body.code !== 0) throw new Error(`S端登录失败: ${JSON.stringify(body)}`);
  return { token: body.data.token as string, username: name };
}

// 原子写（tmp+rename）：virtiofs 上 writeFileSync 会被容器侧读到截断中间态
// （后端 get_local_config JSONDecodeError→500，e2e seed 挂）——rename 原子可见
/** config.json 一律从容器内写（Docker Desktop virtiofs 判例：宿主侧写入的截断/
 *  半写在容器侧延迟可见——rename 换 inode 与就地覆写都撞过）。docker 不可达
 *  （非容器栈）时回落宿主就地写＋fsync。 */
const CONTAINER_NAME = process.env.E2E_CLIENT_CONTAINER || "e2e-iso-client-backend";
function containerWriteConfig(jsonText: string) {
  try {
    // 走 stdin 管道（零 shell 引号面——JSON 里的引号经 argv 曾被打碎）
    execSync(
      `docker exec -i ${CONTAINER_NAME} python3 -c "import sys; open('/app/data/config.json','w').write(sys.stdin.read())"`,
      { input: jsonText, stdio: ["pipe", "pipe", "pipe"], timeout: 10000 },
    );
    return;
  } catch {
    /* docker 不可达——回落宿主写 */
  }
  const fd = fs.openSync(CONFIG_PATH, "r+");
  fs.ftruncateSync(fd, 0);
  fs.writeFileSync(fd, jsonText);
  fs.fsyncSync(fd);
  fs.closeSync(fd);
}

function atomicWriteJson(path: string, text: string) {
  // virtiofs 判例（demo-stack-virtiofs-wal-orphan 同族）：rename 换 inode 在
  // Docker Desktop bind mount 上偶发旧读——e2e 的 config 写入改就地覆写＋fsync，
  // 容器侧次轮读必见新 token（原子性在此场景让位于可见性）。
  const fd = fs.openSync(path, "r+");
  fs.ftruncateSync(fd, 0); // 截尾：新串比旧串短时残留字节会让容器读出 Extra data
  fs.writeFileSync(fd, text);
  fs.fsyncSync(fd);
  fs.closeSync(fd);
}

/** 等 config.json 在容器侧可读出期望 token。⚠ 只用 docker exec 读——绝不打真
 *  check-auth：它对陌生 pc_hash 会走「会话失效→清凭据」链，把刚写好的 config
 *  清空（2026-11-17 实锤：轮询 check-auth = 自毁会话，全测 401）。 */
function containerReadToken(): string {
  try {
    return execSync(
      `docker exec ${CONTAINER_NAME} python3 -c "import json;print(json.load(open('/app/data/config.json')).get('token',''))"`,
      { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"], timeout: 10000 },
    ).trim();
  } catch {
    return "";
  }
}
async function waitConfigVisible(expected: string, tries = 20) {
  for (let i = 0; i < tries; i += 1) {
    if (containerReadToken() === expected) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("config.json 未在容器侧可见（读取回读超时）");
}

async function writeOAuthSession(t: string, u: string, tier = "max") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  let originalToken = "";
  try {
    originalToken = String((JSON.parse(original) as { token?: string }).token ?? "");
  } catch {
    /* 残骸视为空会话 */
  }
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier);
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  containerWriteConfig(JSON.stringify(cfg, null, 2));
  await waitConfigVisible(t);
  return async () => {
    containerWriteConfig(original);
    // restore 后等容器看见旧值（下一测 setup 重写后会再等新值）
    await waitConfigVisible(originalToken).catch(() => {});
  };
}

async function setupSession(page: Page, tier = "max") {
  const { token, username } = await registerAndLogin();
  const restoreConfig = await writeOAuthSession(token, username, tier);
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    restoreConfig();
  };
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  return { restore, token };
}

const authHeaders = (token: string) => ({
  "Content-Type": "application/json",
  Authorization: `Bearer ${token}`,
});

/** 建书（真后端）＋绑桩模型＋落第一卷（供采纳写回），进写作视图等 dock。 */
async function seedBook(page: Page, token: string, name: string): Promise<string> {
  const r = await fetch(`${ORIGIN}/api/novels`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ name, source: "manual" }),
  });
  const body = await r.json();
  const id = (body.data?.id ?? body.id) as string;
  expect(id).toBeTruthy();
  // 绑桩模型（openai-compat → host.docker.internal 桩；容器可达）
  const rc = await fetch(`${ORIGIN}/api/v1/api-configs`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({
      name: `e2e-ai-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: STUB_BASE,
      api_key: "sk-e2e-stub",
    }),
  });
  expect(rc.ok).toBeTruthy();
  const cfg = await rc.json();
  const configId = cfg.id ?? cfg.data?.id;
  // test-connection：拉桩模型列表进配置（绑定校验「模型属配置列表」——ai-assist 同款）
  const rt = await fetch(`${ORIGIN}/api/v1/api-configs/${configId}/test`, {
    method: "POST",
    headers: authHeaders(token),
  });
  expect(rt.ok).toBeTruthy();
  const rb = await fetch(`${ORIGIN}/api/v1/novels/${id}/ai-model`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify({ api_config_id: configId, model: "stub-model" }),
  });
  expect(rb.ok, `绑定模型失败: ${await rb.text()}`).toBeTruthy();
  // 落第一卷（铺卷采纳的写回目标）
  const v = await fetch(`${ORIGIN}/api/novels/${id}/volumes`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ title: "第一卷" }),
  });
  expect(v.ok).toBeTruthy();
  await page.goto(pageUrl(`/novel/${id}`));
  await page.locator(".mtab", { hasText: "写作" }).click();
  await expect(page.getByTestId("aui2-dock")).toBeVisible();
  return id;
}

async function seedEmptyBook(page: Page, token: string): Promise<string> {
  const r = await fetch(`${ORIGIN}/api/novels`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ name: `e2e-empty-dock-${Date.now()}`, source: "manual" }),
  });
  const body = await r.json();
  const id = (body.data?.id ?? body.id) as string;
  expect(id).toBeTruthy();
  await page.goto(pageUrl(`/novel/${id}`));
  await page.locator(".mtab", { hasText: "写作" }).click();
  await expect(page.getByTestId("aui2-dock")).toBeVisible();
  return id;
}

async function sendViaDock(page: Page, text: string) {
  // ChatAnywhere 内部 Sender：dock 内唯一 textarea，Enter 提交（自研输入/发送钮已退役）
  const box = page.getByTestId("aui2-dock").getByRole("textbox");
  await box.fill(text);
  await box.press("Enter");
}

// ── 契约场景桩（脚本化 SSE／错误／历史）────────────────────────────────────

function sse(events: string[]): string {
  return events.map((e) => `data: ${e}\n\n`).join("");
}
const runStart = (id: string) => JSON.stringify({ type: "run_start", runId: id });
const narration = (text: string) => JSON.stringify({ type: "narration", text });
const thinking = (text: string) => JSON.stringify({ type: "thinking", text });
const stepStart = (id: string, stepId: string, tool: string, label = "") =>
  JSON.stringify({ type: "step_start", runId: id, stepId, tool, label });
const stepEnd = (
  id: string,
  stepId: string,
  tool: string,
  resultNote: string,
  ok = true,
  apiCalls?: { op: string; model: string; ms: number; tokens_in: number; tokens_out: number; ok: boolean }[],
) =>
  JSON.stringify({
    type: "step_end",
    runId: id,
    stepId,
    tool,
    resultNote,
    ok,
    ...(apiCalls ? { apiCalls } : {}),
  });
const artifact = (id: string, cardId: string, kind: string, payload: unknown) =>
  JSON.stringify({ type: "artifact", runId: id, cardId, kind, payload });
const runEnd = (id: string) => JSON.stringify({ type: "run_end", runId: id });

function EXPAND_DRAFT_PAYLOAD() {
  return { ok: true, vol_no: 1, draft: EXPAND_DRAFT, warnings: [] };
}

/** 脚本化 assistant/chat＋空 session（调用序按脚本轮转；写回链不拦）。 */
async function mockChat(page: Page, script: string[][]) {
  let call = 0;
  await page.route("**/api/novels/*/assistant/session*", (r) =>
    r.fulfill({ json: { sessionId: "s-e2e", pageCursor: "", grants: {}, messages: [] } }),
  );
  await page.route("**/api/novels/*/assistant/chat", async (r) => {
    const events = script[Math.min(call, script.length - 1)];
    call += 1;
    await new Promise((res) => setTimeout(res, 60));
    r.fulfill({ status: 200, contentType: "text/event-stream", body: sse(events) });
  });
}

// ── 十四场景 ────────────────────────────────────────────────────────────────

test.describe("chat-dock 界面测试（c-writing-agent 批G）", () => {
  test("①空书状态感知开场白＋能力盘", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedEmptyBook(page, token);
    await expect(page.getByText("第一卷还空着，说说你的目标，我来铺。")).toBeVisible();
    await expect(page.getByTestId("aui2-chip-draft_volume_expand")).toBeVisible();
    await restore();
  });

  test("②铺卷全链：草案→采纳→真实写回＋回执＋已采纳徽标", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const id = await seedBook(page, token, `e2e-agt-adopt-${Date.now()}`);
    // 界面测试证据：落一份真实 SSE 响应体到文件（全链事件流）
    page.on("response", async (r) => {
      if (r.url().includes("/assistant/chat")) {
        const t = await r.text().catch(() => "<body error>");
        fs.mkdirSync("test-results/chat-dock-evidence", { recursive: true });
        fs.appendFileSync("test-results/chat-dock-evidence/sse-adopt.log", t + "\n---\n");
      }
    });
    await sendViaDock(page, "帮我铺这一卷的卷纲。");
    // 真循环：工具步（draft_volume_expand）→ 产物卡
    await expect(page.getByTestId("chat-card-text").first()).toBeVisible({ timeout: 30000 });
    // review 钉（2026-11-14）：卡片之后的收口回复必须落在文本气泡可见——
    // 曾被吞进卡片 text（卡片渲染分支不显示）整轮静默
    await expect(
      page.getByText("结合刚才查到的信息，给你答复：草案已经出来，过目采纳就行。"),
    ).toBeVisible({ timeout: 15000 });
    // 采纳 · 写入 → PUT /volumes/vol-1 真实落库
    await page.getByTestId("chat-adopt").click();
    await expect(page.getByText("已写入第 1 卷的卷纲要点，可继续改。")).toBeVisible();
    const v = await fetch(`${ORIGIN}/api/novels/${id}/volumes/vol-1`, {
      headers: authHeaders(token),
    });
    const volText = JSON.stringify(await v.json());
    expect(volText).toContain("逃出船坞");
    expect(volText).toContain("补给站·撤离名单");
    await expect(page.locator(".cd-badge.ok").first()).toBeVisible();
    // 采纳回执落库（POST /assistant/messages/{cardId}/adopt）：重开书后徽标不丢
    await expect
      .poll(async () => {
        const s = await fetch(`${ORIGIN}/api/novels/${id}/assistant/session?thread=vol`, {
          headers: authHeaders(token),
        });
        const body = await s.json();
        const msgs = body.messages ?? [];
        return msgs.filter(
          (m: { cardKind?: string; status?: string }) =>
            m.cardKind && m.cardKind !== "gate" && m.status === "adopted",
        ).length;
      })
      .toBeGreaterThan(0);
    await restore();
  });

  test("③同目标新卡标 stale＋stale 可再采纳（第二版替换写回）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-stale-${Date.now()}`);
    await sendViaDock(page, "帮我铺这一卷的卷纲。");
    await page.getByTestId("chat-adopt").click();
    await expect(page.locator(".cd-badge.ok").first()).toBeVisible();
    await sendViaDock(page, "再铺一版。");
    await expect(page.getByText("旧版")).toBeVisible({ timeout: 30000 });
    await expect(page.locator(".cd-badge.ok").first()).toBeVisible();
    // review 钉（2026-11-14）：stale 卡不再是无按钮死端——再采纳＝替换写回，
    // 新旧两卡都带「已采纳 ✓」（旧采纳不被静默覆盖）
    await page.getByTestId("chat-adopt").last().click();
    await expect(page.getByText("已写入第 1 卷的卷纲要点，可继续改。").nth(1)).toBeVisible();
    await expect(page.locator(".cd-badge.ok")).toHaveCount(2);
    await restore();
  });

  test("④门控卡在对话流（免费档驱动发散被引导）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "free");
    await seedBook(page, token, `e2e-agt-free-${Date.now()}`);
    await mockChat(page, [
      [
        runStart("r1"),
        JSON.stringify({
          type: "gate",
          feature: "assistant-diverge",
          tier_required: "max",
          refusal: "发散造人是 MAX 档的能力。升级后告诉我大概剧情，我就能自己添人添事给你出草案。",
        }),
        runEnd("r1"),
      ],
    ]);
    await sendViaDock(page, "帮我大胆添个反派");
    await expect(page.getByText("发散造人是 MAX 档的能力", { exact: false })).toBeVisible();
    await restore();
  });

  test("⑤线程会话：每页签一个对话——切页分离、切回接续（boss 拍板 2026-11-15）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-keep-${Date.now()}`);
    await mockChat(page, [[runStart("r1"), narration("记住这句话。"), runEnd("r1")]]);
    await sendViaDock(page, "说句话我看看");
    await expect(page.getByText("记住这句话。")).toBeVisible();
    // 切到设定：另一个线程——看不到写作线程的消息
    await page.locator(".mtab", { hasText: "设定" }).click();
    await expect(page.getByTestId("aui2-dock")).toBeVisible();
    await expect(page.getByText("记住这句话。")).toBeHidden();
    // 切回写作：原线程接续
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByText("记住这句话。")).toBeVisible();
    await restore();
  });

  test("⑥流中断错误卡（无终态按失败收尾）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-cut-${Date.now()}`);
    await page.route("**/api/novels/*/assistant/session*", (r) =>
      r.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }),
    );
    await page.route("**/api/novels/*/assistant/chat", (r) =>
      r.fulfill({ status: 200, contentType: "text/event-stream", body: sse([runStart("rX")]) }),
    );
    await sendViaDock(page, "随时断");
    await expect(page.getByTestId("chat-error")).toBeVisible({ timeout: 8000 });
    await restore();
  });

  test("⑦HTTP 500 可读错误（带状态码）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-500-${Date.now()}`);
    await mockChat(page, []);
    await page.unroute("**/api/novels/*/assistant/chat");
    await page.route("**/api/novels/*/assistant/chat", (r) =>
      r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "内部错误" }) }),
    );
    await sendViaDock(page, "触发一个服务端错误");
    await expect(page.getByText(/内部错误/)).toBeVisible();
    await expect(page.getByText(/HTTP 500/)).toBeVisible();
    await restore();
  });

  test("⑧工具轨迹：全链两步→各自单行泡泡可展开", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-trace-${Date.now()}`);
    await sendViaDock(page, "查查进度，看看设定再说话");
    // 全链两步：read_progress＋read_settings 各一张单行工具泡泡
    await expect
      .poll(() => page.getByTestId("chat-proc-tool").count(), { timeout: 30000 })
      .toBe(2);
    const cards = page.getByTestId("chat-proc-tool");
    await expect(cards.nth(0)).toContainText("read_progress");
    await expect(cards.nth(1)).toContainText("read_settings");
    // 点开第一步看详情（打算/结果），再收起状态不回退
    await cards.nth(0).getByText("read_progress").click();
    await expect(cards.nth(0)).toContainText("打算");
    await restore();
  });

  test("⑮思考与工具各自单行泡泡（点开看全文/详情；正文不混 ● tool）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-bubbles-${Date.now()}`);
    await mockChat(page, [
      [
        runStart("b1"),
        thinking("先看看主线再动手"),
        stepStart("b1", "b1-1", "read_settings", "先读主线设定"),
        stepEnd("b1", "b1-1", "read_settings", "主线还没写", true, [
          { op: "assistant_step", model: "m", ms: 3, tokens_in: 1, tokens_out: 2, ok: true },
        ]),
        thinking("还是先补一句"),
        narration("看完了，主线还没写。"),
        runEnd("b1"),
      ],
    ]);
    await sendViaDock(page, "看看主线");

    // 两段思考 = 两张独立思考泡泡，默认单行折叠
    const thinkCards = page.getByTestId("chat-proc-thinking");
    await expect(thinkCards).toHaveCount(2);
    await expect(thinkCards.first()).toContainText("思考过程");
    await expect(page.getByText("先看看主线再动手")).toBeHidden();
    await thinkCards.first().getByText("思考过程").click();
    await expect(page.getByText("先看看主线再动手")).toBeVisible();

    // 一次工具调用 = 一张工具泡泡；点开看打算/结果/模型调用
    const toolCards = page.getByTestId("chat-proc-tool");
    await expect(toolCards).toHaveCount(1);
    await expect(toolCards.first()).toContainText("read_settings");
    await expect(page.getByText("结果")).toBeHidden();
    await toolCards.first().getByText("read_settings").click();
    await expect(toolCards.first()).toContainText("结果");
    await expect(toolCards.first()).toContainText("模型调用");

    // 正文只剩助手说的话，不再混 ● tool 行
    await expect(page.getByText("看完了，主线还没写。")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("● read_settings");
    await restore();
  });

  test("⑯思考泡泡点开贴最新一行（长思考默认看结尾，不用手滚）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-think-scroll-${Date.now()}`);
    const longThink = Array.from({ length: 30 }, (_, i) => `第 ${i + 1} 行走查用的思考内容`).join("\n");
    await mockChat(page, [
      [runStart("sc1"), thinking(longThink), narration("想完了。"), runEnd("sc1")],
    ]);
    await sendViaDock(page, "想一下");
    const card = page.getByTestId("chat-proc-thinking");
    await expect(card).toHaveCount(1);
    await expect(card).toContainText("思考过程");
    await card.getByText("思考过程").click();
    const body = page.getByTestId("chat-proc-thinking-body");
    await expect(body).toBeVisible();
    await expect(body).toContainText("第 30 行");
    const pos = await body.evaluate((el) => ({
      top: el.scrollTop,
      height: el.scrollHeight,
      client: el.clientHeight,
    }));
    // 长思考超出容器：点开即贴底，最新一行在视口内（底部留 2px 取整余量）
    expect(pos.height).toBeGreaterThan(pos.client);
    expect(pos.top + pos.client).toBeGreaterThanOrEqual(pos.height - 2);
    await restore();
  });

  test("⑨多卡并出：一次 run 产卡＋报告独立", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-two-${Date.now()}`);
    await mockChat(page, [
      [
        runStart("r1"),
        artifact("r1", "c1", "text", EXPAND_DRAFT_PAYLOAD()),
        artifact("r1", "c2", "report", {
          report: [{ name: "一致性", items: [{ status: "warn", text: "伏笔 F2 未接" }] }],
        }),
        runEnd("r1"),
      ],
    ]);
    await sendViaDock(page, "铺一下并体检");
    await expect(page.getByTestId("chat-card-text")).toBeVisible();
    await expect(page.getByTestId("chat-card-report")).toBeVisible();
    await expect(page.getByText("伏笔 F2 未接")).toBeVisible();
    await restore();
  });

  test("⑩停止：run 收口且可再发（全链慢桩）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-stop-${Date.now()}`);
    // 桩「慢慢来」延迟 3s——窗口内出停止钮
    await sendViaDock(page, "慢慢来");
    await expect(page.getByTestId("chat-stop")).toBeVisible({ timeout: 5000 });
    await page.getByTestId("chat-stop").click();
    await expect(page.getByTestId("chat-stop")).toBeHidden();
    // 可再发：默认分支直接收口
    await sendViaDock(page, "好了没");
    await expect(page.getByText("收到。")).toBeVisible({ timeout: 15000 });
    await restore();
  });

  test("⑪采纳与 run 并发：已采纳卡不被覆盖", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-conc-${Date.now()}`);
    await mockChat(page, [
      [runStart("r1"), artifact("r1", "c1", "text", EXPAND_DRAFT_PAYLOAD()), runEnd("r1")],
      [runStart("r2"), artifact("r2", "c2", "text", EXPAND_DRAFT_PAYLOAD()), runEnd("r2")],
    ]);
    await sendViaDock(page, "铺");
    await page.getByTestId("chat-adopt").click();
    await expect(page.locator(".cd-badge.ok").first()).toBeVisible();
    await sendViaDock(page, "再铺");
    await expect(page.getByTestId("chat-card-text").nth(1)).toBeVisible();
    await expect(page.locator(".cd-badge.ok").first()).toBeVisible();
    await restore();
  });

  test("⑫发散过目：发散徽标＋锚点＋不自动建卡（全链）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-div-${Date.now()}`);
    let characterCreated = 0;
    await page.route("**/api/characters*", async (r) => {
      if (r.request().method() === "POST") characterCreated += 1;
      r.continue();
    });
    await sendViaDock(page, "大胆一点，帮我添个反派");
    await expect(page.getByText("草案·发散")).toBeVisible({ timeout: 30000 });
    await expect(page.getByText("派生自主线")).toBeVisible();
    await new Promise((res) => setTimeout(res, 600));
    expect(characterCreated).toBe(0); // 只产卡——无自动建卡
    await restore();
  });

  test("⑬长会话历史渲染（40 条无错）", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-long-${Date.now()}`);
    const history = Array.from({ length: 40 }, (_, i) => ({
      id: `m${i}`,
      seq: i + 1,
      role: i % 2 === 0 ? "user" : "assistant",
      page: "volume",
      content: i % 2 === 0 ? `第${i}问` : `第${i}答`,
      cardKind: "",
      status: "done",
      payload: {},
      createdAt: "",
    }));
    await mockChat(page, []);
    await page.route("**/api/novels/*/assistant/session*", (r) =>
      r.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: history } }),
    );
    await page.reload();
    await expect(page.getByTestId("aui2-dock")).toBeVisible();
    // CopyStrip（openwriter 移植）让气泡 textContent 带「复制」字样——禁用 exact
    await expect(page.getByText("第38问")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("第39答")).toBeVisible();
    await restore();
  });

  test("⑮朱雀入口：chip 展开工具面板一键可达", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const id = await seedBook(page, token, `e2e-agt-zq-${Date.now()}`);
    // 落一章并选中（章级注册生效前提）
    await fetch(`${ORIGIN}/api/novels/${id}/volumes/vol-1/chapters`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ title: "渡口" }),
    });
    await page.reload();
    await expect(page.getByTestId("aui2-dock")).toBeVisible();
    // 树中点章 → 章级模式；朱雀在正文页签（chips 随章内页签换装）——先切正文
    await page.locator(".col-tree .ch").first().click();
    await expect(page.getByTestId("aui2-chip-draft_chapter_split")).toBeVisible({ timeout: 8000 });
    await page.getByRole("tab", { name: /正文/ }).click();
    await expect(page.getByTestId("aui2-chip-zhuque")).toBeVisible({ timeout: 8000 });
    // 朱雀 chip 直达检测（工具面板退役——chip 即入口）：拦截送检请求为证
    let zqHits = 0;
    await page.route("**/zhuque-check", (r) => {
      zqHits += 1;
      r.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "先写正文" }) });
    });
    await page.getByTestId("aui2-chip-zhuque").click();
    await expect.poll(() => zqHits).toBeGreaterThan(0);
    await restore();
  });

  test("⑭窄屏：FAB 唤出抽屉＋关闭收起", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    await seedBook(page, token, `e2e-agt-narrow-${Date.now()}`);
    await page.setViewportSize({ width: 800, height: 720 });
    // 抽屉默认收起：dock 不可见（visibility hidden），FAB 在
    const probe = await page.evaluate(() => {
      const fabEl = document.querySelector('[data-testid="assistant-fab"]');
      const st = fabEl ? getComputedStyle(fabEl) : null;
      return {
        innerWidth: window.innerWidth,
        fab: !!fabEl,
        fabVisible: !!st && st.display !== "none" && st.visibility !== "hidden",
        asideClass: document.querySelector("aside.col-ai")?.className ?? null,
      };
    });
    console.log("PROBE14", JSON.stringify(probe));
    await expect(page.getByTestId("assistant-fab")).toBeVisible();
    await expect(page.getByTestId("aui2-dock")).toBeHidden();
    // FAB 唤出 → dock 可见＋关闭钮收起
    await page.getByTestId("assistant-fab").click();
    await expect(page.getByTestId("aui2-dock")).toBeVisible();
    await expect(page.getByTestId("chat-drawer-close")).toBeVisible();
    await page.getByTestId("chat-drawer-close").click();
    await page.waitForTimeout(400);
    const probe2 = await page.evaluate(() => ({
      asideClass: document.querySelector("aside.col-ai")?.className ?? null,
      innerWidth: window.innerWidth,
      dockVisible: (() => { const el = document.querySelector('[data-testid="aui2-dock"]'); if (!el) return false; const st = getComputedStyle(el); return st.display !== "none" && st.visibility !== "hidden"; })(),
    }));
    console.log("PROBE14C", JSON.stringify(probe2));
    await expect(page.getByTestId("aui2-dock")).toBeHidden();
    await restore();
  });
});
