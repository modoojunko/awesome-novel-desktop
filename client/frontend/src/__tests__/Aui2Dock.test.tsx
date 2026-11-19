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

describe("Aui2Dock 授权模式选择器（两层；输入框区 ModeSelect）", () => {
  /** ModeSelect 选项行常驻 DOM（CSS 收起）——按类名＋文案定位选项 pill */
  function optionEl(text: string): HTMLElement {
    const els = Array.from(
      document.querySelectorAll<HTMLElement>("[class*='sender-mode-select-option']"),
    ).filter((el) => !el.className.includes("options")); // 排除容器（容器无 onClick）
    const hit = els.find((el) => el.textContent?.includes(text));
    if (!hit) throw new Error(`选项不存在：${text}`);
    return hit;
  }
  function displayLabel(): string {
    return (
      document.querySelector("[class*='sender-mode-select-display-label']")?.textContent ?? ""
    );
  }

  it("常显当前档位；点选项切档调 setPermissionTier（allow_all 存量映射为自动档）", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(sess([], { tier: "allow_all" }));
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-authbar");
    // 存量 allow_all 映射为自动档显示（会话装载异步——放宽等待窗）
    await waitFor(() => expect(displayLabel()).toContain("自动执行·本书内"), { timeout: 3000 });
    // 点确认档选项 → 两层切档落 setPermissionTier
    fireEvent.click(optionEl("每写必确认"));
    await waitFor(
      () => expect(chatApiState.setPermissionTier).toHaveBeenCalledWith("p1", "confirm_each"),
      { timeout: 3000 },
    );
    await waitFor(() => expect(displayLabel()).toContain("每写必确认"), { timeout: 3000 });
  });

  it("切档失败回滚到上一档（显示态还原）", async () => {
    chatApiState.setPermissionTier.mockRejectedValue(new Error("网络挂了"));
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-authbar");
    await waitFor(() => expect(displayLabel()).toContain("每写必确认"), { timeout: 3000 });
    fireEvent.click(optionEl("自动执行·本书内"));
    await waitFor(() => expect(chatApiState.setPermissionTier).toHaveBeenCalled(), { timeout: 3000 });
    // 失败回滚：显示态还原确认档
    await waitFor(() => expect(displayLabel()).toContain("每写必确认"), { timeout: 3000 });
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

  it("回放去重：同签名轨迹合并为一张「同样步骤 ×N」卡（不再成排 1 步卡）", async () => {
    const readNote = "《短刃震颤引血族》（vol-1-ch-7）";
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([
        { id: "t1", role: "user", content: "第 7 章怎么样", page: "chapter" },
        { id: "t2", role: "tool", content: readNote, page: "chapter" },
        { id: "t3", role: "assistant", content: "节奏不错。", page: "chapter" },
        { id: "t4", role: "user", content: "继续", page: "chapter" },
        { id: "t5", role: "tool", content: readNote, page: "chapter" },
        { id: "t6", role: "assistant", content: "接着写。", page: "chapter" },
        { id: "t7", role: "user", content: "再看看", page: "chapter" },
        { id: "t8", role: "tool", content: readNote, page: "chapter" },
        { id: "t9", role: "assistant", content: "还是那章。", page: "chapter" },
      ]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 章节" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByText("还是那章。")).toBeTruthy());
    const traces = screen.getAllByTestId("chat-trace");
    expect(traces.length).toBe(1);
    expect(traces[0].textContent).toContain("同样步骤 ×3");
    expect(traces[0].textContent).toContain("vol-1-ch-7");
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
    // coverage 负载下 trace 卡挂载慢于 waitFor 窗口（CI 实锤）——findBy 自带重试
    const trace = await screen.findByTestId("chat-trace");
    expect(trace.textContent).toContain("我先想想主线…");
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

describe("系统提示类 gate（no_key 引导）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.stopAssistantRun.mockResolvedValue(undefined);
  });

  it("no_key gate 渲染引导语话术，SHALL NOT 渲染成空授权卡", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({
      type: "gate",
      reason: "no_key",
      message: "这本书还没绑定 AI 模型——到设定 · AI 模型配置绑一次就能开跑。",
    });
    await waitFor(() =>
      expect(screen.getByText(/这本书还没绑定 AI 模型/)).toBeTruthy(),
    );
    // 无 gateId 无 preview：不渲染授权卡（空 {} 卡是 2026-11-17 实锤回归）
    expect(screen.queryByTestId("aui2-auth-card")).toBeNull();
  });
});

describe("写授权卡（permission_required 事件）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("permission_required 事件渲染授权卡（含预览与批复按钮）", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({
      type: "permission_required",
      gateId: "g9",
      preview: { tool: "confirm_chapter", args: { chapter_ref: "vol-1-ch-7" } },
      humanOnly: false,
    });
    await screen.findByTestId("aui2-gate-approve");
    // 事件数据完整进卡（preview 可见＝作家批前看得见改什么）；点击批复链路由 e2e 钉
    // coverage 负载下渲染批次慢于按钮挂载（CI 实锤）——findBy 自带重试
    await screen.findByText(/confirm_chapter/);
    expect(screen.getByText(/vol-1-ch-7/)).toBeTruthy();
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

describe("Aui2Dock 复制对话（c-chat-copy）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.setPermissionTier.mockResolvedValue(undefined);
    chatApiState.approveGate.mockResolvedValue({ ok: true });
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it("点击复制：当前会话全量消息拼 Markdown 进剪贴板，按钮翻「已复制 ✓」", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([
        { id: "m1", role: "user", content: "帮我铺卷", page: "volume" },
        { id: "m2", role: "assistant", content: "铺好了。", page: "volume" },
      ]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByText("铺好了。")).toBeTruthy());
    fireEvent.click(screen.getByTestId("chat-copy-all"));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("**我**\n\n帮我铺卷\n\n**助手**\n\n铺好了。"),
    );
    await waitFor(() => expect(screen.getByTestId("chat-copy-all").textContent).toContain("已复制"));
    // 连点：上一轮倒计时被清掉重排（copyResetRef 分支），文案保持已复制
    fireEvent.click(screen.getByTestId("chat-copy-all"));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("chat-copy-all").textContent).toContain("已复制");
  });

  it("空会话不写剪贴板（无可用行），按钮文案不动", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    fireEvent.click(screen.getByTestId("chat-copy-all"));
    await waitFor(() => expect(screen.getByTestId("chat-copy-all").textContent).toContain("复制对话"));
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
  });

  it("剪贴板不可写静默还原（不弹错不打断），文案还原", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([{ id: "m1", role: "user", content: "帮我铺卷", page: "volume" }]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByText("帮我铺卷")).toBeTruthy());
    (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("blocked"),
    );
    fireEvent.click(screen.getByTestId("chat-copy-all"));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled());
    expect(screen.getByTestId("chat-copy-all").textContent).toContain("复制对话");
    expect(screen.getByTestId("chat-copy-all").textContent).not.toContain("已复制");
  });
});

