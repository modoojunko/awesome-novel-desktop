import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ModelSettingForm from "@/components/novel/settings/ModelSettingForm";

// tasks 7.1 / 9.1.4：本书模型面板——分组卡片 + radiogroup 键盘导航 + 选择/生效分离
const state = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock("@/hooks/useModelStatus", () => ({
  useModelStatus: () => state.current,
}));
vi.mock("@/components/novel/settings/ChangeTimeline", () => ({
  ChangeTimeline: () => <div data-testid="timeline" />,
}));
vi.mock("@/components/novel/settings/NovelUsagePanel", () => ({
  NovelUsagePanel: () => <div data-testid="usage" />,
}));

const CONFIGS = [
  {
    id: "c1",
    name: "主配置",
    vendor: "openai",
    last_test_status: "ok",
    models: ["gpt-4o", "gpt-4o-mini"],
  },
  {
    id: "c2",
    name: "备用",
    vendor: "deepseek",
    last_test_status: "auth_error",
    models: ["deepseek-chat"],
  },
];

function setState(patch: Record<string, unknown> = {}) {
  const modelOptions = CONFIGS.flatMap((c) =>
    c.models.map((m) => ({
      api_config_id: c.id,
      config_name: c.name,
      model: m,
      vendor: c.vendor,
    })),
  );
  state.current = {
    status: "configured",
    aiState: "ready",
    aiMessage: "已就绪",
    configs: CONFIGS,
    modelOptions,
    currentModel: "gpt-4o",
    currentConfigId: "c1",
    currentConfigName: "主配置",
    hasKeys: true,
    loading: false,
    error: null,
    selectModel: vi.fn().mockResolvedValue(undefined),
    addModelToConfig: vi.fn().mockResolvedValue(undefined),
    fetchCandidates: vi.fn().mockResolvedValue({ candidates: [], note: "" }),
    refresh: vi.fn(),
    refreshConfigs: vi.fn(),
    ...patch,
  };
}

const renderForm = () =>
  render(<ModelSettingForm projectId="p1" settingKey="ai-model" />);

