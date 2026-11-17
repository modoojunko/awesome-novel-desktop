// Aui2Dock 契约测试（c-agent-chat-memory 批6）。
// 覆盖：授权芯片三档切换＋失败回滚／授权卡流内批复翻态／历史工具行折叠 trace 卡／
// 页面切换标记／clear 事件清屏／思考增量 trace 卡／产物卡渲染／崩溃兜底由宿主承担
// （AuiErrorBoundary 独立测：NovelWorkspace.test 覆盖挂载）。
// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const chatApiState = vi.hoisted(() => ({
  loadAssistantSession: vi.fn(),
  streamAssistantChat: vi.fn(),
  approveGate: vi.fn(),
  setPermissionTier: vi.fn(),
  stopAssistantRun: vi.fn(),
}));

vi.mock("@/lib/chatApi", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    loadAssistantSession: chatApiState.loadAssistantSession,
    streamAssistantChat: chatApiState.streamAssistantChat,
    approveGate: chatApiState.approveGate,
    setPermissionTier: chatApiState.setPermissionTier,
    stopAssistantRun: chatApiState.stopAssistantRun,
  };
});

import { Aui2Dock } from "@/components/novel/chat/Aui2Dock";
import type { ChatPageScope } from "@/lib/chatRegistry";

const SCOPE: ChatPageScope = {
  view: "workbench",
  chapterRef: null,
  volumeSelId: null,
  emptyBook: false,
};

function sess(messages: unknown[] = [], grants: Record<string, unknown> = { tier: "confirm_each" }) {
  return {
    sessionId: "s1",
    pageCursor: "",
    grants,
    messages: messages as never[],
  };
}

/** 捕获 SSE 回调的 stream mock：返回 abort 并暴露 drives */
function captureStream() {
  let handlers: { onEvent: (e: unknown) => void; onError: (m: string) => void; onDone: () => void } | null = null;
  chatApiState.streamAssistantChat.mockImplementation(
    (_pid: string, _body: unknown, h: never) => {
      handlers = h as never;
      return () => {};
    },
  );
  return {
    drive: (e: unknown) => handlers?.onEvent(e),
    fail: (m: string) => handlers?.onError(m),
    done: () => handlers?.onDone(),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  chatApiState.loadAssistantSession.mockResolvedValue(sess());
  chatApiState.setPermissionTier.mockResolvedValue(undefined);
  chatApiState.approveGate.mockResolvedValue({ ok: true });
});

describe("Aui2Dock 授权模式芯片", () => {
  it("常显当前档位并可下拉切换（切档调 setPermissionTier）", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(sess([], { tier: "allow_book" }));
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    const chip = await screen.findByTestId("aui2-mode-chip");
    await waitFor(() => expect(chip.textContent).toContain("本书内放行"));
    fireEvent.click(chip);
    fireEvent.click(screen.getByTestId("aui2-mode-item-confirm_each"));
    await waitFor(() =>
      expect(chatApiState.setPermissionTier).toHaveBeenCalledWith("p1", "confirm_each"),
    );
    await waitFor(() => expect(chip.textContent).toContain("每写必确认"));
  });

  it("切档失败回滚到上一档（芯片还原）", async () => {
    chatApiState.setPermissionTier.mockRejectedValue(new Error("网络挂了"));
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    const chip = await screen.findByTestId("aui2-mode-chip");
    fireEvent.click(chip);
    fireEvent.click(screen.getByTestId("aui2-mode-item-allow_all"));
    await waitFor(() => expect(chatApiState.setPermissionTier).toHaveBeenCalled());
    await waitFor(() => expect(chip.textContent).not.toContain("全部放行"));
    expect(chip.textContent).toContain("每写必确认");
  });
});

describe("Aui2Dock 历史装载与折叠", () => {
  it("user/assistant 行渲染；连续工具行折叠为一条 trace 卡；页面变化插切换标记", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([
        { id: "m1", role: "user", content: "帮我铺卷", page: "volume" },
        { id: "m2", role: "assistant", content: "铺好了。", page: "volume" },
        { id: "m3", role: "tool", content: "draft_volume_expand ✓ — 出卡", page: "volume" },
        { id: "m4", role: "tool", content: "read_outline ✓", page: "volume" },
        { id: "m5", role: "user", content: "继续", page: "chapter" },
        { id: "m6", role: "assistant", content: "好的。", page: "chapter" },
      ]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByText("铺好了。")).toBeTruthy());
    // 页面切换标记（volume → chapter）
    expect(screen.getByText("—— 切换到章节 ——")).toBeTruthy();
    // 工具行折叠：trace 卡存在且两步合并
    const trace = screen.getAllByTestId("chat-trace");
    expect(trace.length).toBe(1);
    expect(trace[0].textContent).toContain("draft_volume_expand");
    expect(trace[0].textContent).toContain("read_outline");
    expect(trace[0].textContent).toContain("运行轨迹（2 步：draft_volume_expand、read_outline）");
  });

  it("空线程给状态感知开场白（workbench 卷纲＋非空书）", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await waitFor(() =>
      expect(screen.getByText("这一卷想从哪里开始、到哪里收住？给我一句话，我来铺结构。")).toBeTruthy(),
    );
  });
});