describe("Aui2Dock tool_hint 一次性（c-agent-writing-flow-context）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.setPermissionTier.mockResolvedValue(undefined);
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("chip 触发只对紧随那条消息携带 hint；后续自由文本不重放旧工具", async () => {
    const { rerender } = render(
      <Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />,
    );
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    // 第一次：chip 触发（铺这一卷）→ tool_hint 随本次发送携带
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalledTimes(1));
    expect(chatApiState.streamAssistantChat.mock.calls[0][1]).toMatchObject({
      tool_hint: { tool: "draft_volume_expand" },
    });
    sse.done();
    await waitFor(() => expect(screen.queryByTestId("chat-stop")).toBeNull());
    // 第二次：自由文本（autoAsk 同条 onSubmit 链）→ 读走即清，旧 hint 不得重放
    rerender(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 卷纲"
        scope={SCOPE}
        autoAsk={{ seq: 1, message: "规划下一章" }}
      />,
    );
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalledTimes(2));
    const second = chatApiState.streamAssistantChat.mock.calls[1][1] as {
      message?: string;
      tool_hint?: unknown;
    };
    expect(second.message).toContain("规划下一章");
    expect(second.tool_hint).toBeUndefined();
  });
});

describe("Aui2Dock 流式缺尾复现（c-agent-narration-tail-loss）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.setPermissionTier.mockResolvedValue(undefined);
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("delta 欠覆盖时收口整段 narration 不得丢尾（生产实锤：显示缺 8 字尾）", async () => {
    const REPLY = "就一个卡点：第 7 章到底算完了没。正文 4,199 字、未归档。你说走哪条，我跟着动。";
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    // 生产几何：delta 只流到「你说走」（欠覆盖），随后整段 narration 携带完整文本
    sse.drive({ type: "narration_delta", text: REPLY.slice(0, REPLY.length - 8) });
    sse.drive({ type: "narration", text: REPLY });
    sse.drive({ type: "run_end", runId: "r1", steps: 1, toolCalls: 0, degraded: false, error: "" });
    sse.done();
    await waitFor(() =>
      expect(chatApiState.streamAssistantChat.mock.calls.length > 0).toBeTruthy(),
    );
    // 渲染面（ChatAnywhere 消息 store）应含完整叙述
    const api = (chatApiState as unknown as {
      __lastUpdate?: { content: string };
    });
    void api;
    await waitFor(() => {
      const store = (
        screen.getByTestId("aui2-dock").ownerDocument
          ? document.body.textContent
          : ""
      ) as string;
      expect(store).toContain("你说走哪条，我跟着动。");
    });
  });
});

describe("Aui2Dock 流式过覆盖对账（c-agent-narration-tail-loss）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.setPermissionTier.mockResolvedValue(undefined);
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("delta 过覆盖（哨兵前换行）时整段 narration 不重挂——文本不翻倍", async () => {
    const REPLY = "就一个卡点：第 7 章到底算完了没。你说走哪条，我跟着动。";
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    // 生产几何：delta 覆盖到哨兵前（含换行——过覆盖），整段 narration＝纯叙述
    sse.drive({ type: "narration_delta", text: REPLY + "\n" });
    sse.drive({ type: "narration", text: REPLY });
    sse.drive({ type: "run_end", runId: "r2", steps: 1, toolCalls: 0, degraded: false, error: "" });
    sse.done();
    await waitFor(() => expect(screen.queryByTestId("chat-stop")).toBeNull());
    const body = document.body.textContent || "";
    const hits = body.split("你说走哪条").length - 1;
    expect(hits).toBe(1);
  });
});

describe("Aui2Dock GateCard 字段级前后对比（c-agent-page-ops）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.setPermissionTier.mockResolvedValue(undefined);
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("preview 带 changes 时渲染字段前后人话行（旧形状走 JSON pre 分支）", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({
      type: "permission_required",
      gateId: "g9",
      preview: {
        tool: "write_chapter_fields",
        entity: "chapter:vol-1-ch-7",
        changes: [{ field: "challenge", label: "碰到的挑战", before: "旧挑战", after: "新挑战" }],
      },
      humanOnly: false,
      reason: "",
    });
    await waitFor(() => expect(screen.getByTestId("gate-preview-fields")).toBeTruthy());
    const fields = screen.getByTestId("gate-preview-fields");
    expect(fields.textContent).toContain("碰到的挑战");
    expect(fields.textContent).toContain("旧挑战");
    expect(fields.textContent).toContain("新挑战");
  });
});
