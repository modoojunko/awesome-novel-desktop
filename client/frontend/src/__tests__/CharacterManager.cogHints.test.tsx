// cog-logical-levels — 认知区大白话 hint：六层层头各一句 + s5 格位一句
// （他眼里的世界/他把自己当成谁/…），帮作家理解每层写什么；一律不出现术语。
// 手法照 CharacterManager.bootstrap.test.tsx：mock @/lib/api，真渲染断言。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import CharacterManager from "@/components/novel/settings/CharacterManager";
import { COG_FIELD_HINTS, COG_LAYERS, COG_LEVEL_HINTS } from "@/lib/characterModel";

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

const BANNED = ["张力", "层次", "模型", "NLP"];

function cardData(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    novel_id: "p1",
    seq: 1,
    code: "01",
    name: "林野",
    aliases: [] as string[],
    role: "主角",
    persona: "守着灰港的夜。",
    dossier: {},
    cog: {},
    rev: 1,
    created_at: null,
    updated_at: null,
    relations: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({
        data: {
          count: 1,
          protagonist_id: "c1",
          gate: { ok: false, no_protagonist: false },
          confirmed: false,
          items: [cardData()],
        },
      });
    }
    return Promise.resolve({ data: cardData() });
  });
  apiPost.mockResolvedValue({ data: cardData() });
  apiPatch.mockResolvedValue({ data: { rev: 2 } });
});

describe("认知六层 hint（理解层次的大白话落点）", () => {
  it("六层每层都有 hint，且不含术语", () => {
    expect(Object.keys(COG_LEVEL_HINTS).sort()).toEqual(
      COG_LAYERS.map((l) => l.id).sort(),
    );
    for (const hint of Object.values(COG_LEVEL_HINTS)) {
      for (const w of BANNED) expect(hint).not.toContain(w);
      expect(hint.length).toBeGreaterThan(4);
    }
  });

  it("s5 宿命认知观：label 保持既有叫法，格位 hint 指向「他和世界的关系」且不含术语", () => {
    const s5 = COG_LAYERS.flatMap((l) => l.fields).find((f) => f.k === "s5");
    expect(s5?.label).toBe("宿命认知观");
    const hint = COG_FIELD_HINTS.s5;
    expect(hint).toBeTruthy();
    expect(hint).toContain("这个世界到底是怎么回事");
    expect(hint).toContain("注定要面对");
    for (const w of BANNED) expect(hint).not.toContain(w);
  });

  it("层头渲染六问 hint（自我观层可见「他把自己当成谁？」）", async () => {
    render(<CharacterManager projectId="p1" introReady />);
    await screen.findByText("林野");
    await waitFor(() =>
      expect(screen.getByText(COG_LEVEL_HINTS.self)).toBeTruthy(),
    );
  });

  it("展开自我观层：s5 格的 hint 就渲染在 label 下方", async () => {
    render(<CharacterManager projectId="p1" introReady />);
    await screen.findByText("林野");
    // 层头按钮的可及名含层名——点它展开该层
    fireEvent.click(screen.getByRole("button", { name: /自我观/ }));
    expect(await screen.findByText(COG_FIELD_HINTS.s5)).toBeTruthy();
  });
});