describe("ModelSettingForm · 分组卡片 + radiogroup", () => {
  beforeEach(() => setState());

  it("按 api_config_id 分组；组头＝配置名 + 供应商 + 连接状态徽标", () => {
    const { container } = renderForm();
    const groups = container.querySelectorAll(".model-group");
    expect(groups).toHaveLength(2);
    expect(screen.getByText("主配置")).toBeTruthy();
    expect(screen.getByText("备用")).toBeTruthy();
    expect(screen.getByText("已连接")).toBeTruthy();
    expect(screen.getByText("连接失败")).toBeTruthy();
    expect(container.querySelectorAll('[role="radio"]')).toHaveLength(3);
  });

  it("radiogroup 语义：当前模型 aria-checked=true，其余 false", () => {
    const { container } = renderForm();
    expect(container.querySelector('[role="radiogroup"]')).toBeTruthy();
    const rows = [...container.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    const checked = rows.filter((r) => r.getAttribute("aria-checked") === "true");
    expect(checked).toHaveLength(1);
    expect(checked[0].dataset.model).toBe("c1::gpt-4o");
  });

  it("键盘导航：roving tabindex + 方向键环绕 + Home/End", () => {
    const { container } = renderForm();
    const rows = [...container.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    expect(rows[0].tabIndex).toBe(0);
    expect(rows[1].tabIndex).toBe(-1);

    rows[0].focus();
    fireEvent.keyDown(rows[0], { key: "ArrowDown" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(rows[1], { key: "End" });
    expect(document.activeElement).toBe(rows[2]);
    fireEvent.keyDown(rows[2], { key: "ArrowDown" }); // 环绕回首行
    expect(document.activeElement).toBe(rows[0]);
    fireEvent.keyDown(rows[0], { key: "ArrowUp" }); // 环绕到末行
    expect(document.activeElement).toBe(rows[2]);
    fireEvent.keyDown(rows[2], { key: "Home" });
    expect(document.activeElement).toBe(rows[0]);
    expect(container.querySelectorAll('[role="radio"]')).toHaveLength(3);
  });

  it("选择与生效分离：点行 0 次 PUT，点「设为本书模型」恰 1 次整对 PUT", async () => {
    const selectModel = vi.fn().mockResolvedValue(undefined);
    setState({ selectModel });
    const { container } = renderForm();

    const apply = screen.getByRole("button", { name: "设为本书模型" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);

    fireEvent.click(container.querySelector('[data-model="c2::deepseek-chat"]')!);
    expect(selectModel).not.toHaveBeenCalled(); // 只标亮
    expect(apply.disabled).toBe(false);
    expect(screen.getByText("已选：deepseek-chat")).toBeTruthy();

    fireEvent.click(apply);
    await waitFor(() => expect(selectModel).toHaveBeenCalledWith("c2", "deepseek-chat"));
    expect(selectModel).toHaveBeenCalledTimes(1);
  });

  it("400 保留 draft + 行内报错（不清空、按钮仍可用）", async () => {
    const selectModel = vi
      .fn()
      .mockRejectedValue(new Error("该模型不属于这个 API 配置的模型列表"));
    setState({ selectModel });
    const { container } = renderForm();

    fireEvent.click(container.querySelector('[data-model="c2::deepseek-chat"]')!);
    fireEvent.click(screen.getByRole("button", { name: "设为本书模型" }));

    await waitFor(() =>
      expect(screen.getByText(/该模型不属于这个 API 配置的模型列表/)).toBeTruthy(),
    );
    expect(
      container.querySelector('[data-model="c2::deepseek-chat"]')?.getAttribute("aria-checked"),
    ).toBe("true");
    expect(
      (screen.getByRole("button", { name: "设为本书模型" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("draft 变化上抛 onDirtyChange（切面板走全局 dirty 提示）", async () => {
    const onDirtyChange = vi.fn();
    const { container } = render(
      <ModelSettingForm
        projectId="p1"
        settingKey="ai-model"
        onDirtyChange={onDirtyChange}
      />,
    );
    expect(onDirtyChange).toHaveBeenLastCalledWith(false);
    fireEvent.click(container.querySelector('[data-model="c2::deepseek-chat"]')!);
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(true));
  });
});

describe("ModelSettingForm · 状态与空态", () => {
  it("ready：徽标「可用」+ 配置名 · 模型", () => {
    setState();
    const { container } = renderForm();
    expect(screen.getByText("可用")).toBeTruthy();
    expect(screen.getByText(/主配置 · gpt-4o/)).toBeTruthy();
    expect(container.querySelector(".badge.ok")).toBeTruthy();
  });

  it("missing_model：徽标「未选择」+ 引导选模型", () => {
    setState({
      aiState: "missing_model",
      aiMessage: "先在本书选择模型",
      status: "no_model",
    });
    const { container } = renderForm();
    expect(screen.getByText("未选择")).toBeTruthy();
    expect(screen.getByText(/选一个模型并点「设为本书模型」/)).toBeTruthy();
    expect(container.querySelector(".badge.empty")).toBeTruthy();
  });

  it("member_required：文案「模型已配好 · 升级 PRO 后本书 AI 即可用」（不出现「AI 就绪」）", () => {
    setState({
      aiState: "member_required",
      status: "no_key",
      aiMessage: "AI 是会员功能",
    });
    renderForm();
    expect(screen.getByText(/模型已配好 · 升级 PRO 后本书 AI 即可用/)).toBeTruthy();
    expect(screen.queryByText(/AI 就绪/)).toBeNull();
  });

  it("invalid 且无其他可用配置：给「新建配置」不死路出口（O-7）", () => {
    setState({
      aiState: "invalid",
      aiMessage: "本书绑定的模型已失效",
      status: "invalid",
      hasKeys: false,
      configs: [],
      modelOptions: [],
    });
    renderForm();
    expect(screen.getByText(/新建配置/)).toBeTruthy();
  });

  it("供应商没有模型列表时：该配置仍显示 + 候选起点 + 手动入口", async () => {
    const fetchCandidates = vi.fn().mockResolvedValue({
      candidates: ["deepseek-v4-flash", "deepseek-v4-pro"],
      note: "该端点不提供模型列表（Anthropic 兼容端点常见）",
    });
    setState({
      aiState: "missing_model",
      hasKeys: true,
      modelOptions: [],
      fetchCandidates,
      configs: [
        { id: "c9", name: "deepseek", vendor: "deepseek", last_test_status: "ok", models: [] },
      ],
    });
    const { container } = renderForm();
    // 关键回归：不能因为没有模型就把整个供应商藏起来
    expect(screen.getAllByText("deepseek").length).toBeGreaterThan(0);
    expect(container.querySelector('[data-manual="c9"]')).toBeTruthy();
    // 候选与说明是异步拉取的（不触网）
    await waitFor(() =>
      expect(screen.getByText(/该端点不提供模型列表/)).toBeTruthy(),
    );
    await waitFor(() =>
      expect(container.querySelector('[data-candidate="deepseek-v4-flash"]')).toBeTruthy(),
    );
  });

  it("点候选即添加（不必手打）", async () => {
    const addModelToConfig = vi.fn().mockResolvedValue(undefined);
    setState({
      aiState: "missing_model",
      hasKeys: true,
      modelOptions: [],
      addModelToConfig,
      fetchCandidates: vi.fn().mockResolvedValue({
        candidates: ["deepseek-v4-flash"],
        note: "n",
      }),
      configs: [
        { id: "c9", name: "deepseek", vendor: "deepseek", last_test_status: "ok", models: [] },
      ],
    });
    const { container } = renderForm();
    await waitFor(() =>
      expect(container.querySelector('[data-candidate="deepseek-v4-flash"]')).toBeTruthy(),
    );
    fireEvent.click(container.querySelector('[data-candidate="deepseek-v4-flash"]')!);
    await waitFor(() =>
      expect(addModelToConfig).toHaveBeenCalledWith("c9", "deepseek-v4-flash"),
    );
  });

  it("手动补模型：调 addModelToConfig(cid, id) 并清空输入", async () => {
    const addModelToConfig = vi.fn().mockResolvedValue(undefined);
    setState({
      aiState: "missing_model",
      hasKeys: true,
      modelOptions: [],
      addModelToConfig,
      configs: [
        { id: "c9", name: "deepseek", vendor: "deepseek", last_test_status: "ok", models: [] },
      ],
    });
    const { container } = renderForm();
    const input = container.querySelector('[data-manual="c9"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "deepseek-chat" } });
    fireEvent.click(screen.getByRole("button", { name: "添加模型" }));
    await waitFor(() =>
      expect(addModelToConfig).toHaveBeenCalledWith("c9", "deepseek-chat"),
    );
    expect(input.value).toBe("");
  });

  it("loading 态显示查询中", () => {
    setState({ loading: true });
    renderForm();
    expect(screen.getByText("查询中…")).toBeTruthy();
  });
});

describe("ModelSettingForm · 重复提交（tasks 9.4.14）", () => {
  it("双击「设为本书模型」只发 1 次 PUT", async () => {
    let resolve!: () => void;
    const pending = new Promise<void>((r) => {
      resolve = r;
    });
    const selectModel = vi.fn(() => pending);
    setState({ selectModel });
    const { container } = renderForm();

    fireEvent.click(container.querySelector('[data-model="c2::deepseek-chat"]')!);
    const apply = screen.getByRole("button", { name: "设为本书模型" });
    fireEvent.click(apply);
    fireEvent.click(apply);
    fireEvent.click(apply);
    expect(selectModel).toHaveBeenCalledTimes(1);
    resolve();
    await waitFor(() => expect(selectModel).toHaveBeenCalledTimes(1));
  });
});

describe("ModelSettingForm · 端点不提供模型列表的说明（9.1.4 补充）", () => {
  it("空模型组显示「为什么不提供 + 怎么自动获取」的完整说明", async () => {
    setState({
      aiState: "missing_model",
      hasKeys: true,
      modelOptions: [],
      fetchCandidates: vi.fn().mockResolvedValue({ candidates: [], note: "" }),
      configs: [
        { id: "c9", name: "deepseek", vendor: "deepseek", last_test_status: "ok", models: [] },
      ],
    });
    renderForm();
    expect(
      screen.getByText(/该配置没有模型列表（部分供应商不提供）——手动填模型 id/),
    ).toBeTruthy();
  });
});
