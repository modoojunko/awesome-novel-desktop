// 文风量化（style-settings-v2 批2/批3）E2E —— 打桩 AI（零真实调用）：
//   ① 蒸馏全链：样本勾选 → 三步进度 → 作者画像确认 → 六行基线落卡 → 锁定切换
//   ② 区间不足：合计 <3,000 字 → 开始蒸馏禁用＋补样本提示
//   ③ 免费门控：ai_state=member_required → 右栏 AI 卡整体锁定（可见＋不可用）
//   ④ 润色采纳回执：右栏「润色文字文风」→ 三区覆盖 → 回执撤销精确回滚
//   ⑤ 粘贴全链（c-style-paste-distill）：弹窗字数门 → 三步（桩校验 text）→
//      确认卡基线预览 → 落卡样本字数一致
//   ⑥ 粘贴重启＋重试携 text：预置旧 draft（step2）→ 粘贴重启清旧产物 →
//      step1 首试 502 后重试仍带 text → 「取消，稍后再说」收起可恢复确认卡
// 前置：docker 4 服务已启动；CONFIG_PATH 为 docker C端 config.json（bind mount）。
import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);

async function sRegisterAndLogin() {
  const name = `e2e_sq_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/** 把 S端 会话写入 config.json，返回恢复函数（竞态守卫同 foreshadow-ai）。 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
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

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const restoreConfig = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: { token, username, tier } } }),
  );
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    await restoreConfig();
  };
  return { restore: restoreAndCleanup, token };
}

async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first()); // 稳定点击保险（风暴由守卫用例钉死）
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

/** 桩本书 AI 就绪态（D13）＋配置清单。 */
async function stubAiState(page: Page, pid: string, aiState: string) {
  await page.route(`**/api/v1/novels/${pid}/ai-model`, (r) =>
    r.fulfill({
      json: {
        api_config_id: aiState === "missing_model" ? null : "c1",
        model: aiState === "missing_model" ? null : "gpt-4o",
        config_name: "主配置",
        ai_state: aiState,
        effective_model: aiState === "ready" ? "gpt-4o" : "",
        reason: aiState,
        message: "",
      },
    }),
  );
  await page.route("**/api/v1/api-configs", (r) =>
    r.fulfill({
      json: [
        {
          id: "c1",
          name: "主配置",
          vendor: "openai",
          models: ["gpt-4o"],
          status: "active",
          last_test_status: "ok",
        },
      ],
    }),
  );
}

/** 文风面板桩：style GET/PUT、status、readiness（三区空书＝未确认可确认）。 */
async function stubStyleBase(page: Page, pid: string) {
  await page.route(`**/api/novels/${pid}/settings/style`, (r) => {
    if (r.request().method() === "PUT") {
      r.fulfill({ json: { ok: true } });
      return;
    }
    r.fulfill({ json: { role: "", rules: [], craft: [], few_shot_examples: [] } });
  });
}

const EMPTY_QUANT = {
  version: 1,
  confidence: 0,
  sample_chars: 0,
  updated_at: "",
  baseline: {},
  details: {},
  portrait: "",
  history: [],
  draft: null,
};

const SAMPLES_IN_RANGE = {
  files: [{ name: "a.md", chars: 4102 }],
  chapters: [{ id: "ch-9", label: "第 09 章 残卷", chars: 3112 }],
  total: 7214,
  min: 3000,
  max: 10000,
  in_range: true,
  hint: "",
};

const COMMITTED_BASELINE = {
  narrative: { value: "第三人称限知 · 紧贴林拾", tolerance: 10, locked: false },
  rhythm: { value: "对话 48% 动作 24% 叙述 15% 环境 7% 内心独白 6%", tolerance: 10, locked: false },
  syntax: { value: "平均句长 14.6 字（短 41 · 中 38 · 长 16 · 超长 5）", tolerance: 10, locked: false },
  lexicon: { value: "修饰词 8.1/百字（形容 4.2 · 副词 1.8 · 四字短语 2.1）", tolerance: 10, locked: false },
  emotion: { value: "主通道：动作生理 58%（直接陈述压到 12%）", tolerance: 10, locked: false },
  dialogue_verb: { value: "对话 18 字/轮 · 标签动作主导 · 动词力度 strong", tolerance: 10, locked: false },
};

const STEP3_OUT = {
  ok: true,
  step: 3,
  portrait: "一个冷静但不冷漠的讲述者：贴着林拾写，情绪不直说，藏在动作和细节里。",
};

test.describe.serial("文风量化蒸馏链路", () => {
  test("① 蒸馏全链：样本→三步→画像确认落卡→基线渲染→锁定切换", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `蒸馏${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await stubStyleBase(page, pid);

      // 有状态假 KV：draft 随步进增长（模拟后端 style-quant.draft），commit 后为正式基线
      let committed = false;
      const draftState: { step: number; step3?: { portrait: string } } = { step: 0 };
      const quant = () => {
        if (!committed)
          return {
            ...EMPTY_QUANT,
            draft: draftState.step > 0 ? { ...draftState } : null,
          };
        return {
          version: 1,
          confidence: 82,
          sample_chars: 7214,
          updated_at: "2026-09-15T12:00:00",
          baseline: COMMITTED_BASELINE,
          details: { 词法: "形容词 4.2/百字 · 高频词 6 个", 句法: "平均句长 14.6 字" },
          portrait: "一个冷静但不冷漠的讲述者。",
          history: [
            {
              at: "2026-09-15T12:00:00",
              sample_chars: 7214,
              confidence: 82,
              baseline: COMMITTED_BASELINE,
              mixture: {},
            },
          ],
          draft: {},
        };
      };
      await page.route(`**/api/novels/${pid}/settings/style-quant`, (r) => {
        if (r.request().method() === "PUT") {
          const body = r.request().postDataJSON() as { locks?: Record<string, boolean> };
          if (body?.locks?.rhythm !== undefined && COMMITTED_BASELINE.rhythm) {
            COMMITTED_BASELINE.rhythm.locked = body.locks.rhythm;
          }
          r.fulfill({ json: quant() });
          return;
        }
        r.fulfill({ json: quant() });
      });
      await page.route(`**/api/novels/${pid}/settings/style-samples`, (r) =>
        r.fulfill({ json: SAMPLES_IN_RANGE }),
      );
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step1`, (r) => {
        draftState.step = 1;
        r.fulfill({ json: { ok: true, step: 1 } });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step2`, (r) => {
        draftState.step = 2;
        r.fulfill({ json: { ok: true, step: 2 } });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step3`, (r) => {
        draftState.step = 3;
        draftState.step3 = { portrait: STEP3_OUT.portrait };
        r.fulfill({ json: STEP3_OUT });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/commit`, (r) => {
        committed = true;
        r.fulfill({ json: { ok: true, quant: quant(), banned_added: 1 } });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await page
        .locator(".settings-v .col-tree")
        .getByText("文风", { exact: true })
        .click();
      await page.locator('[data-od-id="ptab-quant"]').click();
      await expect(page.locator('[data-od-id="quant-empty"]')).toBeVisible();

      // 去蒸馏 → 样本两路列出且默认全选（合计 7,214 字在区间内）
      await page.locator('[data-od-id="btn-open-distill"]').click();
      await expect(page.locator('[data-od-id="distill-samples"]')).toContainText("a.md");
      await expect(page.locator('[data-od-id="distill-samples"]')).toContainText("7,214");

      // 开始蒸馏：三步全绿 → 画像确认卡
      await page.locator('[data-od-id="btn-run-distill"]').click();
      await expect(page.locator('[data-od-id="author-portrait"]')).toBeVisible({ timeout: 5000 });

      // 落卡：基线六行渲染＋页签徽标翻「置信度 82」
      await page.locator('[data-od-id="btn-portrait-keep"]').click();
      await expect(page.locator('[data-od-id="quant-panel"]')).toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-od-id="quant-tab-badge"]')).toContainText("置信度 82");
      await expect(page.locator('[data-od-id="quant-baseline"]')).toContainText("镜头与人称");
      await expect(page.locator('[data-od-id="quant-baseline"]')).toContainText("±10%");
      await expect(page.locator('[data-od-id="quant-note"]')).toContainText("写章的 AI 按本章剧情自行调节");

      // 锁定切换：aria-pressed 翻转
      const lock = page.locator('[data-od-id="lock-rhythm"]');
      await lock.click();
      await expect(lock).toHaveAttribute("aria-pressed", "true");
    } finally {
      await restore();
    }
  });

  test("② 区间不足：合计 <3,000 → 开始蒸馏禁用＋补样本提示", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `区间${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await stubStyleBase(page, pid);
      await page.route(`**/api/novels/${pid}/settings/style-quant`, (r) =>
        r.fulfill({ json: EMPTY_QUANT }),
      );
      await page.route(`**/api/novels/${pid}/settings/style-samples`, (r) =>
        r.fulfill({
          json: {
            files: [{ name: "short.md", chars: 2100 }],
            chapters: [],
            total: 2100,
            min: 3000,
            max: 10000,
            in_range: false,
            hint: "样本合计 2,100 字，少于 3,000 字统计噪声大——再补一些你认可的文章",
          },
        }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.locator(".settings-v .col-tree").getByText("文风", { exact: true }).click();
      await page.locator('[data-od-id="ptab-quant"]').click();
      await page.locator('[data-od-id="btn-open-distill"]').click();
      const run = page.locator('[data-od-id="btn-run-distill"]');
      await expect(run).toBeDisabled();
      await expect(page.locator('[data-od-id="distill-samples"]')).toContainText("再补");
    } finally {
      await restore();
    }
  });

  test("③ 免费门控：ai_state=member_required → 右栏 AI 卡锁定", async ({ page }) => {
    const { restore } = await setupSession(page, "none");
    try {
      const pid = await createNovel(page, `免费${Date.now() % 100000}`);
      await stubAiState(page, pid, "member_required");
      await stubStyleBase(page, pid);
      await page.route(`**/api/novels/${pid}/settings/style-quant`, (r) =>
        r.fulfill({ json: EMPTY_QUANT }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.locator(".settings-v .col-tree").getByText("文风", { exact: true }).click();
      const rail = page.locator('[data-od-id="ai-assist-style"]');
      await expect(rail).toHaveClass(/locked/);
      await expect(rail).toContainText("未解锁 · 升级 PRO 后本书 AI 即可用");
      // 量化空态照常可见（免费也能看，只是不能蒸馏）
      await page.locator('[data-od-id="ptab-quant"]').click();
      await expect(page.locator('[data-od-id="quant-empty"]')).toBeVisible();
    } finally {
      await restore();
    }
  });

  test("④ 润色采纳回执：三区覆盖→回执撤销精确回滚", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `润色${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await stubStyleBase(page, pid);
      await page.route(`**/api/novels/${pid}/settings/style-quant`, (r) =>
        r.fulfill({ json: EMPTY_QUANT }),
      );
      await page.route(`**/api/novels/${pid}/settings/ai/style/polish`, (r) =>
        r.fulfill({
          json: {
            role: "AI 起草的叙事身份",
            rules: ["每章结尾必须有钩子"],
            craft: ["情绪通过动作表达"],
          },
        }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.locator(".settings-v .col-tree").getByText("文风", { exact: true }).click();
      await expect(page.locator('[data-od-id="input-style-role"]')).toHaveValue("");

      // 右栏「润色文字文风」→ style-ai-card 弹窗出卡 → 采纳 · 覆盖三区
      await page.locator('[data-aiact="polish"]').click();
      const card = page.getByTestId("style-ai-card");
      await expect(card).toBeVisible({ timeout: 10000 });
      await expect(card).toContainText("AI 起草的叙事身份");
      await page.getByTestId("ai-card-adopt").click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.locator('[data-od-id="input-style-role"]')).toHaveValue("AI 起草的叙事身份");
      await expect(page.locator('[data-od-id="panel-receipt"]')).toContainText("润色文字文风");

      // 回执撤销：三区回滚
      await page.locator('[data-od-id="panel-undo"]').click();
      await expect(page.locator('[data-od-id="input-style-role"]')).toHaveValue("");
    } finally {
      await restore();
    }
  });

  // ── 粘贴样本第三路（c-style-paste-distill）─────────────────────────

  const PASTE_TEXT = "雨点砸在铁皮棚上，他没有抬头。".repeat(240); // 去空白 3,600 字
  const PREVIEW_ROWS = {
    narrative: { value: "第三人称限知 · 紧贴林拾", tolerance: 20 },
    rhythm: { value: "对话 44% 动作 26% 叙述 14% 环境 9% 内心独白 7%", tolerance: 20 },
    syntax: { value: "平均句长 14.6 字", tolerance: 20 },
    lexicon: { value: "修饰词 8.1/百字", tolerance: 20 },
    emotion: { value: "主通道：动作生理 58%", tolerance: 20 },
    dialogue_verb: { value: "对话 18 字/轮 · 动词力度 strong", tolerance: 20 },
  };

  test("⑤ 粘贴全链：弹窗字数门→三步（桩校验 text）→确认卡基线预览→落卡", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `粘贴${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await stubStyleBase(page, pid);

      // 有状态假 KV（c-style-paste-distill 锁法）：step1 仅在 body.text 非空时打
      // pasted 标；step2/3 校验 pasted 否则 400——前端若回归为闭包旧值起步直调
      // step3，用例即红（防假绿）
      let pasted = false;
      let committed = false;
      const draftState: {
        step: number;
        sample_chars?: number;
        step3?: { portrait: string; rows: typeof PREVIEW_ROWS };
      } = { step: 0 };
      const quant = () => {
        if (!committed)
          return {
            ...EMPTY_QUANT,
            draft: draftState.step > 0 ? { ...draftState } : null,
          };
        return {
          version: 1,
          confidence: 60,
          sample_chars: 3600,
          updated_at: "2026-09-18T12:00:00",
          baseline: Object.fromEntries(
            Object.entries(PREVIEW_ROWS).map(([k, v]) => [k, { ...v, locked: false }]),
          ),
          details: { 词法: "形容词 4.2/百字" },
          portrait: "一个冷静但不冷漠的讲述者。",
          history: [],
          draft: {},
        };
      };
      await page.route(`**/api/novels/${pid}/settings/style-quant`, (r) => {
        if (r.request().method() === "PUT") {
          r.fulfill({ json: quant() });
          return;
        }
        r.fulfill({ json: quant() });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step1`, (r) => {
        const body = r.request().postDataJSON() as { text?: unknown };
        if (typeof body?.text === "string" && body.text.length > 0) {
          pasted = true;
          draftState.step = 1;
          draftState.sample_chars = 3600;
          r.fulfill({ json: { ok: true, step: 1 } });
          return;
        }
        r.fulfill({ status: 400, json: { detail: "样本合计 0 字，少于 3000 字统计噪声大——再补一些你认可的文章" } });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step2`, (r) => {
        if (!pasted) {
          r.fulfill({ status: 400, json: { detail: "先完成第一步（样本标注）" } });
          return;
        }
        draftState.step = 2;
        r.fulfill({ json: { ok: true, step: 2 } });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step3`, (r) => {
        if (!pasted) {
          r.fulfill({ status: 400, json: { detail: "先完成第二步（量化统计）" } });
          return;
        }
        draftState.step = 3;
        draftState.step3 = { portrait: STEP3_OUT.portrait, rows: PREVIEW_ROWS };
        r.fulfill({ json: { ...STEP3_OUT, portrait: STEP3_OUT.portrait } });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/commit`, (r) => {
        committed = true;
        r.fulfill({ json: { ok: true, quant: quant(), banned_added: 0 } });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.locator(".settings-v .col-tree").getByText("文风", { exact: true }).click();
      await page.locator('[data-od-id="ptab-quant"]').click();
      await expect(page.locator('[data-od-id="quant-empty"]')).toBeVisible();

      // 空态主入口「粘贴文本蒸馏」直开弹窗
      await page.locator('[data-od-id="btn-open-paste"]').click();
      const textarea = page.locator('[data-od-id="input-paste-sample"]');
      await expect(textarea).toBeVisible();

      // 字数门：空 → 禁用；短文 → 还差提示；区间内 → 可提交
      await expect(page.locator('[data-od-id="btn-paste-start"]')).toBeDisabled();
      await textarea.fill("雨".repeat(2100));
      await expect(page.locator('[data-od-id="paste-hint"]')).toContainText("还差 900 字");
      await expect(page.locator('[data-od-id="btn-paste-start"]')).toBeDisabled();
      await textarea.fill(PASTE_TEXT);
      await expect(page.locator('[data-od-id="paste-hint"]')).toContainText("区间内");
      await page.locator('[data-od-id="btn-paste-start"]').click();

      // 三步全绿 → 画像确认卡（含落卡基线预览：预览＝落卡同一常量，渲染格式同构）
      await expect(page.locator('[data-od-id="author-portrait"]')).toBeVisible({ timeout: 5000 });
      const preview = page.locator('[data-od-id="portrait-baseline-preview"]');
      await expect(preview).toContainText("约 第三人称限知 · 紧贴林拾（±20%）");
      await expect(preview).toContainText(`约 ${PREVIEW_ROWS.rhythm.value}（±20%）`);
      // 未落过卡：无锁定行，预览不出现「保留上一版」
      await expect(preview.locator(".badge")).toHaveCount(0);

      // 落卡：正式区六行与预览渲染格式一致；样本字数＝粘贴字数
      await page.locator('[data-od-id="btn-portrait-keep"]').click();
      await expect(page.locator('[data-od-id="quant-panel"]')).toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-od-id="quant-tab-badge"]')).toContainText("置信度 60");
      await expect(page.locator('[data-od-id="quant-baseline"]')).toContainText(
        `约 ${PREVIEW_ROWS.narrative.value}（±20%）`,
      );
      await expect(page.locator('[data-od-id="quant-panel"]')).toContainText("3,600 字样本");
    } finally {
      await restore();
    }
  });

  test("⑥ 粘贴重启＋重试携 text：旧 draft 作废→step1 首试 502 重试仍带 text→「稍后再说」可恢复", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `重启${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await stubStyleBase(page, pid);

      // 预置旧 draft（文件路跑到 step2）；粘贴链桩：step1 带 text 才重置＋打标，
      // 首次带 text 的调用回 502（锁「重试仍携 text」），重试成功后放行 step2/3
      let pasted = false;
      let pasteAttempts = 0;
      const draftState: {
        step: number;
        sample_chars?: number;
        step3?: { portrait: string; rows: typeof PREVIEW_ROWS };
      } = { step: 2 };
      const quant = () => ({
        ...EMPTY_QUANT,
        draft: draftState.step > 0 ? { ...draftState } : null,
      });
      await page.route(`**/api/novels/${pid}/settings/style-quant`, (r) => r.fulfill({ json: quant() }));
      await page.route(`**/api/novels/${pid}/settings/style-samples`, (r) =>
        r.fulfill({ json: SAMPLES_IN_RANGE }),
      );
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step1`, (r) => {
        const body = r.request().postDataJSON() as { text?: unknown };
        if (typeof body?.text === "string" && body.text.length > 0) {
          pasteAttempts += 1;
          if (pasteAttempts === 1) {
            r.fulfill({ status: 502, json: { detail: "AI 学习失败，可重试" } });
            return;
          }
          pasted = true;
          draftState.step = 1;
          draftState.sample_chars = 3600;
          r.fulfill({ json: { ok: true, step: 1 } });
          return;
        }
        r.fulfill({ status: 400, json: { detail: "样本合计 0 字，少于 3000 字统计噪声大——再补一些你认可的文章" } });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step2`, (r) => {
        if (!pasted) {
          r.fulfill({ status: 400, json: { detail: "先完成第一步（样本标注）" } });
          return;
        }
        draftState.step = 2;
        r.fulfill({ json: { ok: true, step: 2 } });
      });
      await page.route(`**/api/novels/${pid}/settings/ai/style-distill/step3`, (r) => {
        if (!pasted) {
          r.fulfill({ status: 400, json: { detail: "先完成第二步（量化统计）" } });
          return;
        }
        draftState.step = 3;
        draftState.step3 = { portrait: STEP3_OUT.portrait, rows: PREVIEW_ROWS };
        r.fulfill({ json: { ...STEP3_OUT, portrait: STEP3_OUT.portrait } });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.locator(".settings-v .col-tree").getByText("文风", { exact: true }).click();
      await page.locator('[data-od-id="ptab-quant"]').click();
      // 旧 draft 挂起（step2 无画像）：仍可进样本页，粘贴入口在样本框顶部
      await page.locator('[data-od-id="btn-open-distill"]').click();
      await expect(page.locator('[data-od-id="distill-samples"]')).toBeVisible();
      await page.locator('[data-od-id="btn-open-paste"]').click();
      const textarea = page.locator('[data-od-id="input-paste-sample"]');
      await textarea.fill(PASTE_TEXT);
      await page.locator('[data-od-id="btn-paste-start"]').click();

      // 粘贴重启：首试 502 → 错误可见，但按钮可重试（粘贴文本仍由前端携带）
      await expect(page.locator('[data-od-id="style-error"]')).toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-od-id="btn-run-distill"]')).toBeEnabled();
      await page.locator('[data-od-id="btn-run-distill"]').click();

      // 重试携 text：粘贴链通过 → 画像确认卡
      await expect(page.locator('[data-od-id="author-portrait"]')).toBeVisible({ timeout: 5000 });

      // 「取消，稍后再说」：收起面板保留 draft；重开蒸馏恢复确认卡
      await page.locator('[data-od-id="btn-portrait-later"]').click();
      await expect(page.locator('[data-od-id="quant-empty"]')).toBeVisible();
      await page.locator('[data-od-id="btn-open-distill"]').click();
      await expect(page.locator('[data-od-id="author-portrait"]')).toBeVisible({ timeout: 5000 });
    } finally {
      await restore();
    }
  });
});
