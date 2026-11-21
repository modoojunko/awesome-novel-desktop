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

const modelState = vi.hoisted(() => ({
  options: [
    { api_config_id: "cfg1", config_name: "写作", model: "deepseek-flash", vendor: "deepseek" },
    { api_config_id: "cfg2", config_name: "qwen", model: "qwen-max", vendor: "qwen" },
  ],
  currentConfigId: "cfg1" as string | null,
  currentModel: "deepseek-flash" as string | null,
}));

vi.mock("@/hooks/useModelStatus", () => ({
  useModelStatus: () => ({
    modelOptions: modelState.options,
    currentConfigId: modelState.currentConfigId,
    currentModel: modelState.currentModel,
    loading: false,
  }),
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
  window.localStorage.clear();
  chatApiState.loadAssistantSession.mockResolvedValue(sess());
  chatApiState.setPermissionTier.mockResolvedValue(undefined);
  chatApiState.approveGate.mockResolvedValue({ ok: true });
});

describe("Aui2Dock 授权模式选择器（两层；输入框底栏 pill）", () => {
  /** 弹层条目（authOpen 时渲染）——按 testid 定位 */
  function menuItem(text: string): HTMLElement {
    const els = Array.from(
      document.querySelectorAll("[data-testid^='aui2-auth-item-']"),
    ) as HTMLElement[];
    const hit = els.find((el) => el.textContent?.includes(text));
    if (!hit) throw new Error(`授权选项不存在：${text}`);
    return hit;
  }
  function pill(): HTMLElement {
    return screen.getByTestId("aui2-auth-pill");
  }

  it("pill 常显当前档位（allow_all 存量映射为自动档）；点开弹层选确认档", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(sess([], { tier: "allow_all" }));
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-authbar");
    // 存量 allow_all 映射为自动档显示
    await waitFor(() => expect(pill().textContent).toContain("自动执行·本书内"), { timeout: 3000 });
    // 点开弹层 → 选确认档
    fireEvent.click(pill());
    fireEvent.click(menuItem("每写必确认"));
    await waitFor(
      () => expect(chatApiState.setPermissionTier).toHaveBeenCalledWith("p1", "confirm_each"),
      { timeout: 3000 },
    );
    await waitFor(() => expect(pill().textContent).toContain("每写必确认"), { timeout: 3000 });
  });

  it("切档失败回滚到上一档（pill 还原）", async () => {
    chatApiState.setPermissionTier.mockRejectedValue(new Error("网络挂了"));
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-authbar");
    await waitFor(() => expect(pill().textContent).toContain("每写必确认"), { timeout: 3000 });
    fireEvent.click(pill());
    fireEvent.click(menuItem("自动执行·本书内"));
    await waitFor(() => expect(chatApiState.setPermissionTier).toHaveBeenCalled(), { timeout: 3000 });
    // 失败回滚：pill 还原确认档
    await waitFor(() => expect(pill().textContent).toContain("每写必确认"), { timeout: 3000 });
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
  it("思考增量进独立思考泡泡（默认单行折叠，点开全文）；收口转「思考过程」；clear 清屏", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    // 经 conversational chip 触发一次发送（铺这一卷）
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({ type: "thinking", text: "我先想想主线…" });
    const card = await screen.findByTestId("chat-proc-thinking");
    expect(card.textContent).toContain("思考中");
    // 默认单行：全文不在 DOM，点开才出现
    expect(screen.queryByText("我先想想主线…")).toBeNull();
    fireEvent.click(screen.getByText("思考中"));
    await waitFor(() => expect(screen.getByText("我先想想主线…")).toBeTruthy());
    // 收口：标题转「思考过程」，展开态保留
    sse.done();
    await waitFor(() =>
      expect(screen.getByTestId("chat-proc-thinking").textContent).toContain("思考过程"),
    );
    // clear 事件清屏（/new 链）——消息区（过程卡与思考文本）清空；芯片行不属消息区
    sse.drive({ type: "clear" });
    await waitFor(() => expect(screen.queryByTestId("chat-proc-thinking")).toBeNull());
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

describe("Aui2Dock 工具步叙述入账（c-agent-narration-persist）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("工具步整段 narration 不重复上屏（delta 段按步重置）", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    // 生产几何：工具步叙述 delta 后跟整段 narration（落库口径），随后 step_end、
    // 下一模型步再流 delta＋收口整段——收口段不得被上一步的 delta 尾巴带偏翻倍。
    sse.drive({ type: "narration_delta", text: "第一段叙述。" });
    sse.drive({ type: "narration", text: "第一段叙述。" });
    sse.drive({
      type: "step_end",
      tool: "read_settings",
      stepId: "s-1",
      runId: "r3",
      resultNote: "（主线还没有内容）",
    });
    sse.drive({ type: "narration_delta", text: "第二段收口。" });
    sse.drive({ type: "narration", text: "第二段收口。" });
    sse.drive({ type: "run_end", runId: "r3", steps: 2, toolCalls: 1, degraded: false, error: "" });
    sse.done();
    await waitFor(() => expect(screen.queryByTestId("chat-stop")).toBeNull());
    const body = document.body.textContent || "";
    expect(body.split("第一段叙述").length - 1).toBe(1);
    expect(body.split("第二段收口").length - 1).toBe(1);
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

describe("Aui2Dock pageUnsaved 上行时效（c-agent-page-ops review P1）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiState.loadAssistantSession.mockResolvedValue(sess());
    chatApiState.setPermissionTier.mockResolvedValue(undefined);
    chatApiState.approveGate.mockResolvedValue({ ok: true });
  });

  it("pageUnsaved 变更后随下一条消息上行（旧闭包会把 dirty 快照留在装载时刻）", async () => {
    const { rerender } = render(
      <Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} pageUnsaved={[]} />,
    );
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    rerender(
      <Aui2Dock
        projectId="p1"
        page="工作台 · 卷纲"
        scope={SCOPE}
        pageUnsaved={["设定面板"]}
      />,
    );
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    const body = chatApiState.streamAssistantChat.mock.calls[0][1] as {
      page_state?: { unsaved: string[] };
    };
    expect(body.page_state?.unsaved).toEqual(["设定面板"]);
    void sse;
  });
});

describe("Aui2Dock 底栏控制条（c-agent-thinking-bubbles）", () => {
  it("默认本书模型＋思考默认开；换模型/关思考后请求带覆盖对与 thinking:false", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    // 模型 pill 默认显示本书模型；思考 pill 默认开
    expect(screen.getByTestId("ai-model-select").textContent).toContain("deepseek-flash");
    const think = screen.getByTestId("aui2-think-pill");
    expect(think.getAttribute("aria-pressed")).toBe("true");

    // 换到 qwen-max + 关思考
    fireEvent.click(screen.getByTestId("ai-model-select"));
    fireEvent.click(await screen.findByText("qwen-max"));
    fireEvent.click(think);
    expect(think.getAttribute("aria-pressed")).toBe("false");

    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    const body = chatApiState.streamAssistantChat.mock.calls[0][1] as Record<string, unknown>;
    expect(body.api_config_id).toBe("cfg2");
    expect(body.model).toBe("qwen-max");
    expect(body.thinking).toBe(false);
    void sse;
  });

  it("选回本书模型不带覆盖对；思考开关按线程记住（切回仍关）", async () => {
    const first = render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    // 先换出去再选回本书模型
    fireEvent.click(screen.getByTestId("ai-model-select"));
    fireEvent.click(await screen.findByText("qwen-max"));
    fireEvent.click(screen.getByTestId("ai-model-select"));
    fireEvent.click(await screen.findByText("deepseek-flash"));
    // 关思考（记住）
    fireEvent.click(screen.getByTestId("aui2-think-pill"));
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    const body = chatApiState.streamAssistantChat.mock.calls[0][1] as Record<string, unknown>;
    expect(body.api_config_id).toBeUndefined();
    expect(body.model).toBeUndefined();
    expect(body.thinking).toBe(false);
    void sse;

    // 重新挂载（模拟切页回来）：按线程记忆恢复关
    first.unmount();
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    await waitFor(() =>
      expect(screen.getByTestId("aui2-think-pill").getAttribute("aria-pressed")).toBe("false"),
    );
  });
});

describe("Aui2Dock 过程泡泡（思考/工具各自独立）", () => {
  it("工具调用一张单行卡；step_end 原位更新；正文不混 ● tool 行", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());

    sse.drive({ type: "step_start", stepId: "s1", tool: "read_settings", label: "先读主线" });
    const card = await screen.findByTestId("chat-proc-tool");
    expect(card.textContent).toContain("read_settings");
    expect(card.textContent).toContain("先读主线");

    sse.drive({
      type: "step_end",
      stepId: "s1",
      tool: "read_settings",
      resultNote: "主线还没写",
      ok: true,
      apiCalls: [
        { op: "assistant_step", model: "m", ms: 12, tokens_in: 1, tokens_out: 2, ok: true },
      ],
    });
    await waitFor(() =>
      expect(screen.getByTestId("chat-proc-tool").textContent).toContain("主线还没写"),
    );
    // 原位更新，不新起第二张卡
    expect(screen.getAllByTestId("chat-proc-tool").length).toBe(1);
    // 默认单行：body 的「结果」不在 DOM，点开才出现
    expect(screen.queryByText("结果")).toBeNull();
    fireEvent.click(screen.getByText("read_settings"));
    await waitFor(() => expect(screen.getByText("结果")).toBeTruthy());
    expect(screen.getByText(/1 次 · assistant_step · m/)).toBeTruthy();

    sse.drive({ type: "narration", text: "看完了。" });
    await waitFor(() => expect(screen.getByText("看完了。")).toBeTruthy());
    expect(document.body.textContent).not.toContain("● read_settings");
  });

  it("历史回放：payload.process 生成同序思考/工具卡；旧 tool 行不再叠轨迹卡", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([
        { id: "u1", role: "user", content: "看看主线", page: "ch:og" },
        {
          id: "a1",
          role: "assistant",
          content: "看完了。",
          page: "ch:og",
          payload: {
            process: [
              { kind: "thinking", text: "先看看" },
              {
                kind: "tool",
                stepId: "s1",
                tool: "read_settings",
                running: false,
                note: "主线还没写",
                ok: true,
              },
            ],
          },
        },
        { id: "t1", role: "tool", content: "read_settings ✓ — 主线还没写", page: "ch:og" },
      ]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByText("看完了。")).toBeTruthy());

    expect(screen.getByTestId("chat-proc-thinking").textContent).toContain("思考过程");
    expect(screen.getByTestId("chat-proc-tool").textContent).toContain("read_settings");
    // 新回合的过程卡替代旧轨迹卡，不重复
    expect(screen.queryByTestId("chat-trace")).toBeNull();
    // 默认折叠，点开看全文
    expect(screen.queryByText("先看看")).toBeNull();
    fireEvent.click(screen.getByText("思考过程"));
    await waitFor(() => expect(screen.getByText("先看看")).toBeTruthy());
  });
});

