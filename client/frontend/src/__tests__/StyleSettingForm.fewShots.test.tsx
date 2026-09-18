// style-settings-v2 — 文风表单两页签测试：
//   · 文风例句（few_shot_examples 1-3 条）：加载回读（>3 截断）、保存载荷（trim/过滤/截断 3）
//   · 撤并键零写回：GET 返回旧键（possible_mistakes/tone/narrator_role）时
//     PUT payload 只含白名单四键（评审 P0）
//   · 页签徽标：题材默认 ↔ 已自定义 · N 处
//   · 确认门槛 canConfirm：叙事身份非空
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { configure } from "@testing-library/react";
// 组件用 data-od-id 做定位属性（与 e2e 同源）——vitest 侧把 testId 指过去
configure({ testIdAttribute: "data-od-id" });
import { createRef } from "react";
import StyleSettingForm from "@/components/novel/settings/StyleSettingForm";
import type { SettingSaveHandle } from "@/components/novel/settings/FormField";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiState }));

const PH = "如：雨点砸在铁皮棚上，他没有抬头。";

function mockGet(style: Record<string, unknown>, quant: Record<string, unknown> = {}) {
  apiState.get.mockImplementation((url: string) => {
    if (url.endsWith("/settings/style")) return Promise.resolve(style);
    if (url.endsWith("/settings/style-quant")) return Promise.resolve(quant);
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function renderForm() {
  const ref = createRef<SettingSaveHandle>();
  render(
    <StyleSettingForm ref={ref} projectId="p1" settingKey="style" />,
  );
  return ref;
}

function rows(): HTMLInputElement[] {
  return screen.getAllByPlaceholderText(PH) as HTMLInputElement[];
}

/** 例句输入所在的 Cfg 折叠块（文风例句专属，避免命中其他 ListEditor 的添加按钮） */
function fewShotsCfg() {
  const cfg = rows()[0].closest("details");
  if (!cfg) throw new Error("文风例句 Cfg 块未找到");
  return within(cfg as HTMLElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet({ role: "一位小说家" });
  apiState.put.mockResolvedValue({});
  apiState.post.mockResolvedValue({});
});

describe("文风例句 few_shot_examples", () => {
  it("加载回读存量例句；>3 条只取前 3 且例句满 3 时不再出现「添加一项」", async () => {
    mockGet({ role: "r", few_shot_examples: ["例句一", "例句二", "例句三", "例句四"] });
    renderForm();
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(rows().map((r) => r.value)).toEqual(["例句一", "例句二", "例句三"]);
    // maxItems=3：例句行数已满时块内「添加一项」不渲染（其他块不受影响）
    expect(fewShotsCfg().queryByText("添加一项")).toBeNull();
  });

  it("保存载荷包含 few_shot_examples：trim + 过滤空行 + 截断 3", async () => {
    const ref = renderForm();
    await waitFor(() => expect(rows()).toHaveLength(1));
    fireEvent.change(rows()[0], { target: { value: "  雨点砸在铁皮棚上。 " } });
    fireEvent.click(fewShotsCfg().getByText("添加一项"));
    fireEvent.change(rows()[1], { target: { value: "   " } }); // 纯空白 → 过滤

    expect(await ref.current!.save()).toBe(true);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/settings/style",
      expect.objectContaining({ few_shot_examples: ["雨点砸在铁皮棚上。"] }),
    );
  });

  it("存量为空 → 单空行可编辑；保存时输出空数组（不塞空串）", async () => {
    const ref = renderForm();
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rows()[0].value).toBe("");
    fireEvent.change(rows()[0], { target: { value: "他数到第七声雷，才开口。" } });

    expect(await ref.current!.save()).toBe(true);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/settings/style",
      expect.objectContaining({ few_shot_examples: ["他数到第七声雷，才开口。"] }),
    );
  });
});

describe("禁用词收编（banned-words-into-style）", () => {
  it("commit 并入禁用词后直接保存：表单态已回读合并，新词不丢", async () => {
    // 初载词表 1 条；画像确认 commit 服务端并入「眸子」（banned_added=1）→
    // 组件回读 GET 到 v2 → 用户不切面板直接保存 → payload 必须带新词（D4 丢词回归）
    const styleV1 = { role: "r", banned_words: ["突然"], tic_patterns: [] };
    const styleV2 = { role: "r", banned_words: ["突然", "眸子"], tic_patterns: [] };
    let styleGets = 0;
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) {
        styleGets += 1;
        return Promise.resolve(styleGets === 1 ? styleV1 : styleV2);
      }
      if (url.endsWith("/settings/style-quant")) {
        // draft 已到画像步：openDistill 直接进入画像确认视图
        return Promise.resolve({ draft: { step: 3, step3: { portrait: "像你的写法" } } });
      }
      if (url.endsWith("/settings/style-samples")) {
        return Promise.resolve({ files: [], chapters: [], min: 3000, max: 10000, in_range: false, hint: "再补些样本" });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    apiState.post.mockResolvedValue({
      ok: true,
      quant: { confidence: 80, baseline: {}, history: [], draft: null, sample_chars: 7214, updated_at: "2026-09-16" },
      banned_added: 1,
    });

    const ref = createRef<SettingSaveHandle>();
    render(<StyleSettingForm ref={ref} projectId="p1" settingKey="style" />);
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());

    // 右栏 AI 四行入口「蒸馏我的文风」→ 量化页签 → 画像确认 → 落卡
    const handle = ref.current as unknown as { runAi?: (key: string) => Promise<void> };
    await handle.runAi!("distill");
    // 旧 draft 无 rows（跨部署边界）：确认卡预览段整段隐藏，不渲染空壳（c-style-paste-distill）
    expect(screen.queryByTestId("portrait-baseline-preview")).toBeNull();
    fireEvent.click(await screen.findByText("就是这样，落卡"));

    // commit 后回读合并：等第二次 style GET（回读）落地再保存
    await waitFor(() => {
      const styleGets = apiState.get.mock.calls.filter(([u]) => String(u).endsWith("/settings/style")).length;
      expect(styleGets).toBeGreaterThanOrEqual(2);
    });
    expect(await ref.current!.save()).toBe(true);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/settings/style",
      expect.objectContaining({ banned_words: ["突然", "眸子"] }),
    );
  });
});

