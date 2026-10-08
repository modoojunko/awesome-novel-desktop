// c-chars-confirm-scope：整项确认缺口上抛（页脚提示的数据源）+ 卡片级保存态归位卡头。
// 手法照 CharacterManager.roleRegroup.test.tsx：mock @/lib/api，真渲染断言。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import CharacterManager, { gateHintOf, type CharGateHint } from "@/components/novel/settings/CharacterManager";

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

function card(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    novel_id: "p1",
    seq: 1,
    code: "C-0001",
    name: "林拾",
    aliases: [] as string[],
    role: "主角",
    persona: "青梧宗杂役弟子，记性过人。",
    dossier: {},
    cog: {},
    rev: 1,
    created_at: null,
    updated_at: null,
    gaps: [] as string[],
    relations: [],
    ...overrides,
  };
}

/** 列表桩：主角 林拾（无缺口）+ 配角 苏晚芜（缺能力上限/代价）+ 主角/配角双主角角标口径 */
function stubList(overrides: {
  items?: Record<string, unknown>[];
  noProtagonist?: boolean;
} = {}) {
  const items = overrides.items ?? [
    card(),
    card({ id: "c2", code: "C-0002", name: "苏晚芜", role: "配角", gaps: ["能力上限", "能力代价"] }),
  ];
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({
        data: {
          count: items.length,
          protagonist_id: overrides.noProtagonist ? null : "c1",
          gate: { ok: false, no_protagonist: !!overrides.noProtagonist },
          confirmed: true,
          items,
        },
      });
    }
    return Promise.resolve({ data: items[0] });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  apiPost.mockResolvedValue({ data: {} });
  apiPatch.mockResolvedValue({ data: { rev: 2 } });
  stubList();
});

describe("gateHintOf（纯函数）", () => {
  it("缺口卡按列表 gaps 归集，首档判据取主角名称/人设（标签来自 GATE_FIELDS）", () => {
    const hint = gateHintOf(
      [
        card({ gaps: [] }) as never,
        card({ id: "c2", name: "苏晚芜", role: "配角", gaps: ["能力上限", "能力代价"] }) as never,
      ],
      false,
    );
    expect(hint.noProtagonist).toBe(false);
    expect(hint.protagonistMissing).toEqual([]);
    expect(hint.protagonistName).toBe("林拾");
    expect(hint.gapCards).toEqual([
      { role: "配角", name: "苏晚芜", fields: ["能力上限", "能力代价"] },
    ]);
  });

  it("主角哨兵名（未命名）与空人设都计入首档缺口", () => {
    const hint = gateHintOf([card({ name: "\u0000abc", persona: "  " }) as never], false);
    expect(hint.protagonistMissing).toEqual(["角色名称", "一句话人设"]);
    expect(hint.protagonistName).toBe("");
  });

  it("无主角卡：noProtagonist 透传，首档缺口为空", () => {
    const hint = gateHintOf([card({ role: "配角" }) as never], true);
    expect(hint.noProtagonist).toBe(true);
    expect(hint.protagonistMissing).toEqual([]);
    expect(hint.protagonistName).toBe("");
  });
});

describe("CharacterManager · 整项缺口上抛与卡头保存态", () => {
  it("列表就绪即上抛缺口摘要（主角无缺口 / 配角两项）", async () => {
    const seen: (CharGateHint | null)[] = [];
    render(<CharacterManager projectId="p1" onGateHintChange={(h) => seen.push(h)} />);

    await screen.findByText("林拾");
    // 断言必须放进 waitFor：DOM 上屏先于被动 effect 的上报，直接取末项会抓到挂载期的 null
    await waitFor(() => {
      const last = seen[seen.length - 1];
      expect(last?.protagonistMissing).toEqual([]);
      expect(last?.gapCards).toEqual([
        { role: "配角", name: "苏晚芜", fields: ["能力上限", "能力代价"] },
      ]);
    });
  });

  it("无主角卡时上抛 noProtagonist（页脚提示「先立主角」的数据源）", async () => {
    stubList({
      items: [card({ id: "c9", code: "C-0009", name: "苏晚芜", role: "配角", gaps: ["剧情定位"] })],
      noProtagonist: true,
    });
    const seen: (CharGateHint | null)[] = [];
    render(<CharacterManager projectId="p1" onGateHintChange={(h) => seen.push(h)} />);

    await screen.findByText("苏晚芜");
    await waitFor(() => expect(seen[seen.length - 1]?.noProtagonist).toBe(true));
  });

  it("保存态归位卡头：带「这张卡」限定词且位于 .char-head 的 .char-side 内", async () => {
    const { container } = render(<CharacterManager projectId="p1" />);
    const chip = await screen.findByText("这张卡已自动保存");

    expect(chip.closest(".char-head")).toBeTruthy();
    expect(chip.closest(".char-side")).toBeTruthy();
    expect(container.querySelector(".char-main > div > .char-save-state")).toBeNull();
  });

  // 评审补丁：初值 gate.no_protagonist=true 是「还不知道」——列表没到手就上报，
  // 会让有主角的书在开场闪一句「要先有一位主角」，加载失败时更会常驻这句假话。
  it("列表未载入前保持静默：首报为 null，不得冒充「书里没有主角」", async () => {
    let release!: (v: unknown) => void;
    apiGet.mockImplementation((url: string) =>
      String(url) === "/novels/p1/characters"
        ? new Promise((r) => {
            release = r;
          })
        : Promise.resolve({ data: card() }),
    );
    const seen: (CharGateHint | null)[] = [];
    render(<CharacterManager projectId="p1" onGateHintChange={(h) => seen.push(h)} />);

    await waitFor(() => expect(seen.length).toBeGreaterThan(0));
    expect(seen.every((h) => h === null)).toBe(true);

    release({
      data: {
        count: 1,
        protagonist_id: "c1",
        gate: { ok: false, no_protagonist: false },
        confirmed: false,
        items: [card()],
      },
    });
    await waitFor(() => expect(seen[seen.length - 1]?.noProtagonist).toBe(false));
  });

  it("列表载入失败保持静默（页脚回落通用提示），不报「无主角」", async () => {
    apiGet.mockRejectedValue(new Error("角色列表 500"));
    const seen: (CharGateHint | null)[] = [];
    render(<CharacterManager projectId="p1" onGateHintChange={(h) => seen.push(h)} />);

    await waitFor(() => expect(seen.length).toBeGreaterThan(0));
    expect(seen.every((h) => h === null)).toBe(true);
  });
});
