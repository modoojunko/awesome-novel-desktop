// 对话框编排生成正文（c-agent-dialog-prose）前端契约测试。
// 覆盖：streamChapterWrite 的 kb_picks body 契约（键存在即发/空数组也发/未传不带）／
// chips 编排形态按能力端点翻转（command 进对话 vs open 直开）／方案卡渲染
// （条目清单＋提示词折叠全文＋已有正文警示）与「开始生成」宿主桥。
// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const chatApiState = vi.hoisted(() => ({
  loadAssistantSession: vi.fn(),
  streamAssistantChat: vi.fn(),
  approveGate: vi.fn(),
  setPermissionTier: vi.fn(),
  stopAssistantRun: vi.fn(),
  getAssistantCapabilities: vi.fn(),
}));

const modelState = vi.hoisted(() => ({
  options: [] as Array<Record<string, unknown>>,
  currentConfigId: null as string | null,
  currentModel: null as string | null,
  aiState: "ready" as string,
}));

vi.mock("@/hooks/useTier", () => ({
  // 权益门在裸 jsdom 无 LicenseProvider：mock 成 undefined＝「未知，放行」（chip 点击可进）
  useFeature: () => undefined,
}));

vi.mock("@/hooks/useModelStatus", () => ({
  useModelStatus: () => ({
    modelOptions: modelState.options,
    currentConfigId: modelState.currentConfigId,
    currentModel: modelState.currentModel,
    loading: false,
    aiState: modelState.aiState,
  }),
}));

vi.mock("@/lib/chatApi", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    loadAssistantSession: chatApiState.loadAssistantSession,
    streamAssistantChat: chatApiState.streamAssistantChat,
    approveGate: chatApiState.approveGate,
    setPermissionTier: chatApiState.setPermissionTier,
    stopAssistantRun: chatApiState.stopAssistantRun,
    getAssistantCapabilities: chatApiState.getAssistantCapabilities,
  };
});

import { Aui2Dock } from "@/components/novel/chat/Aui2Dock";
import { matchRegistration, setDialogProseEnabled, type ChatPageScope } from "@/lib/chatRegistry";
import { streamChapterWrite } from "@/lib/ai";
import { isForeignProsePlan } from "@/lib/prosePlan";

const PROSE_SCOPE: ChatPageScope = {
  view: "workbench",
  chapterRef: "vol-1-ch-1",
  volumeSelId: null,
  emptyBook: false,
  chapterTab: "prose",
};

function sess(messages: unknown[] = [], grants: Record<string, unknown> = { tier: "confirm_each" }) {
  return {
    sessionId: "s1",
    pageCursor: "",
    grants,
    messages: messages as never[],
  };
}

/** 捕获 SSE 回调的 stream mock：返回 abort 并暴露 drives */
function captureStream() {
  let handlers: { onEvent: (e: unknown) => void; onError: (m: string) => void; onDone: () => void } | null = null;
  chatApiState.streamAssistantChat.mockImplementation(
    (_pid: string, _body: unknown, h: never) => {
      handlers = h as never;
      return () => {};
    },
  );
  return {
    drive: (e: unknown) => handlers?.onEvent(e),
    body: () => chatApiState.streamAssistantChat.mock.calls.at(-1)?.[1] as { message: string },
  };
}

function sseResponse(lines: string[]) {
  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      for (const line of lines) controller.enqueue(enc.encode(`data: ${line}\n\n`));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  setDialogProseEnabled(true);
  chatApiState.loadAssistantSession.mockResolvedValue(sess());
  chatApiState.getAssistantCapabilities.mockResolvedValue({ dialog_prose: true });
  modelState.options = [];
  modelState.currentConfigId = null;
  modelState.currentModel = null;
  modelState.aiState = "ready";
});

