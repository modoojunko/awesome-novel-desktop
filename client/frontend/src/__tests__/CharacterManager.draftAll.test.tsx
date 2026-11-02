// 「起草角色」（c-chars-draft-all）：右栏行门控＋有卡补空格 / 无卡新建（角色可选）
// ＋编辑流（提示词可改→生成→采纳）＋缓存重开＋迟到守卫。手法照 bootstrap 测试：mock @/lib/api。
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

function cardData(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    novel_id: "p1",
    seq: 1,
    code: "01",
    name: "\u0000abcdef123456",
    aliases: [] as string[],
    role: "配角",
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
    protagonist_id: items.some((i) => i.role === "主角")
      ? (items.find((i) => i.role === "主角") as { id: string }).id
      : null,
    gate: { ok: false, no_protagonist: !items.some((i) => i.role === "主角") },
    confirmed: false,
    items,
  };
}

function emptyList() {
  return {
    count: 0,
    protagonist_id: null,
    gate: { ok: false, no_protagonist: true },
    confirmed: false,
    items: [],
  };
}

const RENDERED_PROMPT = "【本书】雨区渡口……\n【已确认的设定】\n【题材】……";
const SOURCES = ["题材", "简介"];
const DRAFT = {
  role: "配角",
  name: "老周",
  aliases: ["周船工"],
  persona: "渡口撑船三十年，认得每一道水纹。",
  cells: [
    { path: "dossier.look", value: "黝黑精瘦" },
    { path: "cog.v1", value: "攒钱把船换成新船" },
  ],
  skipped: [{ key: "race", why: "简介没提" }],
  prompt: RENDERED_PROMPT,
  sources: SOURCES,
};

function mockDraftAll(draft: unknown = DRAFT) {
  apiPost.mockImplementation((url: string, body?: unknown) => {
    if (String(url).includes("/draft-all")) {
      if ((body as { preview?: boolean } | undefined)?.preview) {
        return Promise.resolve({ data: { prompt: RENDERED_PROMPT, sources: SOURCES, role: "配角" } });
      }
      return Promise.resolve({ data: draft });
    }
    return Promise.resolve({ data: cardData() });
  });
}

function sideCardSetup(overrides: Record<string, unknown> = {}) {
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({ data: listWith([cardData(overrides)]) });
    }
    return Promise.resolve({ data: cardData(overrides) });
  });
  mockDraftAll();
  apiPatch.mockResolvedValue({ data: { rev: 2 } });
}

function footerClose() {
  const btns = screen.getAllByRole("button", { name: "关闭" });
  return btns[btns.length - 1];
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CharsAiRail 起草角色行", () => {
  const base: CharAiCtx = {
    name: "老周",
    nameless: false,
    code: "02",
    role: "配角",
    personaGap: 1,
    dossierGap: 3,
    cogGap: 5,
  };
  const onRun = vi.fn();

  it("有卡有空格：首行出现且点击分派 draftAll", async () => {
    render(
      <CharsAiRail ctx={base} hasCards hasConfirmed aiState="ready" onRun={onRun} />,
    );
    fireEvent.click(await screen.findByTestId("char-rail-draft-all"));
    await waitFor(() => expect(onRun).toHaveBeenCalledWith("draftAll"));
    // 旧三补充与一键立卡已合并退役
    expect(screen.queryByText("人设补充")).toBeNull();
    expect(screen.queryByText("基础信息补充")).toBeNull();
    expect(screen.queryByText("认知补充")).toBeNull();
    expect(screen.queryByText("一键立卡")).toBeNull();
    expect(screen.getByText("一致性体检")).toBeTruthy();
  });

  it("卡满退场；路人只看档案空格", () => {
    const { unmount } = render(
      <CharsAiRail
        ctx={{ ...base, personaGap: 0, dossierGap: 0, cogGap: 0 }}
        hasCards
        hasConfirmed
        aiState="ready"
        onRun={onRun}
      />,
    );
    expect(screen.queryByTestId("char-rail-draft-all")).toBeNull();
    unmount();
    render(
      <CharsAiRail
        ctx={{ ...base, role: "路人", personaGap: 1, dossierGap: 2, cogGap: 0 }}
        hasCards
        hasConfirmed
        aiState="ready"
        onRun={onRun}
      />,
    );
    expect(screen.getByTestId("char-rail-draft-all").textContent).toContain("基础档案");
  });

  it("只剩名字为空也出起草角色行；主角待立仍不给", () => {
    const { unmount } = render(
      <CharsAiRail
        ctx={{
          ...base,
          nameless: true,
          name: "未命名",
          personaGap: 0,
          dossierGap: 0,
          cogGap: 0,
        }}
        hasCards
        hasConfirmed
        aiState="ready"
        onRun={onRun}
      />,
    );
    expect(screen.getByTestId("char-rail-draft-all")).toBeTruthy();
    unmount();
    render(
      <CharsAiRail
        ctx={{
          ...base,
          role: "主角",
          nameless: true,
          name: "未命名",
          personaGap: 0,
          dossierGap: 0,
          cogGap: 0,
        }}
        hasCards
        hasConfirmed
        aiState="ready"
        onRun={onRun}
      />,
    );
    expect(screen.queryByTestId("char-rail-draft-all")).toBeNull();
  });

  it("有卡但未选中：起草角色＝新建；空书不出现", () => {
    const { unmount } = render(
      <CharsAiRail ctx={null} hasCards hasConfirmed aiState="ready" onRun={onRun} />,
    );
    expect(screen.getByTestId("char-rail-draft-all").textContent).toContain("新建一张角色卡");
    unmount();
    render(
      <CharsAiRail ctx={null} noCard introReady hasConfirmed aiState="ready" onRun={onRun} />,
    );
    expect(screen.queryByTestId("char-rail-draft-all")).toBeNull();
  });

  it("没有已确认设定：行置灰＋先确认设定，点击不分派", () => {
    render(
      <CharsAiRail ctx={base} hasCards hasConfirmed={false} aiState="ready" onRun={onRun} />,
    );
    const row = screen.getByTestId("char-rail-draft-all") as HTMLButtonElement;
    expect(row.disabled).toBe(true);
    expect(row.textContent).toContain("先确认设定");
    fireEvent.click(row);
    expect(onRun).not.toHaveBeenCalled();
  });
});