describe("Aui2Dock 模型选择失效回退（c-agent-thinking-bubbles）", () => {
  it("localStorage 里的历史模型已不在清单 → 显示本书模型且请求不带覆盖对", async () => {
    window.localStorage.setItem("assistant:model:p1:vol", "cfgX::gone");
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    await waitFor(() =>
      expect(screen.getByTestId("ai-model-select").textContent).toContain("deepseek-flash"),
    );
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    const body = chatApiState.streamAssistantChat.mock.calls[0][1] as Record<string, unknown>;
    expect(body.api_config_id).toBeUndefined();
    expect(body.model).toBeUndefined();
    void sse;
  });
});

describe("Aui2Dock 过程泡泡边界（失败/打断/缺省）", () => {
  it("失败步显示「没成功」；无打算/结果时不可展开", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());

    // 未先 step_start 的 step_end：补一条已完成卡；ok=false + 空 note
    sse.drive({ type: "step_end", stepId: "s1", tool: "read_settings", resultNote: "", ok: false });
    const card = await screen.findByTestId("chat-proc-tool");
    expect(card.textContent).toContain("read_settings");
    await waitFor(() => expect(card.textContent).toContain("没成功"));
    // 无详情 → 没有 body（点了也不出现「结果」）
    fireEvent.click(screen.getByText("read_settings"));
    expect(screen.queryByText("结果")).toBeNull();
  });

  it("运行中无 label 显示「正在执行…」；收口未完成标「被打断」", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());

    sse.drive({ type: "step_start", stepId: "s2", tool: "draft_volume_expand" });
    const card = await screen.findByTestId("chat-proc-tool");
    expect(card.textContent).toContain("正在执行…");
    sse.done();
    await waitFor(() => expect(screen.getByTestId("chat-proc-tool").textContent).toContain("被打断"));
  });

  it("流中断（onError）收口未完成步 → 「被打断」＋错误卡", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({ type: "step_start", stepId: "s3", tool: "read_settings" });
    await screen.findByTestId("chat-proc-tool");
    sse.fail("连接中断");
    await waitFor(() => expect(screen.getByTestId("chat-proc-tool").textContent).toContain("被打断"));
    expect(screen.getByTestId("chat-error")).toBeTruthy();
  });

  it("读类结果返回 JSON：单行头说人话，点开看原文", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({ type: "step_start", stepId: "sj", tool: "read_settings", label: "先读主线" });
    sse.drive({
      type: "step_end",
      stepId: "sj",
      tool: "read_settings",
      resultNote: '{"fullstory": "林野是夜班巡护员"}',
      ok: true,
    });
    const card = await screen.findByTestId("chat-proc-tool");
    await waitFor(() => expect(card.textContent).toContain("已读取"));
    expect(card.textContent).not.toContain("fullstory");
    fireEvent.click(screen.getByText("read_settings"));
    await waitFor(() => expect(screen.getByText(/"fullstory"/)).toBeTruthy());
  });

  it("历史 process 有 running 项 → 回放标「被打断」", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([
        { id: "u1", role: "user", content: "铺一下", page: "ch:og" },
        {
          id: "a1",
          role: "assistant",
          content: "好。",
          page: "ch:og",
          payload: {
            process: [
              { kind: "tool", stepId: "s1", tool: "draft_volume_expand", running: true },
            ],
          },
        },
      ]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByText("好。")).toBeTruthy());
    expect(screen.getByTestId("chat-proc-tool").textContent).toContain("被打断");
  });

  it("历史 process 为空/形状不对 → 不生成过程卡", async () => {
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([
        { id: "u1", role: "user", content: "看看", page: "ch:og" },
        {
          id: "a1",
          role: "assistant",
          content: "看完了。",
          page: "ch:og",
          payload: { process: [null, { kind: "thinking", text: " " }, { kind: "tool" }, { kind: "x" }] },
        },
        { id: "a2", role: "assistant", content: "还是空的。", page: "ch:og", payload: { process: [] } },
      ]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByText("还是空的。")).toBeTruthy());
    expect(screen.queryByTestId("chat-proc-thinking")).toBeNull();
    expect(screen.queryByTestId("chat-proc-tool")).toBeNull();
  });
});

