// 角色面板首进引导 + 「从简介立主角」（character-bootstrap-from-intro）行为测试。
// c-char-prompt-view 编辑流：点起草＝先出服务端渲染稿提示词（可编辑），点「生成」才出稿，
// 结果段换一个/采纳。手法照 WorldSettingPanel.test.tsx：mock @/lib/api，断言端点调用序与渲染分支。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import CharacterManager, {
  type CharacterSaveHandle,
} from "@/components/novel/settings/CharacterManager";
import { CharsAiRail } from "@/components/novel/AiWriterAssistant";
import type { CharAiCtx } from "@/lib/characterModel";

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPatch = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
    patch: (...a: unknown[]) => apiPatch(...a),
    delete: vi.fn(),
  },
}));

function emptyList() {
  return {
    count: 0,
    protagonist_id: null,
    gate: { ok: false, no_protagonist: true },
    confirmed: false,
    items: [],
  };
}

function cardData(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    novel_id: "p1",
    seq: 1,
    code: "01",
    name: "\u0000abcdef123456",
    aliases: [] as string[],
    role: "主角",
    persona: "",
    dossier: {},
    cog: {},
    rev: 1,
    created_at: null,
    updated_at: null,
    relations: [],
    ...overrides,
  };
}

function listWith(items: Record<string, unknown>[]) {
  return {
    count: items.length,
    protagonist_id: items.some((i) => i.role === "主角") ? (items.find((i) => i.role === "主角") as { id: string }).id : null,
    gate: { ok: false, no_protagonist: !items.some((i) => i.role === "主角") },
    confirmed: false,
    items,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") return Promise.resolve({ data: emptyList() });
    return Promise.resolve({ data: cardData() });
  });
  apiPost.mockResolvedValue({ data: cardData() });
  apiPatch.mockImplementation((_url: string, _body: unknown) =>
    Promise.resolve({ data: { rev: 2 } }),
  );
});

describe("CharacterManager 首进引导", () => {
  it("空态 + 简介已填：引导卡给两个出口", async () => {
    render(<CharacterManager projectId="p1" introReady />);
    expect(await screen.findByText("简介里已经有主角的线索了")).toBeTruthy();
    expect(screen.getByRole("button", { name: "从简介立主角" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "手动建主角" })).toBeTruthy();
  });

  it("空态 + 简介未填：不给 AI 入口，指引先补简介，手动兜底", async () => {
    render(<CharacterManager projectId="p1" introReady={false} />);
    expect(await screen.findByText(/先去 01 简介写几句/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "从简介立主角" })).toBeNull();
    expect(screen.getByRole("button", { name: "手动建主角" })).toBeTruthy();
  });

  it("空态点「添加角色」首卡默认主角", async () => {
    apiPost.mockResolvedValue({ data: cardData() });
    render(<CharacterManager projectId="p1" introReady />);
    await screen.findByText("简介里已经有主角的线索了");
    fireEvent.click(screen.getByRole("button", { name: /添加角色/ }));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/characters", { name: "", role: "主角" });
  });

  it("非空列表点「添加角色」默认配角", async () => {
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData({ name: "张三" })]) });
      }
      return Promise.resolve({ data: cardData({ name: "张三" }) });
    });
    apiPost.mockResolvedValue({ data: cardData({ id: "c2", role: "配角" }) });
    render(<CharacterManager projectId="p1" introReady />);
    await screen.findByText("张三");
    fireEvent.click(screen.getByRole("button", { name: /添加角色/ }));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/characters", { name: "", role: "配角" });
  });
});

