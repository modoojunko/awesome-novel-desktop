// 角色面板首进引导 + 「从简介立主角」（character-bootstrap-from-intro）行为测试。
// 手法照 WorldSettingPanel.test.tsx：mock @/lib/api，断言端点调用序与渲染分支。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import CharacterManager, {
  type CharacterSaveHandle,
} from "@/components/novel/settings/CharacterManager";
import { CharsAiRail } from "@/components/novel/settings/AiWriterAssistant";
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

describe("CharacterManager 从简介立主角", () => {
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

  it("空态出稿→采纳＝建主角卡＋逐格补写", async () => {
    apiPost.mockImplementation((url: string, body?: unknown) => {
      if (String(url) === "/novels/p1/settings/ai/characters/bootstrap") {
        return Promise.resolve({ data: DRAFT });
      }
      return Promise.resolve({ data: cardData({ name: String((body as { name?: string })?.name ?? "") }) });
    });
    apiGet.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") {
        return Promise.resolve({ data: emptyList() });
      }
      return Promise.resolve({ data: cardData({ name: "林拾", persona: "扫了十年落叶的杂役弟子。" }) });
    });
    const onCtx = vi.fn();
    render(<CharacterManager projectId="p1" introReady onCtxChange={onCtx} />);
    fireEvent.click(await screen.findByRole("button", { name: "从简介立主角" }));
    // 出稿预览：名称/别名/人设都先过目
    expect(await screen.findByText("AI 拟稿 · 采纳才写入")).toBeTruthy();
    expect(screen.getByText("林拾")).toBeTruthy();
    expect(screen.getByText("拾哥")).toBeTruthy();
    expect(screen.getByText(/扫了十年落叶/)).toBeTruthy();
    // 采纳：create(主角) → aliases/persona/cells 逐格 PATCH（走既有单格写入）
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const createCall = apiPost.mock.calls.find((c) => c[0] === "/novels/p1/characters");
    expect(createCall?.[1]).toEqual({ name: "林拾", role: "主角" });
    const patched = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(patched).toEqual(["aliases", "persona", "dossier.race", "cog.w5"]);
  });

  it("主角待立：采纳只补空格（名字/别名/人设为空才写）", async () => {
    apiPost.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/settings/ai/characters/bootstrap") {
        return Promise.resolve({
          data: { ...DRAFT, cells: [{ path: "dossier.race", value: "人族" }] },
        });
      }
      return Promise.resolve({ data: cardData() });
    });
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
    await screen.findByText("AI 拟稿 · 采纳才写入");
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

  it("AI 门控未就绪：空态按钮点击走 onBlocked、不发请求", async () => {
    const blocked = vi.fn();
    render(<CharacterManager projectId="p1" introReady aiState="no_key" onBlocked={blocked} />);
    fireEvent.click(await screen.findByRole("button", { name: "从简介立主角" }));
    await waitFor(() => expect(blocked).toHaveBeenCalledWith("no_key"));
    expect(apiPost).not.toHaveBeenCalled();
  });
});

describe("CharsAiRail 从简介立主角行", () => {
  const base: CharAiCtx = {
    name: "未命名",
    nameless: true,
    code: "01",
    role: "主角",
    personaGap: 1,
    dossierGap: 6,
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