describe("streamChapterWrite kb_picks body 契约", () => {
  it("extras.kbPicks 键存在（空数组也算）→ body.kb_picks 下发", async () => {
    let sentBody: string | undefined;
    const fetchMock = vi.fn(async (_url: unknown, init?: { body?: string }) => {
      sentBody = init?.body;
      return sseResponse([JSON.stringify({ type: "done", full_text: "正文" })]);
    });
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("auth_token", "tok");
    streamChapterWrite(
      "p1",
      "vol-1-ch-1",
      { onChunk: vi.fn(), onDone: vi.fn(), onError: vi.fn() },
      "提示词覆盖",
      undefined,
      { kbPicks: [] },
    );
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(sentBody!);
    expect(body.prompt).toBe("提示词覆盖");
    expect(body.kb_picks).toEqual([]); // 键存在即 agent 模式（空数组＝零命中无块）
  });

  it("picks 带理由 → 逐条透传；未传 extras → 不带 kb_picks 键（旧路）", async () => {
    let sentBody: string | undefined;
    const fetchMock = vi.fn(async (_url: unknown, init?: { body?: string }) => {
      sentBody = init?.body;
      return sseResponse([JSON.stringify({ type: "done", full_text: "正文" })]);
    });
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("auth_token", "tok");
    streamChapterWrite("p1", "vol-1-ch-1", { onChunk: vi.fn(), onDone: vi.fn(), onError: vi.fn() }, undefined, undefined, {
      kbPicks: [{ entry_id: "e1", reason: "物件桥段" }, { entry_id: "e2" }],
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
const withPicks = JSON.parse(sentBody!);
    expect(withPicks.kb_picks).toEqual([{ entry_id: "e1", reason: "物件桥段" }, { entry_id: "e2" }]);

    fetchMock.mockClear();
    streamChapterWrite("p1", "vol-1-ch-1", { onChunk: vi.fn(), onDone: vi.fn(), onError: vi.fn() }, "只改提示词");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
const legacy = JSON.parse(sentBody!);
    expect("kb_picks" in legacy).toBe(false); // 不含键＝规则选块旧路
  });
});

describe("chatRegistry 编排形态旗标（setDialogProseEnabled）", () => {
  it("true→command 型；false→open 型直开", () => {
    setDialogProseEnabled(true);
    let chip = matchRegistration(PROSE_SCOPE)!.chips(PROSE_SCOPE).find((c) => c.key === "ai_write")!;
    expect(chip.command).toBe("生成本章正文。");
    expect(chip.open).toBeUndefined();
    setDialogProseEnabled(false);
    chip = matchRegistration(PROSE_SCOPE)!.chips(PROSE_SCOPE).find((c) => c.key === "ai_write")!;
    expect(chip.command).toBe("");
    expect(chip.open).toBe("ai_write");
    setDialogProseEnabled(true); // 还原缺省
  });
});

describe("生成正文 chip 编排形态（能力端点驱动）", () => {
  it("dialog_prose=true → command 型（点 chip 发指令进对话框）", async () => {
    const reg = matchRegistration(PROSE_SCOPE);
    const chip = reg!.chips(PROSE_SCOPE).find((c) => c.key === "ai_write")!;
    expect(chip.command).toBe("生成本章正文。");
    expect(chip.open).toBeUndefined();

    const onProsePlanStart = vi.fn();
    render(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 章节"
        scope={PROSE_SCOPE}
        onProsePlanStart={onProsePlanStart}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("aui2-dock").getAttribute("data-dialog-prose")).toBe("on"),
    );
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-ai_write"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    expect(sse.body().message).toBe("生成本章正文。");
  });

  it("dialog_prose=false（env 熔断）→ open 型（点 chip 宿主直开，不发指令）", async () => {
    chatApiState.getAssistantCapabilities.mockResolvedValue({ dialog_prose: false });
    const onOpenAction = vi.fn();
    const onProsePlanStart = vi.fn();
    render(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 章节"
        scope={PROSE_SCOPE}
        onOpenAction={onOpenAction}
        onProsePlanStart={onProsePlanStart}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("aui2-dock").getAttribute("data-dialog-prose")).toBe("off"),
    );
    fireEvent.click(screen.getByTestId("aui2-chip-ai_write"));
    await waitFor(() => expect(onOpenAction).toHaveBeenCalledWith("ai_write"));
    expect(chatApiState.streamAssistantChat).not.toHaveBeenCalled();
  });
});

describe("方案卡跨章防护（review P1）", () => {
  it("卡上 chapter_ref 与当前章不一致 → 视为别章卡（禁止开流）；空值不误伤", () => {
    expect(isForeignProsePlan({ chapter_ref: "vol-1-ch-5" }, "vol-1-ch-6")).toBe(true);
    expect(isForeignProsePlan({ chapter_ref: "vol-1-ch-6" }, "vol-1-ch-6")).toBe(false);
    expect(isForeignProsePlan({ chapter_ref: "" }, "vol-1-ch-6")).toBe(false);
    expect(isForeignProsePlan({}, "vol-1-ch-6")).toBe(false);
    expect(isForeignProsePlan({ chapter_ref: "vol-1-ch-5" }, null)).toBe(false);
  });
});

