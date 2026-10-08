// AiModal 交互（c-prompt-tab-retire 后单段式；c-retire-prompt-polish：原「AI 润色」
// 按钮整链退役，弹窗只剩 组装/刷新 → 编辑/存稿 → 生成）：
// 本次组装稿标「本次组装」；存量稿标「本章已存稿」；
// 编辑后确认透传提示词。
// c-prompt-tab-retire：新增「存为本章提示词」（PUT prompts/write）与 onPromptSaved。
// 「刷新提示词」：fresh=1 绕过存量行重新组装（换稿＋转本次组装），失败不动当前稿。
// c-prose-model-select：新增「生成模型」选择位（跨配置/供应商按次选模型，仅本次生效）——
// 弹窗现在会取配置清单与本书模型，故请求桩按 URL 分派。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AiModal } from "@/components/novel/workbench/modals";

const reqState = vi.hoisted(() => ({ request: vi.fn(), put: vi.fn() }));
const toastState = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ request: reqState.request, api: { put: reqState.put } }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

// ── 模型域桩（c-prose-model-select）：跨配置 × 多模型 + 本书模型就绪 ────────────
const CONFIGS = [
  {
    id: "c1",
    name: "深度求索",
    vendor: "deepseek",
    models: ["deepseek-v4-pro", "deepseek-v4-flash"],
  },
  { id: "c2", name: "本地 · Ollama", vendor: "ollama", models: ["qwen2.5:14b"] },
];
const AI_MODEL_READY = {
  api_config_id: "c1",
  config_name: "深度求索",
  model: "deepseek-v4-pro",
  ai_state: "ready",
  message: "",
};

/** 按 URL 分派：提示词端点走 `prompt` 序列/实现，模型域走固定桩。 */
function installRequestMock(
  prompt?: Record<string, unknown> | (() => Promise<unknown>),
  opts: { configs?: unknown; aiModel?: unknown } = {},
) {
  const nextPrompt =
    typeof prompt === "function"
      ? (prompt as () => Promise<unknown>)
      : () => Promise.resolve(prompt ?? { prompt: "## 角色定位\n本次组装稿", has_outline: true, polished: false });
  reqState.request.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/novels/p1/chapters/")) {
      return nextPrompt();
    }
    if (url === "/api-configs") return Promise.resolve(opts.configs ?? CONFIGS);
    if (url === "/novels/p1/ai-model") return Promise.resolve(opts.aiModel ?? AI_MODEL_READY);
    return Promise.resolve({});
  });
}

/** 提示词端点响应队列（每次调用取下一个，末项用尽后重复）。 */
function promptQueue(...resps: Array<Record<string, unknown> | Error>) {
  let i = 0;
  return () => {
    const r = resps[Math.min(i++, resps.length - 1)];
    return r instanceof Error ? Promise.reject(r) : Promise.resolve(r);
  };
}

function renderModal(onConfirm = vi.fn(), onPromptSaved = vi.fn()) {
  render(
    <AiModal
      open
      onClose={vi.fn()}
      projectId="p1"
      chapterRef="vol-1-ch-1"
      onConfirm={onConfirm}
      onPromptSaved={onPromptSaved}
    />,
  );
  return { onConfirm, onPromptSaved };
}

beforeEach(() => {
  vi.clearAllMocks();
  reqState.put.mockResolvedValue({});
  installRequestMock();
});

