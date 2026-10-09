import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import WorldSettingPanel, {
  type WorldPanelHandle,
} from "@/components/novel/settings/world/WorldSettingPanel";

const apiGet = vi.fn();
const apiPut = vi.fn();
const worldDraftTopic = vi.fn();
const worldConsistencyCheck = vi.fn();
const toastState = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    put: (...a: unknown[]) => apiPut(...a),
  },
}));

vi.mock("@/lib/ai", () => ({
  worldDraftTopic: (...a: unknown[]) => worldDraftTopic(...a),
  worldConsistencyCheck: (...a: unknown[]) => worldConsistencyCheck(...a),
  aiBlockReason: () => null,
}));

vi.mock("@/lib/toast", () => ({ toast: toastState }));

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

/** 生成弹窗 footer 的「关闭」键（头部 X 的 aria-label 同名，取 DOM 序最后一个＝footer）。 */
function footerClose() {
  const btns = screen.getAllByRole("button", { name: "关闭" });
  return btns[btns.length - 1];
}

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
    expect(worldDraftTopic).toHaveBeenCalledWith("世界舞台", "p1", "text", "");
    const adopt = await screen.findByText("采纳 · 覆盖");
    fireEvent.click(adopt);
    expect(stage).toHaveValue("云梁界，古典王朝的修仙世界。");
    expect(onReceipt).toHaveBeenCalled();
    const receipt = onReceipt.mock.calls.at(-1)![0];
    expect(receipt.text).toContain("世界舞台");
    await act(async () => { await receipt.undo(); });
    expect(stage).toHaveValue("");
  });

  it("起草带作者底稿：输入框已敲的半稿（未保存）随请求直传（c-world-draft-input）", async () => {
    worldDraftTopic.mockResolvedValue({ value: "灵力九境……", topic: "力量体系" });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    const power = await screen.findByPlaceholderText(/灵力——修为靠功法传承/);
    fireEvent.change(power, { target: { value: "灵力分九境，金丹可毁山" } });
    await waitFor(() => expect(ref.current).not.toBeNull());
    await act(async () => { await ref.current!.runAi("power"); });
    expect(worldDraftTopic).toHaveBeenCalledWith("力量体系", "p1", "text", "灵力分九境，金丹可毁山");
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

  it("AI 生成铁律：出卡确认弹窗，采纳后追加进约束条目（按 key 去重）", async () => {
    const rows = [
      { key: "不可推翻的事", value: "死者不可复生" },
      { key: "世人不知道的事", value: "洞虚的存在" },
    ];
    worldDraftTopic.mockResolvedValue({ value: rows, topic: "constraints" });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界铁律");
    await act(async () => { await ref.current!.runAi("constraints"); });
    // 出卡：结果进弹窗（world-ai-card），采纳 · 合并写回
    expect(screen.getByTestId("world-ai-card")).toBeTruthy();
    expect(screen.getByText("AI 填 · 世界铁律")).toBeTruthy();
    fireEvent.click(screen.getByTestId("ai-card-adopt"));
    await waitFor(() => expect(screen.queryByTestId("world-ai-card")).toBeNull());
    expect(screen.getByDisplayValue("不可推翻的事")).toBeTruthy();
    expect(screen.getByDisplayValue("死者不可复生")).toBeTruthy();
    expect(screen.getByDisplayValue("世人不知道的事")).toBeTruthy();

    // 重开同一行＝展示缓存，不再发请求（D9）
    await act(async () => { await ref.current!.runAi("constraints"); });
    await waitFor(() =>
      expect(document.querySelector('[data-od-id="ai-card-cache"]')).toBeTruthy(),
    );
    expect(worldDraftTopic).toHaveBeenCalledTimes(1);

    // 「换一个」才重新生成；再采纳：已存在的铁律不重复追加
    await act(async () => { fireEvent.click(screen.getByTestId("ai-card-regen")); });
    await waitFor(() => expect(worldDraftTopic).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByTestId("ai-card-adopt"));
    await waitFor(() => expect(screen.queryByTestId("world-ai-card")).toBeNull());
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

  it("关闭即弃：打开→关闭，格值不变、无残留", async () => {
    worldDraftTopic.mockResolvedValue({ value: "云梁界的候选稿", topic: "世界舞台" });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界舞台");
    await act(async () => { await ref.current!.runAi("stage"); });
    expect(screen.getByTestId("world-ai-card")).toBeTruthy();
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("world-ai-card")).toBeNull());
    expect((document.querySelector('[data-od-id="stage-input"]') as HTMLTextAreaElement).value)
      .toBe("");
    expect(toastState.success).not.toHaveBeenCalled();
  });

  it("体检报告卡：缓存重开免请求（D9），「重新检查」重新发请求（报告卡无版数徽标——版数语义属生成卡）", async () => {
    worldConsistencyCheck.mockResolvedValue({
      items: [{ name: "历史自洽", status: "warn", note: "旧账对不上" }],
      degraded: false,
      verdict: "先补历史",
    });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界舞台");
    await act(async () => { await ref.current!.runAi("check"); });
    expect(screen.getByTestId("world-check-card")).toBeTruthy();
    // 报告卡不显示版数徽标（P2-9：版数语义属生成卡）
    expect(screen.queryByTestId("ai-card-version")).toBeNull();
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("world-check-card")).toBeNull());

    // 重开＝缓存展示，不再发请求（D9）
    await act(async () => { await ref.current!.runAi("check"); });
    await waitFor(() =>
      expect(document.querySelector('[data-od-id="ai-card-cache"]')).toBeTruthy(),
    );
    expect(screen.getByText(/上次体检结果/)).toBeTruthy();
    expect(worldConsistencyCheck).toHaveBeenCalledTimes(1);

    // 「重新检查」＝重新发请求；缓存提示条随新结果消失
    await act(async () => { fireEvent.click(screen.getByTestId("ai-card-regen")); });
    await waitFor(() => expect(worldConsistencyCheck).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(document.querySelector('[data-od-id="ai-card-cache"]')).toBeNull(),
    );
  });

  it("报告卡「AI 起草」→ 关报告卡开生成卡；采纳后自动回报告并标「（已处理）」", async () => {
    worldConsistencyCheck.mockResolvedValue({
      items: [{ name: "力量与上限", status: "warn", note: "还没写上限" }],
      degraded: false,
      verdict: "",
    });
    worldDraftTopic.mockResolvedValue({ value: "灵力九境，金丹可毁山", topic: "力量体系" });
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界舞台");
    await act(async () => { await ref.current!.runAi("check"); });
    expect(screen.getByTestId("world-check-card")).toBeTruthy();

    // 报告行内「AI 起草」→ 关报告卡、开力量生成卡
    fireEvent.click(screen.getByText("AI 起草"));
    await waitFor(() => expect(screen.getByTestId("world-ai-card")).toBeTruthy());
    await waitFor(() => expect(screen.queryByTestId("world-check-card")).toBeNull());

    // 采纳 → 写回力量格＋自动回报告卡，力量与上标记「（已处理）」
    fireEvent.click(screen.getByTestId("ai-card-adopt"));
    await waitFor(() => expect(screen.getByTestId("world-check-card")).toBeTruthy());
    expect(screen.getByTestId("world-check-card").textContent).toContain("（已处理）");
    expect((document.querySelector('[data-od-id="power-text"]') as HTMLTextAreaElement).value)
      .toBe("灵力九境，金丹可毁山");
  });

  it("现实向开关与在途生成互斥：power 生成在途时点击被拒（toast）", async () => {
    let resolveDraft: (v: { value: string }) => void = () => {};
    worldDraftTopic.mockImplementation(
      () =>
        new Promise((res) => {
          resolveDraft = res;
        }),
    );
    const ref = createRef<WorldPanelHandle>();
    render(<WorldSettingPanel projectId="p1" ref={ref} />);
    await screen.findByText("世界舞台");
    await act(async () => { void ref.current!.runAi("power"); }); // 在途不 resolve
    const sw = screen.getByRole("switch");
    fireEvent.click(sw);
    expect(toastState.info).toHaveBeenCalledWith("力量/代价正在生成——等这轮结束再切换现实向");
    expect(sw.getAttribute("aria-checked")).toBe("false");
    // 收尾放行，避免悬挂 promise
    await act(async () => { resolveDraft({ value: "灵力九境" }); });
  });
});