describe("正文方案卡（prose_plan）渲染与开始生成宿主桥", () => {
  const PLAN_PAYLOAD = {
    chapter_ref: "vol-1-ch-1",
    chapter_title: "第七章",
    prompt: "提".repeat(500),
    picks: [
      { entry_id: "e1", title: "体温计反转", concept: "手法", reason: "章纲已安排物件试探桥段" },
      { entry_id: "e2", title: "以物写情", concept: "文笔", reason: "落点用物件收" },
    ],
    has_existing_prose: true,
    word_target: 2500,
  };

  function planCardEvent() {
    return {
      type: "artifact",
      cardId: "c1",
      kind: "prose_plan",
      payload: PLAN_PAYLOAD,
    };
  }

  it("条目清单＋理由＋提示词折叠全文＋已有正文警示；开始生成桥接宿主并翻已开始", async () => {
    // 宿主确认通过后回调 onStarted（同步路径：无已有正文时宿主立即开流）
    const onProsePlanStart = vi.fn(
      (_payload: Record<string, unknown>, started?: () => void) => started?.(),
    );
    render(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 章节"
        scope={PROSE_SCOPE}
        onProsePlanStart={onProsePlanStart}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("aui2-dock").getAttribute("data-dialog-prose")).toBe("on"),
    );
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-ai_write"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());

    act(() => sse.drive(planCardEvent()));
    const body = await screen.findByTestId("prose-plan-body");
    expect(body.textContent).toContain("第七章");
    expect(body.textContent).toContain("体温计反转");
    expect(body.textContent).toContain("章纲已安排物件试探桥段");
    expect(body.textContent).toContain("以物写情");
    expect(body.textContent).toContain("本章已有正文"); // 清空重写警示
    // 提示词折叠：默认只显前 400 字，展开见全文
    const pre = body.querySelector(".cd-plan-prompt-text")!;
    expect(pre.textContent!.length).toBe(400);
    fireEvent.click(screen.getByTestId("prose-plan-toggle"));
    expect(body.querySelector(".cd-plan-prompt-text")!.textContent!.length).toBe(500);

    // 开始生成：宿主桥收全 payload（提示词全文＋picks）
    await waitFor(() => {
      fireEvent.click(screen.getByTestId("prose-plan-start"));
      expect(onProsePlanStart).toHaveBeenCalledTimes(1);
    });
    expect(onProsePlanStart.mock.calls[0][0].prompt).toBe(PLAN_PAYLOAD.prompt);
    expect(onProsePlanStart.mock.calls[0][0].picks).toHaveLength(2);
    // 卡面翻「已开始生成」
    await waitFor(() => expect(screen.getByText(/已开始生成/)).toBeTruthy());
    expect(screen.queryByTestId("prose-plan-start")).toBeNull();
  });

  it("宿主未确认（onStarted 未回调，如再生成确认框被取消）→ 卡面停留草稿态", async () => {
    const onProsePlanStart = vi.fn(); // 模拟宿主弹确认框：暂不回调 onStarted
    render(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 章节"
        scope={PROSE_SCOPE}
        onProsePlanStart={onProsePlanStart}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("aui2-dock").getAttribute("data-dialog-prose")).toBe("on"),
    );
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-ai_write"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    act(() => sse.drive(planCardEvent()));
    await screen.findByTestId("prose-plan-body");
    await waitFor(() => {
      fireEvent.click(screen.getByTestId("prose-plan-start"));
      expect(onProsePlanStart).toHaveBeenCalledTimes(1);
    });
    // 确认未通过：不翻「已开始」、按钮仍在（clearing 之前曾同步翻卡的回归钉）
    expect(screen.queryByText(/已开始生成/)).toBeNull();
    expect(screen.queryByTestId("prose-plan-start")).toBeTruthy();
  });

  it("未命中（picks 空）明示回退文风设定", async () => {
    const onProsePlanStart = vi.fn();
    render(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 章节"
        scope={PROSE_SCOPE}
        onProsePlanStart={onProsePlanStart}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("aui2-dock").getAttribute("data-dialog-prose")).toBe("on"),
    );
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-ai_write"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    act(() =>
      sse.drive({
        type: "artifact",
        cardId: "c2",
        kind: "prose_plan",
        payload: { ...PLAN_PAYLOAD, picks: [], has_existing_prose: false },
      }),
    );
    const nomatch = await screen.findByTestId("prose-plan-nomatch");
    expect(nomatch.textContent).toContain("按本书文风设定生成");
    expect(screen.queryByTestId("prose-plan-picks")).toBeNull();
    // 无已有正文：不出现清空警示
    expect(screen.queryByTestId("prose-plan-body")!.textContent).not.toContain("本章已有正文");
  });
});