describe("AiModal（组装 → 编辑/存稿 → 生成）", () => {
  it("本次组装稿：标「本次组装」，且不再出现「AI 润色」入口（c-retire-prompt-polish）", async () => {
    renderModal();
    const ta = await screen.findByTestId("ai-prompt");
    expect((ta as HTMLTextAreaElement).value).toContain("本次组装稿");
    expect(screen.getByTestId("ai-raw-tag").textContent).toBe("本次组装");
    expect(screen.queryByTestId("ai-polish")).toBeNull();
    expect(screen.queryByText("AI 润色")).toBeNull();
  });

  it("存量稿：标「本章已存稿」", async () => {
    installRequestMock({
      prompt: "## 任务指示\n存量稿",
      has_outline: true,
      polished: true,
    });
    renderModal();
    await screen.findByTestId("ai-polished-tag");
    expect(screen.getByTestId("ai-polished-tag").textContent).toBe("本章已存稿");
  });

  it("刷新提示词：fresh=1 重新组装 + 换稿转「本次组装」", async () => {
    installRequestMock(
      promptQueue(
        { prompt: "## 任务指示\n存量稿", has_outline: true, polished: true },
        { prompt: "## 角色定位\n按新章纲重组稿", has_outline: true, polished: false },
      ),
    );
    renderModal();
    await screen.findByTestId("ai-polished-tag");
    fireEvent.click(screen.getByTestId("ai-prompt-refresh"));
    await waitFor(() =>
      expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
        "按新章纲重组稿",
      ),
    );
    // 第二次请求带 fresh=1（绕过存量行组装）
    expect(reqState.request).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/write/prompt?fresh=1",
      { quiet: true },
    );
    expect(screen.getByTestId("ai-raw-tag").textContent).toBe("本次组装");
  });

  it("刷新失败：报错 toast 且既有稿不清空", async () => {
    installRequestMock(
      promptQueue(
        { prompt: "## 任务指示\n存量稿", has_outline: true, polished: true },
        new Error("组装失败"),
      ),
    );
    renderModal();
    await screen.findByTestId("ai-polished-tag");
    fireEvent.click(screen.getByTestId("ai-prompt-refresh"));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("组装失败"));
    expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
      "存量稿",
    );
  });

  it("旧版整包分级提示：raw 行建议刷新、polished 行只信息性", async () => {
    // raw：粗组存稿旧行 → warn 提示含「刷新」引导
    installRequestMock(
      promptQueue(
        {
          prompt: "## 角色定位\n你是。\n## 故事背景\n……",
          has_outline: true,
          polished: true,
          legacy_kind: "raw",
        },
        { prompt: "## 当前章节\n重组稿", has_outline: true, polished: false, legacy_kind: "" },
      ),
    );
    renderModal();
    const note = await screen.findByTestId("ai-legacy-note");
    expect(note.textContent).toContain("刷新提示词");
    fireEvent.click(screen.getByTestId("ai-prompt-refresh"));
    await waitFor(() =>
      expect(screen.queryByTestId("ai-legacy-note")).toBeNull(),
    );
  });

  it("旧版润色行：只显示信息性说明，不引导覆盖", async () => {
    installRequestMock({
      prompt: "## 任务指示\n…\n## 红线\n…\n## 质感\n…",
      has_outline: true,
      polished: true,
      legacy_kind: "polished",
    });
    renderModal();
    const note = await screen.findByTestId("ai-legacy-note");
    expect(note.textContent).toContain("已由系统按本书设定注入");
    expect(note.textContent).not.toContain("刷新");
  });

  it("lint 告警随 GET 透出显示", async () => {
    installRequestMock({
      prompt: "## 当前章节\n稿",
      has_outline: true,
      polished: false,
      legacy_kind: "",
      warnings: ["「本章必须完成」未获剧情条目覆盖：主角黑化"],
    });
    renderModal();
    const warns = await screen.findByTestId("ai-lint-warnings");
    expect(warns.textContent).toContain("未获剧情条目覆盖");
  });

  it("初始组装失败 → 刷新成功：错误清除且「生成正文」恢复可点", async () => {
    installRequestMock(
      promptQueue(new Error("提示词组装失败"), {
        prompt: "## 角色定位\n刷新后的组装稿",
        has_outline: true,
        polished: false,
      }),
    );
    const { onConfirm } = renderModal();
    await screen.findByText(/提示词组装失败/);
    expect(
      (screen.getByTestId("ai-confirm") as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByTestId("ai-prompt-refresh"));
    await waitFor(() =>
      expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
        "刷新后的组装稿",
      ),
    );
    // 错误段落撤下 + 「生成正文」解锁，刷新＝初始失败态的第二条恢复路径
    expect(screen.queryByText(/提示词组装失败/)).toBeNull();
    expect(
      (screen.getByTestId("ai-confirm") as HTMLButtonElement).disabled,
    ).toBe(false);
    fireEvent.click(screen.getByTestId("ai-confirm"));
    expect(onConfirm).toHaveBeenCalledWith("## 角色定位\n刷新后的组装稿", undefined);
  });

  it("存为本章提示词：PUT prompts/write + 转存量标 + onPromptSaved", async () => {
    reqState.put.mockResolvedValue({});
    const { onPromptSaved } = renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.change(screen.getByTestId("ai-prompt"), {
      target: { value: "## 任务指示\n作家存稿" },
    });
    fireEvent.click(screen.getByTestId("ai-prompt-save"));
    await waitFor(() =>
      expect(reqState.put).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/prompts/write",
        { content: "## 任务指示\n作家存稿" },
      ),
    );
    await screen.findByTestId("ai-polished-tag");
    expect(toastState.success).toHaveBeenCalledWith("已存为本章提示词");
    expect(onPromptSaved).toHaveBeenCalled();
  });

  it("编辑后「生成正文」透传当前提示词", async () => {
    const { onConfirm } = renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.change(screen.getByTestId("ai-prompt"), {
      target: { value: "## 任务指示\n作家手改稿" },
    });
    fireEvent.click(screen.getByTestId("ai-confirm"));
    expect(onConfirm).toHaveBeenCalledWith("## 任务指示\n作家手改稿", undefined);
  });
});