describe("Aui2Dock 流式契约", () => {
  it("思考增量进 trace 卡（live 展开收口折叠）；产物卡渲染 CardBody；clear 清屏", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    // 经 conversational chip 触发一次发送（铺这一卷）
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({ type: "thinking", text: "我先想想主线…" });
    let trace!: HTMLElement;
    await waitFor(() => {
      trace = screen.getByTestId("chat-trace");
      expect(trace.textContent).toContain("我先想想主线…");
    });
    expect(trace.textContent).toContain("进行中");
    // 收口折叠
    sse.done();
    await waitFor(() => expect(screen.getByTestId("chat-trace").textContent).toContain("运行轨迹"));
    // clear 事件清屏（/new 链）——消息区（trace 卡与思考文本）清空；芯片行不属消息区
    sse.drive({ type: "clear" });
    await waitFor(() => expect(screen.queryByTestId("chat-trace")).toBeNull());
    expect(screen.queryByText("我先想想主线…")).toBeNull();
  });

  it("授权卡流内批复：点允许调 approveGate 并翻卡面态", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({
      type: "gate",
      gateId: "g1",
      preview: { entity: "volume:vol-1", fields: { summary: "新概要" } },
      humanOnly: false,
    });
    // coverage 负载下点击时序会抖（按钮就位≠当前帧可点）——点击进 waitFor 重试
    await waitFor(() => {
      fireEvent.click(screen.getByTestId("aui2-gate-approve"));
      expect(chatApiState.approveGate).toHaveBeenCalledWith("p1", "g1", "approved");
    });
    await waitFor(() => expect(screen.getByText(/已授权/)).toBeTruthy());
  });

  it("错误收尾上抛流式结束（保留已产出由 e2e 真浏览器钉——jsdom 不渲染 live 文本气泡）", async () => {
    const onStreamingChange = vi.fn();
    render(
      <Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} onStreamingChange={onStreamingChange} />,
    );
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({ type: "narration", text: "已产出的一段。" });
    sse.fail("模型连接失败");
    // 契约：开始 true → 终态 false（树锁定守卫依据）；过程不崩
    await waitFor(() => expect(onStreamingChange).toHaveBeenLastCalledWith(false));
    expect(onStreamingChange).toHaveBeenCalledWith(true);
  });
});

describe("AuiErrorBoundary 崩溃兜底", () => {
  // 屏蔽 React 的 error boundary 控制台报错噪音（测试自己断言 UI 态）
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("渲染异常降级为错误提示＋重试入口，重试后 children 重新挂载", async () => {
    const { AuiErrorBoundary } = await import("@/components/novel/chat/AuiErrorBoundary");
    let boom = true;
    function Child() {
      if (boom) throw new Error("渲染炸了");
      return <div data-testid="child-ok">恢复正常</div>;
    }
    render(
      <AuiErrorBoundary>
        <Child />
      </AuiErrorBoundary>,
    );
    expect(screen.getByTestId("aui2-error-boundary")).toBeTruthy();
    expect(screen.getByText(/渲染炸了/)).toBeTruthy();
    // 重试＝重置边界态（children 重新挂载→dock 历史重装载）
    boom = false;
    fireEvent.click(screen.getByTestId("aui2-error-retry"));
    await waitFor(() => expect(screen.getByTestId("child-ok")).toBeTruthy());
    expect(screen.queryByTestId("aui2-error-boundary")).toBeNull();
  });
});

describe("停止/打断（openworker 语义）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.setPermissionTier.mockResolvedValue(undefined);
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("停止钮点击走 stop 端点（协同取消主路径，不本地断流）", async () => {
    chatApiState.stopAssistantRun.mockResolvedValue(undefined);
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    const stopBtn = await screen.findByTestId("chat-stop");
    fireEvent.click(stopBtn);
    await waitFor(() =>
      expect(chatApiState.stopAssistantRun).toHaveBeenCalledWith("p1", expect.any(String)),
    );
    // 服务端协同取消 → 流收口 → 停止钮退场（本地 abort 不触发）
    sse.done();
    await waitFor(() => expect(screen.queryByTestId("chat-stop")).toBeNull());
  });
});