describe("CharacterManager 起草角色：有卡只补空格", () => {
  it("预览→生成→采纳：不建卡，只写空格", async () => {
    sideCardSetup({ name: "老周", persona: "已有人设", dossier: { race: "人族" } });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText("老周");

    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-prompt-edit");
    expect(screen.getByTestId("char-draft-sources").textContent).toContain("本次输入：题材、简介");
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/draft-all", {
      character_id: "c1",
      role: undefined,
      preview: true,
    });

    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await screen.findByText("AI 拟稿 · 起草角色（采纳才写入）");
    // 结果段也要标明本次输入（spec：结果段 SHALL 标明已确认项）
    expect(screen.getByTestId("char-draft-sources").textContent).toContain("本次输入：题材、简介");
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/draft-all", {
      character_id: "c1",
      role: undefined,
      prompt: RENDERED_PROMPT,
    });

    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const patched = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    // 名字/人设/种族已写 → 不动；别名与空格落库
    expect(patched).toEqual(["aliases", "dossier.look", "cog.v1"]);
    const createCalls = apiPost.mock.calls.filter((c) => c[0] === "/novels/p1/characters");
    expect(createCalls).toHaveLength(0);
  });

  it("缓存重开不回提示词段、不发新请求", async () => {
    sideCardSetup({ name: "老周" });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText("老周");
    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-prompt-edit");
    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await screen.findByText("AI 拟稿 · 起草角色（采纳才写入）");
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    expect(apiPost).toHaveBeenCalledTimes(2);

    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-card");
    expect(screen.getByText(/上次生成结果/)).toBeTruthy();
    expect(screen.queryByTestId("char-ai-prompt-edit")).toBeNull();
    expect(apiPost).toHaveBeenCalledTimes(2);
  });
});

