// 配角/反派「一键立卡」（c-char-ai-card-generic）：右栏行门控＋采纳只补空格不建卡＋缓存重开＋卡区提示行。
// 手法照 CharacterManager.bootstrap.test.tsx：mock @/lib/api，断言端点调用序与渲染分支。
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
    protagonist_id: items.some((i) => i.role === "主角") ? (items.find((i) => i.role === "主角") as { id: string }).id : null,
    gate: { ok: false, no_protagonist: !items.some((i) => i.role === "主角") },
    confirmed: false,
    items,
  };
}

const DRAFT = {
  name: "老周",
  aliases: ["周船工"],
  persona: "渡口撑船三十年，认得每一道水纹。",
  cells: [
    { path: "dossier.look", value: "黝黑精瘦" },
    { path: "cog.v1", value: "攒钱把船换成新船" },
  ],
  skipped: [{ key: "race", why: "简介没提" }],
};

function sideCardSetup(overrides: Record<string, unknown> = {}) {
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({ data: listWith([cardData(overrides)]) });
    }
    return Promise.resolve({ data: cardData(overrides) });
  });
  apiPost.mockImplementation((url: string) => {
    if (String(url).includes("/bootstrap")) {
      return Promise.resolve({ data: DRAFT });
    }
    return Promise.resolve({ data: cardData(overrides) });
  });
  apiPatch.mockResolvedValue({ data: { rev: 2 } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CharsAiRail 一键立卡行", () => {
  const base: CharAiCtx = {
    name: "未命名",
    nameless: true,
    code: "02",
    role: "配角",
    personaGap: 1,
    dossierGap: 8,
    cogGap: 10,
  };
  const onRun = vi.fn();

  it("配角有空格：首行出现且点击分派 cardDraft", async () => {
    render(<CharsAiRail ctx={base} aiState="ready" onRun={onRun} />);
    fireEvent.click(await screen.findByText("一键立卡"));
    await waitFor(() => expect(onRun).toHaveBeenCalledWith("cardDraft"));
    expect(screen.getByText(/按简介为「未命名」把人设、档案、认知的空格一次拟齐/)).toBeTruthy();
  });

  it("反派同权：行照常出现", () => {
    render(<CharsAiRail ctx={{ ...base, role: "反派" }} aiState="ready" onRun={onRun} />);
    expect(screen.getByText("一键立卡")).toBeTruthy();
  });

  it("卡满退场：三处缺口清零后行不再出现", () => {
    const { unmount } = render(
      <CharsAiRail
        ctx={{ ...base, name: "老周", nameless: false, personaGap: 0, dossierGap: 0, cogGap: 0 }}
        aiState="ready"
        onRun={onRun}
      />,
    );
    expect(screen.queryByText("一键立卡")).toBeNull();
    unmount();
  });

  it("路人不给行", () => {
    render(<CharsAiRail ctx={{ ...base, role: "路人" }} aiState="ready" onRun={onRun} />);
    expect(screen.queryByText("一键立卡")).toBeNull();
  });

  it("主角不给行（主角走「从简介立主角」）", () => {
    render(<CharsAiRail ctx={{ ...base, role: "主角" }} aiState="ready" onRun={onRun} />);
    expect(screen.queryByText("一键立卡")).toBeNull();
    expect(screen.getByText("从简介立主角")).toBeTruthy();
  });
});

