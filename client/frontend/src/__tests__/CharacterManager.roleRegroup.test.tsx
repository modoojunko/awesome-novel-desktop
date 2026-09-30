// 人物卡保存后角色树同步：单格自动保存（含身份/名字）落库成功即重取列表，
// 作家不再需要整页刷新才看到「配角 → 反派」的归组与行名变化。
// 手法照 CharacterManager.cogHints.test.tsx：mock @/lib/api，真渲染断言。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import CharacterManager from "@/components/novel/settings/CharacterManager";

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

/** 服务端已落库的身份/名字：PATCH 成功后变，后续 GET（列表+单卡）都返回新值 */
let savedRole = "配角";
let savedName = "林二";

function cardData(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    novel_id: "p1",
    seq: 1,
    code: "01",
    name: savedName,
    aliases: [] as string[],
    role: savedRole,
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

beforeEach(() => {
  vi.clearAllMocks();
  savedRole = "配角";
  savedName = "林二";
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({
        data: {
          count: 1,
          protagonist_id: null,
          gate: { ok: false, no_protagonist: true },
          confirmed: false,
          items: [cardData()],
        },
      });
    }
    return Promise.resolve({ data: cardData() });
  });
  apiPost.mockResolvedValue({ data: cardData() });
  apiPatch.mockImplementation((_url: unknown, body: { path: string; value: unknown }) => {
    const b = body as { path: string; value: unknown };
    if (b.path === "role") savedRole = String(b.value);
    if (b.path === "name") savedName = String(b.value);
    return Promise.resolve({ data: { rev: 2 } });
  });
});

function groupOf(role: string): HTMLElement {
  const head = screen.getByText(role, { selector: ".char-group-head .nm" });
  return head.closest(".char-group") as HTMLElement;
}

describe("人物卡保存后角色树刷新", () => {
  it("身份从配角改成反派：落库后行归入反派组、配角组清零，无需整页刷新", async () => {
    render(<CharacterManager projectId="p1" />);
    await screen.findByText("林二");
    expect(groupOf("配角").textContent).toContain("林二");
    expect(groupOf("反派").textContent).not.toContain("林二");

    fireEvent.click(screen.getByRole("button", { name: "反派" }));

    await waitFor(
      () => {
        expect(groupOf("反派").textContent).toContain("林二");
        expect(groupOf("配角").textContent).not.toContain("林二");
      },
      { timeout: 3000 },
    );
    const listCalls = apiGet.mock.calls.filter((c) => String(c[0]) === "/novels/p1/characters");
    expect(listCalls.length).toBeGreaterThanOrEqual(2); // 首载 + 落库后同步
  });

  it("改名同理：保存后左侧行名同步成新名字", async () => {
    render(<CharacterManager projectId="p1" />);
    await screen.findByText("林二");
    fireEvent.change(screen.getByRole("textbox", { name: "角色名称" }), {
      target: { value: "林奇" },
    });
    await waitFor(
      () => {
        expect(groupOf("配角").textContent).toContain("林奇");
        expect(groupOf("配角").textContent).not.toContain("林二");
      },
      { timeout: 3000 },
    );
  });
});