// ── c-prose-model-select：生成模型选择位（跨配置/供应商，按次生效）─────────────
describe("AiModal · 生成模型选择位", () => {
  it("默认本书模型：触发位显示「配置名 · 模型名」，确认不带按次模型对", async () => {
    const { onConfirm } = renderModal();
    await screen.findByTestId("ai-prompt");
    const trigger = await screen.findByTestId("ai-model-select");
    expect(screen.getByTestId("ai-model-name").textContent).toBe(
      "深度求索 · deepseek-v4-pro",
    );
    fireEvent.click(trigger);
    const panel = await screen.findByTestId("ai-model-panel");
    // 跨配置分组：两个配置名都在弹层里（组头）
    expect(panel.textContent).toContain("深度求索");
    expect(panel.textContent).toContain("本地 · Ollama");
    // 「本书模型」标记只跟在绑定行
    expect(panel.textContent).toContain("本书模型");
    fireEvent.click(screen.getByTestId("ai-confirm"));
    expect(onConfirm).toHaveBeenCalledWith(expect.any(String), undefined);
  });

  it("换到另一配置的模型：确认携带按次模型对（仅本次生效）", async () => {
    const { onConfirm } = renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.click(await screen.findByTestId("ai-model-select"));
    fireEvent.click(screen.getByTestId("ai-model-panel").querySelector('[data-model="c2::qwen2.5:14b"]')!);
    expect(screen.getByTestId("ai-model-name").textContent).toBe("本地 · Ollama · qwen2.5:14b");
    fireEvent.click(screen.getByTestId("ai-confirm"));
    expect(onConfirm).toHaveBeenCalledWith(expect.any(String), {
      api_config_id: "c2",
      model: "qwen2.5:14b",
    });
  });

  it("换回本书模型：按次模型对撤销（仍走本书模型路径）", async () => {
    const { onConfirm } = renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.click(await screen.findByTestId("ai-model-select"));
    fireEvent.click(screen.getByTestId("ai-model-panel").querySelector('[data-model="c1::deepseek-v4-flash"]')!);
    fireEvent.click(screen.getByTestId("ai-model-select"));
    fireEvent.click(screen.getByTestId("ai-model-panel").querySelector('[data-model="c1::deepseek-v4-pro"]')!);
    fireEvent.click(screen.getByTestId("ai-confirm"));
    expect(onConfirm).toHaveBeenCalledWith(expect.any(String), undefined);
  });

  it("Esc 只收弹层：弹窗不关、提示词与选择保留", async () => {
    const onClose = vi.fn();
    render(
      <AiModal
        open
        onClose={onClose}
        projectId="p1"
        chapterRef="vol-1-ch-1"
        onConfirm={vi.fn()}
      />,
    );
    await screen.findByTestId("ai-prompt");
    fireEvent.click(await screen.findByTestId("ai-model-select"));
    expect(await screen.findByTestId("ai-model-panel")).toBeTruthy();
    fireEvent.keyDown(screen.getByTestId("ai-model-select"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("ai-model-panel")).toBeNull());
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByTestId("ai-prompt")).toBeTruthy();
  });

  it("单选/未就绪：不渲染选择位（单模型用户零变化）", async () => {
    // 全部配置合计只有一个可选模型
    installRequestMock(undefined, {
      configs: [{ id: "c1", name: "深度求索", vendor: "deepseek", models: ["deepseek-v4-pro"] }],
    });
    renderModal();
    await screen.findByTestId("ai-prompt");
    await waitFor(() => expect(reqState.request).toHaveBeenCalledWith("/api-configs", { apiBase: "/api/v1" }));
    expect(screen.queryByTestId("ai-model-select")).toBeNull();
  });

  it("本书模型未就绪：不渲染选择位（按次选择是叠加在就绪之上的选择）", async () => {
    installRequestMock(undefined, {
      aiModel: { api_config_id: "c1", config_name: "深度求索", model: "", ai_state: "missing_model", message: "先在本书选择模型" },
    });
    renderModal();
    await screen.findByTestId("ai-prompt");
    await waitFor(() =>
      expect(reqState.request).toHaveBeenCalledWith("/novels/p1/ai-model", { apiBase: "/api/v1" }),
    );
    expect(screen.queryByTestId("ai-model-select")).toBeNull();
  });

  // 评审整改（P2）：多配置时弹层只受视口约束（封顶＋整层滚动），不再逐组裁切
  it("弹层带视口感知上限：空间充足时下方展开且 maxHeight 有封顶", async () => {
    renderModal();
    await screen.findByTestId("ai-prompt");
    const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 100, bottom: 140, left: 20, right: 540, width: 520, height: 40, x: 20, y: 100,
      toJSON: () => ({}),
    } as DOMRect);
    try {
      fireEvent.click(await screen.findByTestId("ai-model-select"));
      const panel = await screen.findByTestId("ai-model-panel");
      expect(panel.style.top).toBe("146px");
      expect(panel.style.bottom).toBe("");
      expect(panel.style.maxHeight).toBe("360px");
    } finally {
      rectSpy.mockRestore();
    }
  });

  it("弹层放不下时向上翻转（挂 bottom）且按上方可用空间限高", async () => {
    renderModal();
    await screen.findByTestId("ai-prompt");
    const origH = window.innerHeight;
    const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 700, bottom: 740, left: 20, right: 540, width: 520, height: 40, x: 20, y: 700,
      toJSON: () => ({}),
    } as DOMRect);
    Object.defineProperty(window, "innerHeight", { value: 900, configurable: true });
    try {
      fireEvent.click(await screen.findByTestId("ai-model-select"));
      const panel = await screen.findByTestId("ai-model-panel");
      expect(panel.style.bottom).toBe("206px"); // (900-700)+6：下缘贴触发位上缘
      expect(panel.style.top).toBe("");
      expect(panel.style.maxHeight).toBe("360px");
    } finally {
      rectSpy.mockRestore();
      Object.defineProperty(window, "innerHeight", { value: origH, configurable: true });
    }
  });

  it("键盘停在哪一行对读屏可见（aria-activedescendant 指向选项 id）", async () => {
    renderModal();
    await screen.findByTestId("ai-prompt");
    const trigger = await screen.findByTestId("ai-model-select");
    fireEvent.click(trigger);
    await screen.findByTestId("ai-model-panel");
    // 首项即本书模型（c1::deepseek-v4-pro）
    expect(trigger.getAttribute("aria-activedescendant")).toBe("ai-model-opt-0");
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(trigger.getAttribute("aria-activedescendant")).toBe("ai-model-opt-1");
    const active = document.getElementById("ai-model-opt-1");
    expect(active?.getAttribute("role")).toBe("option");
    expect(active?.textContent).toContain("deepseek-v4-flash");
    // 收起后不再指向已卸载的选项
    fireEvent.keyDown(trigger, { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("ai-model-panel")).toBeNull());
    expect(trigger.getAttribute("aria-activedescendant")).toBeNull();
  });
});