describe("CharacterManager 一键立卡", () => {
  /** 弹窗 footer 的「关闭」键（头部 X 的 aria-label 同名，取 DOM 序最后一个＝footer）。 */
  function footerClose() {
    const btns = screen.getAllByRole("button", { name: "关闭" });
    return btns[btns.length - 1];
  }

  it("出稿进弹窗（角色名进标题）→ 采纳＝只补空格、永不建卡", async () => {
    sideCardSetup();
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByTestId("char-ai-hint");
    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    await screen.findByTestId("char-ai-card");
    // 端点同一、带卡 id；标题带当前角色（哨兵名 → 「未命名」）
    expect(apiPost).toHaveBeenCalledWith("/novels/p1/settings/ai/characters/bootstrap", {
      character_id: "c1",
    });
    expect(screen.getByText("AI 拟稿 · 为「未命名」立卡（采纳才写入）")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const createCalls = apiPost.mock.calls.filter((c) => c[0] === "/novels/p1/characters");
    expect(createCalls).toHaveLength(0); // 不建卡（区别于立主角空态）
    const patched = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(patched).toContain("name");
    expect(patched).toContain("aliases");
    expect(patched).toContain("persona");
    expect(patched).toContain("dossier.look");
    expect(patched).toContain("cog.v1");
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
  });

  it("已填格不动：卡上有人设时采纳不写 persona", async () => {
    sideCardSetup({ persona: "作者自己写的人设" });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText(/作者自己写的人设/);
    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    await screen.findByTestId("char-ai-card");
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const patched = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(patched).not.toContain("persona");
    expect(patched).toContain("dossier.look");
  });

  it("缓存重开：同一行再点＝展示缓存，不再发请求（D9）", async () => {
    sideCardSetup();
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByTestId("char-ai-hint");
    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    await screen.findByTestId("char-ai-card");
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    expect(apiPost).toHaveBeenCalledTimes(1);

    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    await screen.findByTestId("char-ai-card");
    expect(screen.getByText(/上次生成结果/)).toBeTruthy();
    expect(apiPost).toHaveBeenCalledTimes(1); // 缓存命中，无新请求
  });

  it("cardDraft 稿与立主角稿互不串缓存（切换 kind＝重新出稿）", async () => {
    sideCardSetup();
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByTestId("char-ai-hint");
    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    await screen.findByTestId("char-ai-card");
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    // 同一张卡换成主角语义请求（bootstrap）——kind 不同，不走 cardDraft 缓存
    await act(async () => {
      await ref.current?.runAi?.("bootstrap");
    });
    await screen.findByTestId("char-ai-card");
    expect(screen.getByText("AI 拟稿 · 从简介立主角（采纳才写入）")).toBeTruthy();
    expect(apiPost).toHaveBeenCalledTimes(2);
  });

  it("切卡后缓存不跟人：B 卡点同行＝重新出稿，不借 A 的缓存", async () => {
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({
          data: listWith([cardData({ id: "c1", name: "阿一" }), cardData({ id: "c2", name: "阿二" })]),
        });
      }
      if (String(url).endsWith("/c1")) return Promise.resolve({ data: cardData({ id: "c1", name: "阿一" }) });
      return Promise.resolve({ data: cardData({ id: "c2", name: "阿二" }) });
    });
    apiPost.mockImplementation((url: string) => {
      if (String(url).includes("/bootstrap")) {
        return Promise.resolve({ data: DRAFT });
      }
      return Promise.resolve({ data: cardData() });
    });
    apiPatch.mockResolvedValue({ data: { rev: 2 } });
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText("阿一");
    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    await screen.findByTestId("char-ai-card");
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("char-ai-card")).toBeNull());
    expect(apiPost).toHaveBeenCalledTimes(1);

    // 切到 B 卡（loadCard 清出稿槽）→ 再点同行必须重新出稿
    fireEvent.click(screen.getByText("阿二"));
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith("/novels/p1/characters/c2"));
    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    await screen.findByTestId("char-ai-card");
    expect(apiPost).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/上次生成结果/)).toBeNull(); // 非缓存态
  });

  it("无卡上下文 cardDraft 不发请求", async () => {
    apiGet.mockImplementation(() => Promise.resolve({
      data: { count: 0, protagonist_id: null, gate: { ok: false, no_protagonist: true }, confirmed: false, items: [] },
    }));
    const ref = createRef<CharacterSaveHandle>();
    render(<CharacterManager ref={ref} projectId="p1" introReady />);
    await screen.findByText("简介里已经有主角的线索了");
    await act(async () => {
      await ref.current?.runAi?.("cardDraft");
    });
    expect(screen.queryByTestId("char-ai-card")).toBeNull();
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("卡区提示行：配角空卡出现、有人设后消失、主角不出现", async () => {
    sideCardSetup();
    const first = render(<CharacterManager projectId="p1" introReady />);
    expect(await screen.findByTestId("char-ai-hint")).toBeTruthy();
    first.unmount();

    // 卡上已有人设 → 提示行消失（不再需要指路）
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData({ persona: "已有" })]) });
      }
      return Promise.resolve({ data: cardData({ persona: "已有" }) });
    });
    const second = render(<CharacterManager projectId="p1" introReady />);
    await second.findByText(/已有/);
    await waitFor(() => expect(screen.queryByTestId("char-ai-hint")).toBeNull());
    second.unmount();

    // 主角卡不出现提示行（走空态引导/立主角链）
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: listWith([cardData({ role: "主角" })]) });
      }
      return Promise.resolve({ data: cardData({ role: "主角" }) });
    });
    render(<CharacterManager projectId="p1" introReady />);
    await screen.findByText(/一句话人设/);
    expect(screen.queryByTestId("char-ai-hint")).toBeNull();
  });
});
