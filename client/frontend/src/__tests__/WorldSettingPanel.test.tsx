import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import WorldSettingPanel, {
  type WorldPanelHandle,
} from "@/components/novel/settings/world/WorldSettingPanel";
import { recordLoreSuggestions } from "@/lib/loreSuggestions";

const apiGet = vi.fn();
const apiPut = vi.fn();
const worldDraftTopic = vi.fn();
const worldConsistencyCheck = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    put: (...a: unknown[]) => apiPut(...a),
  },
}));

const worldLoreApply = vi.fn();
vi.mock("@/lib/ai", () => ({
  worldDraftTopic: (...a: unknown[]) => worldDraftTopic(...a),
  worldConsistencyCheck: (...a: unknown[]) => worldConsistencyCheck(...a),
  worldLoreApply: (...a: unknown[]) => worldLoreApply(...a),
  aiBlockReason: () => null,
}));

const EMPTY = {
  no_power: false, stage: "", power: "", cost: "",
  history: [], factions: [], constraints: [], extra: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation((url: string) => {
    if (String(url).includes("settings/genre"))
      return Promise.resolve({ theme: "仙侠/修真", sub_genre: "凡人流" });
    return Promise.resolve(EMPTY);
  });
  apiPut.mockResolvedValue({ ok: true });
});