describe("正文方案卡生成模型（c-prose-plan-review-model）", () => {
  const OPTS = [
    { api_config_id: "c1", model: "m1", config_name: "配置一", vendor: "deepseek" },
    { api_config_id: "c2", model: "m2", config_name: "配置二", vendor: "ollama" },
  ];
  const PAYLOAD = {
    chapter_ref: "vol-1-ch-1",
    chapter_title: "第七章",
    prompt: "提示词全文",
    picks: [{ entry_id: "e1", title: "道具盘点否定法", concept: "手法", reason: "贴本章" }],
    has_existing_prose: false,
    word_target: 2500,
  };

  function stubRect() {
    return vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 100, bottom: 140, left: 20, right: 540, width: 520, height: 40, x: 20, y: 100,
      toJSON: () => ({}),
    } as DOMRect);
  }

  async function openPlan(
    onProsePlanStart: (payload: Record<string, unknown>, onStarted?: () => void) => void,
  ) {
    render(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 章节"
        scope={PROSE_SCOPE}
        onProsePlanStart={onProsePlanStart}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("aui2-dock").getAttribute("data-dialog-prose")).toBe("on"),
    );
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-ai_write"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    act(() =>
      sse.drive({ type: "artifact", cardId: "c1", kind: "prose_plan", payload: PAYLOAD }),
    );
    await screen.findByTestId("prose-plan-body");
  }

  function useTwoModels() {
    modelState.options = OPTS;
    modelState.currentConfigId = "c1";
    modelState.currentModel = "m1";
  }

  it("模型行默认本书模型；未换模型时 payload 不带 model_selection", async () => {
    useTwoModels();
    const onStart = vi.fn((_p: Record<string, unknown>, started?: () => void) => started?.());
    await openPlan(onStart);
    const field = await screen.findByTestId("prose-plan-model");
    expect(within(field).getByTestId("ai-model-name").textContent).toBe("配置一 · m1");
    fireEvent.click(screen.getByTestId("prose-plan-start"));
    expect(onStart).toHaveBeenCalledTimes(1);
    const payload = onStart.mock.calls[0][0] as Record<string, unknown>;
    expect("model_selection" in payload).toBe(false);
  });

  it("卡上换模型 → payload 带按次模型对", async () => {
    useTwoModels();
    const onStart = vi.fn((_p: Record<string, unknown>, started?: () => void) => started?.());
    await openPlan(onStart);
    const field = await screen.findByTestId("prose-plan-model");
    const rectSpy = stubRect();
    try {
      fireEvent.click(within(field).getByTestId("ai-model-select"));
      const panel = await screen.findByTestId("ai-model-panel");
      fireEvent.click(within(panel).getByRole("option", { name: /m2/ }));
    } finally {
      rectSpy.mockRestore();
    }
    fireEvent.click(screen.getByTestId("prose-plan-start"));
    const payload = onStart.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.model_selection).toEqual({ api_config_id: "c2", model: "m2" });
  });

  it("可选模型 < 2 不渲染模型行", async () => {
    modelState.options = [OPTS[0]];
    modelState.currentConfigId = "c1";
    modelState.currentModel = "m1";
    await openPlan(vi.fn());
    expect(screen.queryByTestId("prose-plan-model")).toBeNull();
  });

  it("未点开始生成不调用宿主（评审闸）", async () => {
    useTwoModels();
    const onStart = vi.fn();
    await openPlan(onStart);
    expect(onStart).not.toHaveBeenCalled();
  });
});
