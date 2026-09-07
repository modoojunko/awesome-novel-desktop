// 设计一致性视觉比对 —— 模型配置屏（/config vs model-config.html）。
// 口径与 design-parity.spec.ts（书架屏）一致：原型 file:// 注入
// localStorage ainovel.apiconfigs（显式空数组=空态，见 ADJUSTMENTS.md）；
// 应用侧打桩 /api/v1/api-configs(+status/usage-summary)/user/profile，
// 与原型 SEED_CONFIGS / SEED_USAGE 逐字段对齐。
import fs from "fs";
import path from "path";
import { test, expect } from "@playwright/test";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { stubUpdateNotice } from "./helpers";

const PROTO_FILE = path.resolve(process.cwd(), "../../docs/design-c/prototypes/model-config.html");
const BASELINE_DIR = path.resolve(process.cwd(), "../../docs/design-c/baselines");
const RUN_PARITY = process.env.DESIGN_PARITY === "1";
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 1 } as const;
const MAX_DIFF_RATIO = 0.002;

// 与原型 SEED_CONFIGS 对齐（last_test_status ← 原型 status；其余字段补齐 ApiConfig 形状）
const SEED_CONFIGS = (): unknown[] => {
  const now = new Date().toISOString();
  const c = (over: Record<string, unknown>) => ({
    vendor_display_name: "",
    status: "active",
    last_test_error: null,
    last_tested_at: null,
    models_updated_at: null,
    created_at: now,
    updated_at: now,
    ...over,
  });
  return [
    c({ id: "c1", name: "主线 · OpenAI", vendor: "openai", base_url: "https://api.openai.com", api_key_masked: "sk-••••••••••A3f9", last_test_status: "ok", models: ["gpt-4o", "gpt-4o-mini", "o3-mini"] }),
    c({ id: "c2", name: "备用 · Anthropic", vendor: "anthropic", base_url: "https://api.anthropic.com", api_key_masked: "sk-ant-••••••••9q2L", last_test_status: "auth_error", models: ["claude-sonnet-5"] }),
    c({ id: "c3", name: "深度求索", vendor: "deepseek", base_url: "https://api.deepseek.com", api_key_masked: "sk-••••••••••x1Kp", last_test_status: "untested", models: [] }),
    c({ id: "c4", name: "本地 · Ollama", vendor: "ollama", base_url: "http://localhost:11434", api_key_masked: "", last_test_status: "ok", models: ["qwen2.5:14b", "llama3.1:8b"] }),
    c({ id: "c5", name: "通义 · Qwen", vendor: "qwen", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", api_key_masked: "sk-••••••••••7D3m", last_test_status: "rate_limited", models: ["qwen-max", "qwen-plus"] }),
    c({ id: "c6", name: "自建 · OpenAI 兼容", vendor: "openai-compat", base_url: "https://llm.example.com/v1", api_key_masked: "sk-••••••••••B2n8", last_test_status: "network_error", models: [] }),
  ];
};

// 原型侧注入用（字段名与 SEED_CONFIGS 一致）
const PROTO_CONFIGS = [
  { id: 'c1', name: '主线 · OpenAI', vendor: 'openai', base_url: 'https://api.openai.com', api_key_masked: 'sk-••••••••••A3f9', status: 'ok', models: ['gpt-4o', 'gpt-4o-mini', 'o3-mini'], affected: 1, tested: '2 小时前' },
  { id: 'c2', name: '备用 · Anthropic', vendor: 'anthropic', base_url: 'https://api.anthropic.com', api_key_masked: 'sk-ant-••••••••9q2L', status: 'auth_error', models: ['claude-sonnet-5'], affected: 1, tested: '昨天' },
  { id: 'c3', name: '深度求索', vendor: 'deepseek', base_url: 'https://api.deepseek.com', api_key_masked: 'sk-••••••••••x1Kp', status: 'untested', models: [], affected: 0, tested: null },
  { id: 'c4', name: '本地 · Ollama', vendor: 'ollama', base_url: 'http://localhost:11434', api_key_masked: '', status: 'ok', models: ['qwen2.5:14b', 'llama3.1:8b'], affected: 1, tested: '1 小时前' },
  { id: 'c5', name: '通义 · Qwen', vendor: 'qwen', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', api_key_masked: 'sk-••••••••••7D3m', status: 'rate_limited', models: ['qwen-max', 'qwen-plus'], affected: 0, tested: '昨天' },
  { id: 'c6', name: '自建 · OpenAI 兼容', vendor: 'openai-compat', base_url: 'https://llm.example.com/v1', api_key_masked: 'sk-••••••••••B2n8', status: 'network_error', models: [], affected: 0, tested: '3 天前' },
];

// 与原型 SEED_USAGE 对齐（queried_at=now → note 文案「刚刚」一致）
const SEED_USAGE = () => ({
  total_all_time: 128450,
  total_this_month: 42310,
  total_today: 1280,
  by_config: [
    { config_id: "c1", config_name: "主线 · OpenAI", tokens: 62000 },
    { config_id: "c4", config_name: "本地 · Ollama", tokens: 38400 },
    { config_id: "c5", config_name: "通义 · Qwen", tokens: 28050 },
  ],
  queried_at: new Date().toISOString(),
});

const CASES = [
  { state: "configs", proto: PROTO_CONFIGS },
  { state: "empty", proto: [] as unknown[] },
] as const;

test.describe("design-parity 模型配置屏（model-config.html）", () => {
  test.skip(
    !RUN_PARITY || !fs.existsSync(PROTO_FILE),
    !RUN_PARITY ? "仅 design:check 运行（DESIGN_PARITY=1）" : "原型缺失：docs/design-c/ 为本地资产"
  );

  for (const c of CASES) {
    test(c.state, async ({ browser }) => {
      // ── 原型侧（设计真值）──────────────────────────────────
      const protoCtx = await browser.newContext({ viewport: VIEWPORT });
      await protoCtx.addInitScript((configs) => {
        localStorage.setItem("ainovel.apiconfigs", JSON.stringify(configs));
      }, c.proto);
      const protoPage = await protoCtx.newPage();
      await protoPage.goto(`file://${PROTO_FILE}`);
      await protoPage.evaluate(() => document.fonts.ready);
      await protoPage.waitForTimeout(700);
      const protoShot = await protoPage.screenshot();
      await protoCtx.close();

      // ── 应用侧（打桩固定数据）──────────────────────────────
      const appCtx = await browser.newContext({ viewport: VIEWPORT });
      await appCtx.addInitScript(() => {
        localStorage.setItem("auth_token", "parity-stub-token");
        localStorage.setItem("auth_username", "parity");
      });
      const appPage = await appCtx.newPage();
      const configs = c.state === "configs" ? SEED_CONFIGS() : [];
      // 注意路由注册顺序（playwright 后注册先匹配）：具体路径在前，精确列表最后
      await appPage.route("**/api/v1/api-configs/usage-summary", (r) => r.fulfill({ json: SEED_USAGE() }));
      await appPage.route("**/api/v1/api-configs/status", (r) => r.fulfill({ json: [] }));
      await appPage.route("**/api/v1/user/profile", (r) => r.fulfill({ json: { migration_completed: true } }));
      await appPage.route("**/api/auth/verify", (r) =>
        r.fulfill({ json: { tier: "monthly", is_member: true, expired: false, trial_remaining_days: 0 } })
      );
      await appPage.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
      await appPage.route("**/api/v1/api-configs", (r) => r.fulfill({ json: configs }));
      // /auth/config（portal_url，公开营销地址非密钥）：新栈 backend 对其 401 会触发
      // api.ts 全局 401 跳 /#/login，把场景弹离配置页——必须就地打桩
      await appPage.route("**/api/auth/config", (r) => r.fulfill({ json: { portal_url: "" } }));
      // model-config.html 原型无更新提示条 → 打桩无更新，应用侧不得渲染
      await stubUpdateNotice(appPage, "none");
      await appPage.goto("/#/config");
      await appPage.waitForLoadState("networkidle");
      await appPage.evaluate(() => document.fonts.ready);
      await appPage.waitForTimeout(700); // page-enter 0.4s 收敛
      const appShot = await appPage.screenshot();
      await appCtx.close();

      // ── 比对 ────────────────────────────────────────────────
      const a = PNG.sync.read(protoShot);
      const b = PNG.sync.read(appShot);
      if (a.width !== b.width || a.height !== b.height) {
        throw new Error(
          `截图尺寸不一致（结构差异）：原型 ${a.width}x${a.height} vs 应用 ${b.width}x${b.height}`
        );
      }
      const diff = new PNG({ width: a.width, height: a.height });
      const diffCount = pixelmatch(a.data, b.data, diff.data, a.width, a.height, {
        threshold: 0.1,
      });
      fs.mkdirSync(BASELINE_DIR, { recursive: true });
      const base = `model-config.${c.state}`;
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.proto.png`), protoShot);
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.app.png`), appShot);
      fs.writeFileSync(path.join(BASELINE_DIR, `${base}.diff.png`), PNG.sync.write(diff));
      const ratio = diffCount / (a.width * a.height);
      expect(
        ratio,
        `像素差异率 ${(ratio * 100).toFixed(3)}%（阈值 0.2%）— 三张对比图见 docs/design-c/baselines/${base}.*`
      ).toBeLessThan(MAX_DIFF_RATIO);
    });
  }
});
