// c-chars-confirm-scope：角色面板页脚提示＝整项口径的缺口摘要（按档位），主按钮按保存模型分派。
// 手法照 SettingsView.introHandle.test.tsx：mock @/lib/api 与右栏依赖，真渲染断言。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import SettingsView from "@/components/novel/workbench/SettingsView";

const apiState = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), patch: vi.fn(),
  // 确认即前进会切到主线面板（arc）→ 该面板的读取也要有桩，否则卸载期抛未处理异常
  fetchStory: vi.fn(), updateStory: vi.fn(),
  fetchStoryArc: vi.fn(), updateStoryArc: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiState, request: vi.fn() }));

const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

vi.mock("@/lib/ai", () => ({ introAi: vi.fn(), genreAi: vi.fn(), aiBlockReason: () => null }));
vi.mock("@/hooks/useTier", () => ({
  useFeature: () => true,
  useTier: () => ({ isPro: true, isFree: false, tier: "pro" }),
}));
vi.mock("@/hooks/useModelStatus", () => ({
  useModelStatus: () => ({
    status: "configured", aiState: "ready", aiMessage: "", modelOptions: [],
    currentModel: "gpt-4o", currentConfigId: "c1", currentConfigName: "cfg",
    hasKeys: true, loading: false, error: null, selectModel: vi.fn(), refresh: vi.fn(),
  }),
}));

function card(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1", novel_id: "p1", seq: 1, code: "C-0001", name: "林拾",
    aliases: [] as string[], role: "主角", persona: "青梧宗杂役弟子。",
    dossier: {}, cog: {}, rev: 1, created_at: null, updated_at: null,
    gaps: [] as string[], relations: [],
    ...overrides,
  };
}

function stubChars(items: Record<string, unknown>[], noProtagonist = false) {
  apiState.get.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({
        data: {
          count: items.length,
          protagonist_id: noProtagonist ? null : "c1",
          gate: { ok: false, no_protagonist: noProtagonist },
          confirmed: true,
          items,
        },
      });
    }
    return Promise.resolve({ data: items[0] ?? {} });
  });
}

function renderChars(confirmed: boolean) {
  return render(
    <SettingsView
      projectId="p1"
      initialPanel="characters"
      settingsStatus={{ characters: true }}
      confirmedStatus={confirmed ? { characters: true } : {}}
      confirmSetting={vi.fn().mockResolvedValue(true)}
      novelName="残卷听澜"
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiState.post.mockResolvedValue({ data: { ok: true } });
  apiState.patch.mockResolvedValue({ data: { rev: 2 } });
  apiState.fetchStory.mockResolvedValue({ synopsis: "" });
  apiState.fetchStoryArc.mockResolvedValue({ fullstory: "", ending: {} });
});

describe("角色面板 · 页脚缺口摘要（按档位）", () => {
  it("第一次确认档：主角写全时说明只看主角 + 自动保存（note 语气，非 warn）", async () => {
    stubChars([card()]);
    const { container } = renderChars(false);

    const note = await screen.findByText(/第一次确认只看主角/);
    expect(note.textContent).toBe(
      "主角写全了——第一次确认只看主角；配角、反派后补也行，改动会自动保存",
    );
    expect(note.className).toBe("note");
    expect(container.querySelector('[data-od-id="chars-gate-hint"]')).toBeNull();
    expect(screen.getByRole("button", { name: "确认完成" })).toBeTruthy();
  });

  it("第一次确认档：主角缺人设时点名缺项（warn 常驻，点击前可见）", async () => {
    stubChars([card({ persona: "" })]);
    const { container } = renderChars(false);

    await waitFor(() =>
      expect(container.querySelector('[data-od-id="chars-gate-hint"]')?.textContent).toBe(
        "还差：主角《林拾》缺 一句话人设（第一次确认只看主角）",
      ),
    );
    expect(container.querySelector('[data-od-id="chars-gate-hint"]')?.className).toBe("warnline");
  });

  it("此后确认档：点名首张缺口卡并给张数（不是当前选中卡的卡级状态）", async () => {
    stubChars([
      card(),
      card({ id: "c2", code: "C-0002", name: "苏晚芜", role: "配角", gaps: ["能力上限", "能力代价"] }),
      card({ id: "c3", code: "C-0003", name: "银铎", role: "反派", gaps: ["剧情定位"] }),
    ]);
    const { container } = renderChars(true);

    await waitFor(() =>
      expect(container.querySelector('[data-od-id="chars-gate-hint"]')?.textContent).toBe(
        "还差：配角《苏晚芜》缺 能力上限、能力代价（共 2 张卡）",
      ),
    );
  });

  it("此后确认档无缺口：提示齐了并说明「已确认」口径", async () => {
    stubChars([card()]);
    renderChars(true);

    expect(await screen.findByText("已确认 · 改动自动保存，可随时重新确认")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新确认" })).toBeTruthy();
  });

  it("无主角卡：提示先立主角", async () => {
    stubChars([card({ id: "c9", code: "C-0009", name: "苏晚芜", role: "配角", gaps: ["剧情定位"] })], true);
    const { container } = renderChars(false);

    await waitFor(() =>
      expect(container.querySelector('[data-od-id="chars-gate-hint"]')?.textContent).toBe(
        "确认「角色」要先有一位主角——在人物卡上把谁点成主角",
      ),
    );
  });

  // 评审补丁：列表没到手时不得冒充「无主角」——回落通用提示即可（加载失败另有 toast）
  it("列表载入失败：回落通用提示，不显示「先立主角」warn", async () => {
    apiState.get.mockImplementation((url: string) => {
      if (String(url) === "/novels/p1/characters") return Promise.reject(new Error("角色列表 500"));
      return Promise.resolve({ data: {} });
    });
    const { container } = renderChars(false);

    await waitFor(() =>
      expect(container.querySelector(".panel-foot .note")?.textContent).toBe(
        "高级项可后补 · 确认即计入进度",
      ),
    );
    expect(container.querySelector('[data-od-id="chars-gate-hint"]')).toBeNull();
  });
});

describe("角色面板 · 主按钮按保存模型分派", () => {
  it("已确认态点「重新确认」：走角色门禁端点 + 回执「已重新确认」", async () => {
    stubChars([card()]);
    renderChars(true);

    fireEvent.click(await screen.findByRole("button", { name: "重新确认" }));

    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith("/novels/p1/characters/confirm", { first: false }),
    );
    await waitFor(() => expect(toastState.success).toHaveBeenCalledWith("「角色」已重新确认"));
    expect(screen.queryByRole("button", { name: "保存修改" })).toBeNull();
  });

  it("未确认态点「确认完成」：首次档（first=true）+ 计入进度", async () => {
    stubChars([card()]);
    const confirmSetting = vi.fn().mockResolvedValue(true);
    render(
      <SettingsView
        projectId="p1"
        initialPanel="characters"
        settingsStatus={{ characters: true }}
        confirmedStatus={{}}
        confirmSetting={confirmSetting}
        novelName="残卷听澜"
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "确认完成" }));

    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith("/novels/p1/characters/confirm", { first: true }),
    );
    await waitFor(() => expect(confirmSetting).toHaveBeenCalledWith("characters"));
  });
});