describe("落卡基线预览（c-style-paste-distill）", () => {
  it("确认卡渲染 rows 六行；锁定行显示上一版值＋「保留上一版」标记，不显示新值", async () => {
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "r", banned_words: [], tic_patterns: [] });
      if (url.endsWith("/settings/style-quant"))
        return Promise.resolve({
          confidence: 0,
          baseline: { rhythm: { value: "旧配比", tolerance: 10, locked: true } },
          draft: {
            step: 3,
            sample_chars: 5040,
            step3: {
              portrait: "像你的写法",
              rows: {
                narrative: { value: "第三人称限知", tolerance: 20 },
                rhythm: { value: "对话 48% 动作 24%", tolerance: 20 },
                syntax: { value: "平均句长 14 字", tolerance: 20 },
                lexicon: { value: "修饰 8/百字", tolerance: 20 },
                emotion: { value: "动作生理 58%", tolerance: 20 },
                dialogue_verb: { value: "标签动作主导", tolerance: 20 },
              },
            },
          },
        });
      if (url.endsWith("/settings/style-samples"))
        return Promise.resolve({ files: [], chapters: [], min: 3000, max: 10000, in_range: false, hint: "x" });
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    apiState.post.mockResolvedValue({
      ok: true,
      quant: { confidence: 53, baseline: {}, history: [], draft: null, sample_chars: 5040, updated_at: "x" },
      banned_added: 0,
    });
    const ref = createRef<SettingSaveHandle>();
    render(<StyleSettingForm ref={ref} projectId="p1" settingKey="style" />);
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    const handle = ref.current as unknown as { runAi?: (key: string) => Promise<void> };
    await handle.runAi!("distill");
    const preview = await screen.findByTestId("portrait-baseline-preview");
    // 非锁定行：新蒸馏值＋预览容差
    expect(preview.textContent).toContain("约 第三人称限知（±20%）");
    // 锁定行：如实显示落卡将保留的上一版值（预览＝落卡），新值不出现
    expect(preview.textContent).toContain("保留上一版");
    expect(preview.textContent).toContain("约 旧配比（±10%）");
    expect(preview.textContent).not.toContain("对话 48%");
  });
});

describe("撤并键零写回（评审 P0）", () => {  it("GET 带旧键（possible_mistakes/tone/narrator_role）时 PUT payload 只含白名单四键", async () => {
    mockGet({
      role: "冷静叙事者",
      core_principles: ["克制"],
      possible_mistakes: ["不要滥用形容词"],
      depiction_techniques: ["动作外化"],
      narrator_role: "第三人称限知",
      tone: { default_tone: "冷静" },
    });
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    expect(await ref.current!.save()).toBe(true);
    expect(apiState.put).toHaveBeenCalledTimes(1);
    const body = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(["banned_words", "craft", "few_shot_examples", "role", "rules", "tic_patterns"]);
  });
});

describe("两页签与确认门槛", () => {
  it("页签徽标：题材默认 → 改身份后「已自定义 · 1 处」", async () => {
    mockGet({ role: "冷静叙事者", rules: ["钩子"] });
    renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    expect(screen.getByTestId("style-tab-badge").textContent).toBe("题材默认");
    fireEvent.change(screen.getByTestId("input-style-role"), { target: { value: "改过的身份" } });
    expect(screen.getByTestId("style-tab-badge").textContent).toBe("已自定义 · 1 处");
  });

  it("canConfirm：叙事身份非空 true、空 false", async () => {
    mockGet({ role: "" });
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    expect(ref.current!.canConfirm?.()).toBe(false);
    fireEvent.change(screen.getByTestId("input-style-role"), { target: { value: "冷静叙事者" } });
    expect(ref.current!.canConfirm?.()).toBe(true);
  });

  it("量化页签未蒸馏空态：PRO 徽＋去蒸馏入口；页签徽「未蒸馏」", async () => {
    renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: /量化参数/ }));
    await waitFor(() => expect(screen.getByTestId("quant-empty")).toBeTruthy());
    expect(screen.getByTestId("quant-tab-badge").textContent).toBe("未蒸馏");
  });
});