describe("WorldSettingPanel", () => {
  it("渲染五格与题材继承条", async () => {
    render(<WorldSettingPanel projectId="p1" />);
    for (const name of ["世界舞台", "力量体系", "力量的代价", "势力", "世界铁律"]) {
      expect(await screen.findByText(name)).toBeTruthy();
    }
    await waitFor(() => expect(screen.getByText(/舞台底色＝/)).toBeTruthy());
  });

  it("现实向开关收起力量格并记 dirty", async () => {
    const onDirty = vi.fn();
    render(<WorldSettingPanel projectId="p1" onDirtyChange={onDirty} />);
    const btn = await screen.findByRole("switch");
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-checked")).toBe("true");
    expect(screen.queryByPlaceholderText(/灵力——修为靠功法传承/)).toBeNull();
    expect(onDirty).toHaveBeenCalledWith(true);
  });

  it("铁律名目建议点选即加一条", async () => {
    render(<WorldSettingPanel projectId="p1" />);
    await screen.findByText("世界铁律");
    fireEvent.click(screen.getByText("能力上限"));
    expect(screen.getByDisplayValue("能力上限")).toBeTruthy();
  });

  it("AI 采纳：写回控件 + 脚部回执 + 一步撤销", async () => {
    worldDraftTopic.mockResolvedValue({ value: "云梁界，古典王朝的修仙世界。", topic: "世界舞台" });
    const onReceipt = vi.fn();
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} onReceiptChange={onReceipt} />);
    const stage = await screen.findByPlaceholderText(/云梁界，古典王朝的修仙世界/);
    await waitFor(() => expect(ref.current).not.toBeNull());
    await ref.current!.runAi("stage");
    expect(worldDraftTopic).toHaveBeenCalledWith("世界舞台", "p1", "text");
    const adopt = await screen.findByText("采纳 · 覆盖");
    fireEvent.click(adopt);
    expect(stage).toHaveValue("云梁界，古典王朝的修仙世界。");
    expect(onReceipt).toHaveBeenCalled();
    const receipt = onReceipt.mock.calls.at(-1)![0];
    expect(receipt.text).toContain("世界舞台");
    await act(async () => { await receipt.undo(); });
    expect(stage).toHaveValue("");
  });

  it("一致性体检：结果渲染 + 去哪补 + AI 起草入口", async () => {
    worldConsistencyCheck.mockResolvedValue({
      items: [
        { name: "代价与边界", status: "warn", note: "还没写代价" },
        { name: "简介 × 世界", status: "miss", note: "简介没写" },
      ],
      degraded: true, degraded_reasons: ["简介未填"], verdict: "补上代价再确认",
    });
    const onGotoPanel = vi.fn();
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} onGotoPanel={onGotoPanel} />);
    await waitFor(() => expect(ref.current).not.toBeNull());
    await act(async () => { await ref.current!.runAi("check"); });
    expect(screen.getByText("代价与边界")).toBeTruthy();
    expect(screen.getByText("风险")).toBeTruthy();
    expect(screen.getByText("03 力量的代价")).toBeTruthy();
    expect(screen.getByText(/AI 起草/)).toBeTruthy();
    // 简介缺口不在世界页：跳转出口而非 AI 起草
    fireEvent.click(screen.getByText("去补简介"));
    expect(onGotoPanel).toHaveBeenCalledWith("intro");
  });

  it("lore 建议：挂载即显示，采纳入账后清掉本条", async () => {
    worldLoreApply.mockResolvedValue({});
    recordLoreSuggestions("p1", "vol-1-ch-1", [
      { key: "血衣楼", value: "第12章登场的新势力", set: "extra" },
    ]);
    render(<WorldSettingPanel projectId="p1" />);
    expect(await screen.findByText(/血衣楼/)).toBeTruthy();
    fireEvent.click(screen.getByText("采纳入账"));
    await waitFor(() => expect(worldLoreApply).toHaveBeenCalled());
    expect(screen.queryByText(/采纳入账/)).toBeNull();
  });

  it("save：lore 写入的 origin 不被整包保存抹掉", async () => {
    apiGet.mockImplementation((url: string) => {
      if (String(url).includes("settings/genre"))
        return Promise.resolve({ theme: "仙侠/修真", sub_genre: "凡人流" });
      return Promise.resolve({
        ...EMPTY,
        history: [{ key: "丹阁大火", value: "三十年前", origin: "vol-1-ch-3" }],
      });
    });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界铁律");
    await ref.current!.save();
    const [, body] = apiPut.mock.calls[0];
    expect(body.history[0]).toMatchObject({ key: "丹阁大火", origin: "vol-1-ch-3" });
  });

  it("AI 生成铁律：采纳后追加进约束条目（按 key 去重）", async () => {
    const rows = [
      { key: "不可推翻的事", value: "死者不可复生" },
      { key: "世人不知道的事", value: "洞虚的存在" },
    ];
    worldDraftTopic.mockResolvedValue({ value: rows, topic: "constraints" });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界铁律");
    await act(async () => { await ref.current!.runAi("constraints"); });
    const sink = screen.getByText(/AI 填 · 世界铁律/).closest(".ai-sink")!;
    await waitFor(() => expect(sink.querySelector(".ans-act button.primary")).toBeTruthy());
    fireEvent.click(sink.querySelector(".ans-act button.primary")!);
    expect(screen.getByDisplayValue("不可推翻的事")).toBeTruthy();
    expect(screen.getByDisplayValue("死者不可复生")).toBeTruthy();
    expect(screen.getByDisplayValue("世人不知道的事")).toBeTruthy();

    // 已存在的铁律不重复追加
    await act(async () => { await ref.current!.runAi("constraints"); });
    const sink2 = screen.getByText(/AI 填 · 世界铁律/).closest(".ai-sink")!;
    await waitFor(() => expect(sink2.querySelector(".ans-act button.primary")).toBeTruthy());
    fireEvent.click(sink2.querySelector(".ans-act button.primary")!);
    expect(screen.getAllByDisplayValue("不可推翻的事")).toHaveLength(1);
    expect(screen.getAllByDisplayValue("死者不可复生")).toHaveLength(1);
  });

  it("历史与旧账：建议名目加一条", async () => {
    render(<WorldSettingPanel projectId="p1" />);
    await screen.findByText("历史与旧账");
    fireEvent.click(screen.getByText("大战与灾变"));
    expect(screen.getAllByDisplayValue("大战与灾变").length).toBeGreaterThan(0);
  });

  it("save：PUT 契约 v2 并过滤空条目", async () => {
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界铁律");
    await ref.current!.save();
    expect(apiPut).toHaveBeenCalledTimes(1);
    const [url, body] = apiPut.mock.calls[0];
    expect(String(url)).toContain("/settings/world");
    expect(body.no_power).toBe(false);
    expect(body.history).toEqual([]);
    expect(body.constraints).toEqual([]);
  });
});

  it("sink 生成历史只保留最近 5 次", async () => {
    worldDraftTopic.mockResolvedValue({ value: "草稿", topic: "世界舞台" });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界舞台");
    for (let i = 0; i < 7; i++) {
      await act(async () => { await ref.current!.runAi("stage"); });
    }
    const sink = screen.getByText(/AI 填 · 世界舞台/).closest(".ai-sink")!;
    expect(sink.querySelectorAll(".ah-chip")).toHaveLength(5);
    expect(sink.textContent).toContain("只保留最近 5 次");
  });
