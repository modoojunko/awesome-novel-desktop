import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import ModelSettingForm from "@/components/novel/settings/ModelSettingForm";

// tasks 9.1.4：本书模型面板——ai_state 文案/徽标 + 失效无配置时的「新建配置」出口
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

function setState(patch: Record<string, unknown>) {
  state.current = {
    status: "configured",
    aiState: "ready",
    aiMessage: "已就绪",
    modelOptions: [],
    currentModel: "gpt-4o",
    currentConfigId: "c1",
    currentConfigName: "主配置",
    hasKeys: true,
    loading: false,
    error: null,
    selectModel: vi.fn(),
    refresh: vi.fn(),
    ...patch,
  };
}

describe("ModelSettingForm", () => {
  beforeEach(() => setState({}));

  it("ready：徽标「可用」+ 配置名 · 模型", () => {
    const { container } = render(<ModelSettingForm projectId="p1" settingKey="ai-model" />);
    expect(screen.getByText("可用")).toBeTruthy();
    expect(screen.getByText(/主配置 · gpt-4o/)).toBeTruthy();
    expect(container.querySelector(".badge.ok")).toBeTruthy();
  });

  it("missing_model：徽标「未选择」+ 先选模型文案", () => {
    setState({ aiState: "missing_model", aiMessage: "先在本书选择模型", status: "no_model" });
    const { container } = render(<ModelSettingForm projectId="p1" settingKey="ai-model" />);
    expect(screen.getByText("未选择")).toBeTruthy();
    expect(screen.getByText(/先在本书选择模型/)).toBeTruthy();
    expect(container.querySelector(".badge.empty")).toBeTruthy();
  });

  it("no_key：给「去配置」入口", () => {
    setState({ aiState: "no_key", aiMessage: "暂无可用 API Key", status: "no_key", hasKeys: false });
    render(<ModelSettingForm projectId="p1" settingKey="ai-model" />);
    expect(screen.getByText("去配置")).toBeTruthy();
  });

  it("invalid 且无其他可用配置：给「新建配置」不死路出口（O-7）", () => {
    setState({
      aiState: "invalid",
      aiMessage: "本书绑定的模型已失效",
      status: "invalid",
      hasKeys: false,
    });
    render(<ModelSettingForm projectId="p1" settingKey="ai-model" />);
    expect(screen.getByText(/新建配置/)).toBeTruthy();
  });

  it("loading 态显示查询中", () => {
    setState({ loading: true });
    render(<ModelSettingForm projectId="p1" settingKey="ai-model" />);
    expect(screen.getByText("查询中…")).toBeTruthy();
  });
});