describe("Aui2Dock 底栏空模型兜底", () => {
  it("没有可用模型配置 → 「未配模型」禁用 pill；本书模型不在清单 → 显示「选模型」", async () => {
    const originalOptions = modelState.options;
    try {
      modelState.options = [];
      const first = render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
      await screen.findByTestId("aui2-dock");
      expect(screen.getByText("未配模型")).toBeTruthy();
      first.unmount();

      modelState.options = originalOptions;
      modelState.currentConfigId = "cfgX";
      modelState.currentModel = "gone";
      render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
      await screen.findByTestId("aui2-dock");
      await waitFor(() =>
        expect(screen.getByTestId("ai-model-select").textContent).toContain("选模型"),
      );
    } finally {
      modelState.options = originalOptions;
      modelState.currentConfigId = "cfg1";
      modelState.currentModel = "deepseek-flash";
    }
  });
});

describe("Aui2Dock 任务计划卡（c-agent-action-contract）", () => {
  it("历史 plan 快照按最近一条恢复：四态、未完成数、计划卡唯一", async () => {
    const p1 = {
      id: "pl1",
      items: [{ id: "a", title: "主线前提", status: "done" }],
    };
    const p2 = {
      id: "pl1",
      items: [
        { id: "a", title: "主线前提", status: "done" },
        { id: "b", title: "主角陆沉", status: "active" },
        { id: "c", title: "卷一开头", status: "pending" },
        { id: "d", title: "旧版主线对照", status: "failed" },
      ],
      note: "卷一开头是正文——对话不代笔，去正文页走写作流。",
    };
    chatApiState.loadAssistantSession.mockResolvedValue(
      sess([
        { id: "u1", role: "user", content: "三件事", page: "chapter" },
        { id: "e1", role: "event", content: "", cardKind: "plan", payload: { plan: p1 }, page: "chapter" },
        { id: "e2", role: "event", content: "", cardKind: "plan", payload: { plan: p2 }, page: "chapter" },
      ]),
    );
    render(<Aui2Dock projectId="p1" page="工作台 · 章节" scope={SCOPE} />);
    await waitFor(() => expect(screen.getByTestId("chat-plan")).toBeTruthy());
    const cards = screen.getAllByTestId("chat-plan");
    expect(cards.length).toBe(1);
    const card = cards[0];
    expect(card.textContent).toContain("主角陆沉");
    expect(card.textContent).toContain("在做");
    expect(card.textContent).toContain("没做成");
    expect(card.textContent).toContain("还有 3 件没做");
    expect(card.querySelectorAll('[data-state="done"]').length).toBe(1);
    expect(card.querySelectorAll('[data-state="failed"]').length).toBe(1);
    expect(card.textContent).toContain("卷一开头是正文");
  });

  it("SSE plan 事件实时翻态；run_end 用最终快照与未完成计数", async () => {
    render(<Aui2Dock projectId="p1" page="工作台 · 卷纲" scope={SCOPE} />);
    await screen.findByTestId("aui2-dock");
    const sse = captureStream();
    fireEvent.click(screen.getByTestId("aui2-chip-draft_volume_expand"));
    await waitFor(() => expect(chatApiState.streamAssistantChat).toHaveBeenCalled());
    sse.drive({
      type: "plan",
      plan: {
        id: "pl2",
        items: [
          { id: "a", title: "主线前提", status: "done" },
          { id: "b", title: "主角陆沉", status: "active" },
        ],
      },
    });
    await waitFor(() => {
      const card = screen.getByTestId("chat-plan");
      expect(card.textContent).toContain("在做");
      expect(card.textContent).toContain("还有 1 件没做");
    });
    sse.drive({
      type: "run_end",
      plan: {
        id: "pl2",
        items: [
          { id: "a", title: "主线前提", status: "done" },
          { id: "b", title: "主角陆沉", status: "pending" },
        ],
      },
      planIncomplete: 1,
    });
    await waitFor(() => {
      const card = screen.getByTestId("chat-plan");
      expect(card.querySelectorAll('[data-state="active"]').length).toBe(0);
      expect(card.textContent).toContain("还有 1 件没做");
    });
  });
});