describe("CharacterManager 起草角色：无卡新建", () => {
  it("默认配角→切反派：预览/生成/采纳都带角色，采纳建卡", async () => {
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") return Promise.resolve({ data: emptyList() });
      return Promise.resolve({ data: cardData({ id: "c9", name: "老周", role: "反派" }) });
    });
    mockDraftAll({ ...DRAFT, role: "反派" });
    apiPatch.mockResolvedValue({ data: { rev: 2 } });

    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByTestId("char-empty-guide");

    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-prompt-edit");
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/draft-all", {
      character_id: undefined,
      role: "配角",
      preview: true,
    });
    // 无卡时可切反派：切角色＝重新取渲染稿（不调 AI）
    fireEvent.click(screen.getByTestId("char-draft-role-villain"));
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/draft-all", {
        character_id: undefined,
        role: "反派",
        preview: true,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await screen.findByText("AI 拟稿 · 起草角色（采纳才建卡）");
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/draft-all", {
      character_id: undefined,
      role: "反派",
      prompt: RENDERED_PROMPT,
    });

    fireEvent.click(screen.getByRole("button", { name: "采纳 · 建卡" }));
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/novels/p1/characters", {
        name: "老周",
        role: "反派",
      }),
    );
    const patched = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(patched).toEqual(["aliases", "persona", "dossier.look", "cog.v1"]);
  });

  it("双击采纳只建一张卡（在途互斥）", async () => {
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") return Promise.resolve({ data: emptyList() });
      return Promise.resolve({ data: cardData({ id: "c9", name: "老周", role: "配角" }) });
    });
    mockDraftAll();
    apiPatch.mockResolvedValue({ data: { rev: 2 } });

    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByTestId("char-empty-guide");
    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-prompt-edit");
    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await screen.findByText("AI 拟稿 · 起草角色（采纳才建卡）");

    const adopt = screen.getByRole("button", { name: "采纳 · 建卡" });
    fireEvent.click(adopt);
    fireEvent.click(adopt); // 同一 tick 连点：第二次必须被在途互斥丢弃
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const createCalls = apiPost.mock.calls.filter((c) => c[0] === "/novels/p1/characters");
    expect(createCalls).toHaveLength(1);
  });
});

describe("CharacterManager 起草角色：迟到守卫", () => {
  it("生成途中切卡：迟到草稿弃用，不在别的卡上开弹窗", async () => {
    let resolveDraft!: (v: { data: unknown }) => void;
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({
          data: listWith([
            cardData({ id: "c1", name: "阿一" }),
            cardData({ id: "c2", name: "阿二" }),
          ]),
        });
      }
      if (String(url).endsWith("/c1")) return Promise.resolve({ data: cardData({ id: "c1", name: "阿一" }) });
      return Promise.resolve({ data: cardData({ id: "c2", name: "阿二" }) });
    });
    apiPost.mockImplementation((url: string, body?: unknown) => {
      if (String(url).includes("/draft-all")) {
        if ((body as { preview?: boolean } | undefined)?.preview) {
          return Promise.resolve({ data: { prompt: RENDERED_PROMPT, sources: SOURCES, role: "配角" } });
        }
        return new Promise((r) => {
          resolveDraft = r;
        });
      }
      return Promise.resolve({ data: cardData() });
    });
    apiPatch.mockResolvedValue({ data: { rev: 2 } });

    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText("阿一");
    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-prompt-edit");
    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/draft-all", {
        character_id: "c1",
        role: undefined,
        prompt: RENDERED_PROMPT,
      }),
    );
    // 生成途中切到 B 卡
    fireEvent.click(screen.getByText("阿二"));
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith("/novels/p1/characters/c2"));
    await act(async () => {
      resolveDraft({ data: DRAFT });
    });
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
  });
});

describe("CharacterManager 起草角色：关闭在途", () => {
  it("生成中关窗：结果只缓存，不把弹窗顶回来；重开看缓存", async () => {
    let resolveDraft!: (v: { data: unknown }) => void;
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData({ name: "老周" })]) });
      }
      return Promise.resolve({ data: cardData({ name: "老周" }) });
    });
    apiPost.mockImplementation((url: string, body?: unknown) => {
      if (String(url).includes("/draft-all")) {
        if ((body as { preview?: boolean } | undefined)?.preview) {
          return Promise.resolve({
            data: { prompt: RENDERED_PROMPT, sources: SOURCES, role: "配角" },
          });
        }
        return new Promise((r) => {
          resolveDraft = r;
        });
      }
      return Promise.resolve({ data: cardData() });
    });
    apiPatch.mockResolvedValue({ data: { rev: 2 } });

    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText("老周");
    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-prompt-edit");
    fireEvent.click(screen.getByRole("button", { name: "生成" }));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2)); // preview + generate

    fireEvent.click(footerClose()); // 生成在途，作者关窗
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    await act(async () => {
      resolveDraft({ data: DRAFT });
    });
    // 迟到结果只缓存；不得把弹窗顶回来
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());

    // 重开同一行：展示缓存，不再发请求
    await act(async () => {
      await ref.current?.runAi?.("draftAll");
    });
    await screen.findByTestId("char-ai-card");
    expect(screen.getByText(/上次生成结果/)).toBeTruthy();
    expect(apiPost).toHaveBeenCalledTimes(2);
  });
});