describe("CharacterManager 从简介立主角（提示词编辑流）", () => {
  const RENDERED_PROMPT = "【本书】测试书（东方仙侠）\n【新拟名禁令】晚、晴、墨、默……\n【产出】1. name……";
  const DRAFT = {
    name: "林拾",
    aliases: ["拾哥"],
    persona: "扫了十年落叶的杂役弟子。",
    cells: [
      { path: "dossier.race", value: "人族" },
      { path: "cog.w5", value: "不知眼眸来历" },
    ],
    skipped: [{ key: "age", why: "作者自己定" }],
  };

  /** bootstrap 端点桩：preview＝渲染稿；其余＝出稿。 */
  function mockBootstrap(draft: unknown, opts?: { promptText?: string }) {
    apiPost.mockImplementation((url: string, body?: unknown) => {
      if (String(url).includes("/bootstrap")) {
        if ((body as { preview?: boolean } | undefined)?.preview) {
          return Promise.resolve({ data: { prompt: opts?.promptText ?? RENDERED_PROMPT } });
        }
        return Promise.resolve({ data: draft });
      }
      return Promise.resolve({ data: cardData() });
    });
  }

  /** 编辑流驱动：出提示词段 → 点「生成」→ 等结果段（标题出现）。 */
  async function previewAndGenerate() {
    await screen.findByTestId("char-ai-prompt-edit");
    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await screen.findByText("AI 拟稿 · 从简介立主角（采纳才写入）");
  }

  /** 弹窗 footer 的「关闭」键（头部 X 的 aria-label 同名，取 DOM 序最后一个＝footer）。 */
  function footerClose() {
    const btns = screen.getAllByRole("button", { name: "关闭" });
    return btns[btns.length - 1];
  }

  it("空态：点立主角先出提示词编辑段（preview 不出稿），点生成才出稿→采纳", async () => {
    mockBootstrap(DRAFT);
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: emptyList() });
      }
      return Promise.resolve({ data: cardData({ name: "林拾", persona: "扫了十年落叶的杂役弟子。" }) });
    });
    const onCtx = vi.fn();
    render(<CharacterManager projectId="p1" introReady onCtxChange={onCtx} />);
    fireEvent.click(await screen.findByRole("button", { name: "从简介立主角" }));
    // 第一步：提示词编辑段（无结果、无换一个）
    const edit = await screen.findByTestId("char-ai-prompt-edit");
    expect((edit as HTMLTextAreaElement).value).toBe(RENDERED_PROMPT);
    expect(screen.queryByText(/上次生成结果/)).toBeNull();
    expect(screen.queryByRole("button", { name: "换一个" })).toBeNull();
    // 第二步：生成 → 结果段
    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await screen.findByText("AI 拟稿 · 从简介立主角（采纳才写入）");
    const body = screen.getByTestId("char-ai-card").textContent!;
    expect(body).toContain("林拾");
    // 调用序：preview 带渲染稿请求；生成带编辑稿（未改＝渲染稿逐字下发）
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/bootstrap", {
      character_id: undefined,
      preview: true,
    });
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/bootstrap", {
      character_id: undefined,
      prompt: RENDERED_PROMPT,
    });
    // 采纳：create(主角) → aliases/persona/cells 逐格 PATCH（走既有单格写入）
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull()); // 确认写回＝弹窗自动关
    const createCall = apiPost.mock.calls.find((c) => c[0] === "/novels/p1/characters");
    expect(createCall?.[1]).toEqual({ name: "林拾", role: "主角" });
    const patched = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(patched).toEqual(["aliases", "persona", "dossier.race", "cog.w5"]);
  });

  it("改提示词再生成：编辑稿逐字下发，换一个沿用同一编辑稿", async () => {
    mockBootstrap(DRAFT);
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData()]) });
      }
      return Promise.resolve({ data: cardData() });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/一句话人设/);
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    const edited = "【本书】测试书\n【额外要求】名字要土，禁用文艺腔。";
    fireEvent.change(await screen.findByTestId("char-ai-prompt-edit"), {
      target: { value: edited },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await screen.findByText("AI 拟稿 · 从简介立主角（采纳才写入）");
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/bootstrap", {
      character_id: "c1",
      prompt: edited,
    });
    // 换一个＝同一编辑稿重跑
    fireEvent.click(screen.getByRole("button", { name: "换一个" }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(3));
    expect(apiPost).toHaveBeenLastCalledWith("/novels/p1/settings/ai/characters/bootstrap", {
      character_id: "c1",
      prompt: edited,
    });
  });

  it("主角待立：采纳只补空格（名字/别名/人设为空才写）", async () => {
    mockBootstrap({ ...DRAFT, cells: [{ path: "dossier.race", value: "人族" }] });
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({
          data: listWith([cardData({ persona: "已有人设", aliases: ["旧号"] })]),
        });
      }
      return Promise.resolve({ data: cardData({ persona: "已有人设", aliases: ["旧号"] }) });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/一句话人设/); // 卡已加载（哨兵名 → 角色名显示「未命名」）
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await previewAndGenerate();
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const createCalls = apiPost.mock.calls.filter((c) => c[0] === "/novels/p1/characters");
    expect(createCalls).toHaveLength(0); // 不建新卡
    const patched = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(patched).toContain("name");
    expect(patched).not.toContain("persona"); // 已有人设，不动
    expect(patched).not.toContain("aliases"); // 已有别名，不动
    expect(patched).toContain("dossier.race");
  });

  it("出稿后作者手写的格不被覆盖（只写空格复查）", async () => {
    mockBootstrap({
      name: "林拾",
      aliases: [],
      persona: "",
      cells: [{ path: "dossier.look", value: "AI 拟的外貌" }],
    });
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData()]) });
      }
      return Promise.resolve({ data: cardData() });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/一句话人设/);
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await previewAndGenerate();
    // 作者在出稿与采纳之间手写了「外貌标签」（弹窗开着，底层表单仍可编辑）
    fireEvent.change(screen.getByRole("textbox", { name: "外貌标签" }), {
      target: { value: "作者写的外貌" },
    });
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    // dossier.look 只应有作者自己的那次 PATCH，AI 拟稿值不得写入
    const lookPatches = apiPatch.mock.calls.filter(
      (c) => (c[1] as { path: string }).path === "dossier.look",
    );
    expect(lookPatches).toHaveLength(1);
    expect((lookPatches[0][1] as { value: string }).value).toBe("作者写的外貌");
  });

  it("关闭即弃：出稿弹窗关闭后字段不变、无残留", async () => {
    mockBootstrap(DRAFT);
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData()]) });
      }
      return Promise.resolve({ data: cardData() });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/一句话人设/);
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await previewAndGenerate();
    await screen.findByTestId("char-ai-card");
    // 旧后端响应无 prompt 字段＝结果段不出折叠区（DRAFT 未带 prompt）
    expect(screen.queryByTestId("ai-card-prompt")).toBeNull();
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    // 关闭即弃：名字/人设没被写、无 PATCH
    expect((screen.getByRole("textbox", { name: "角色名称" }) as HTMLInputElement).value).toBe("");
    expect((screen.getByRole("textbox", { name: "一句话人设" }) as HTMLTextAreaElement).value).toBe("");
    expect(apiPatch).not.toHaveBeenCalled();
  });

  it("缓存重开：已出过稿再点＝直接展示缓存结果（D9），不回提示词段", async () => {
    mockBootstrap(DRAFT);
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData()]) });
      }
      return Promise.resolve({ data: cardData() });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/一句话人设/);
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await previewAndGenerate();
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    expect(apiPost).toHaveBeenCalledTimes(2); // preview + 生成

    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await screen.findByTestId("char-ai-card");
    expect(document.querySelector('[data-od-id="ai-card-cache"]')).toBeTruthy();
    expect(screen.getByText(/上次生成结果/)).toBeTruthy();
    expect(screen.queryByTestId("char-ai-prompt-edit")).toBeNull(); // 缓存命中不回编辑段
    expect(apiPost).toHaveBeenCalledTimes(2); // 缓存命中，无新请求
  });

  it("选中卡切换时弹窗关闭（缓存面板级寿命）", async () => {
    mockBootstrap(DRAFT);
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({
          data: listWith([cardData({ id: "c1", name: "张三" }), cardData({ id: "c2", name: "李四" })]),
        });
      }
      if (String(url).endsWith("/c1")) return Promise.resolve({ data: cardData({ id: "c1", name: "张三" }) });
      return Promise.resolve({ data: cardData({ id: "c2", name: "李四" }) });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText("张三");
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await previewAndGenerate();
    await screen.findByTestId("char-ai-card");
    fireEvent.click(screen.getByText("李四"));
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    expect(apiPost).toHaveBeenCalledTimes(2); // 切卡不再出稿
  });

  it("AI 门控未就绪：空态按钮点击走 onBlocked、不发请求", async () => {
    const blocked = vi.fn();
    render(<CharacterManager projectId="p1" introReady aiState="no_key" onBlocked={blocked} />);
    fireEvent.click(await screen.findByRole("button", { name: "从简介立主角" }));
    await waitFor(() => expect(blocked).toHaveBeenCalledWith("no_key"));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("出稿弹窗带「查看本次提示词」：单段展示，复制入剪贴板（c-char-prompt-view）", async () => {
    const writeText = vi.fn((_text: string) => Promise.resolve());
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    mockBootstrap({
      ...DRAFT,
      prompt: "【本书】测试书（东方仙侠）\n【新拟名禁令】晚、晴、墨、默……",
    });
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData()]) });
      }
      return Promise.resolve({ data: cardData() });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/一句话人设/);
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await previewAndGenerate();
    await screen.findByTestId("char-ai-card");
    // 结果段折叠区：只有一段（实发用户段），系统段不进前端
    const details = screen.getByTestId("ai-card-prompt");
    expect(details.textContent).toContain("查看本次提示词");
    expect(details.textContent).toContain("【新拟名禁令】");
    expect(details.querySelectorAll("pre")).toHaveLength(1);
    fireEvent.click(screen.getByTestId("ai-card-prompt-copy"));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toContain("【新拟名禁令】");
    expect(writeText.mock.calls[0][0]).not.toContain("【系统】");
    await waitFor(() => expect(screen.getByText("已复制")).toBeTruthy());
  });

  it("剪贴板写入被拒：复制钮静默还原，不弹错（出稿照常可采纳）", async () => {
    const writeText = vi.fn((_text: string) => Promise.reject(new Error("denied")));
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    mockBootstrap({ ...DRAFT, prompt: "u" });
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData()]) });
      }
      return Promise.resolve({ data: cardData() });
    });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/一句话人设/);
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await previewAndGenerate();
    await screen.findByTestId("char-ai-card");
    fireEvent.click(screen.getByTestId("ai-card-prompt-copy"));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.getByText("复制")).toBeTruthy(); // 未变「已复制」
    expect(screen.getByRole("button", { name: "采纳 · 写入" })).toBeTruthy(); // 出稿照常
  });
});

describe("CharsAiRail 从简介立主角行", () => {
  const base: CharAiCtx = {
    name: "未命名",
    nameless: true,
    code: "01",
    role: "主角",
    personaGap: 1,
    dossierGap: 8,
    cogGap: 10,
  };
  const onRun = vi.fn();

  it("主角待立时出现且点击分派 bootstrap", async () => {
    render(<CharsAiRail ctx={base} aiState="ready" onRun={onRun} />);
    fireEvent.click(await screen.findByText("从简介立主角"));
    await waitFor(() => expect(onRun).toHaveBeenCalledWith("bootstrap"));
  });

  it("名字已立或非主角卡不出现该行", () => {
    const { unmount } = render(
      <CharsAiRail ctx={{ ...base, nameless: false, name: "林拾" }} aiState="ready" onRun={onRun} />,
    );
    expect(screen.queryByText("从简介立主角")).toBeNull();
    unmount();
    render(
      <CharsAiRail ctx={{ ...base, role: "配角" }} aiState="ready" onRun={onRun} />,
    );
    expect(screen.queryByText("从简介立主角")).toBeNull();
  });
});
