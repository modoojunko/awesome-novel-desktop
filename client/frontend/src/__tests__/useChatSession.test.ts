import { beforeEach, describe, expect, it } from "vitest";
import { chatReducer, type ChatState } from "@/hooks/useChatSession";

function fresh(): ChatState {
  return { messages: [], runActive: false, thinkingText: "", error: "" };
}

describe("useChatSession reducer（run 模型）", () => {
  let state: ChatState;
  beforeEach(() => {
    state = fresh();
  });

  it("user_send 入列并清错误", () => {
    state = chatReducer({ ...state, error: "旧的" }, { type: "user_send", id: "s1", text: "你好", page: "volume" });
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].role).toBe("user");
    expect(state.error).toBe("");
  });

  it("run_start 建 assistant 占位并置流式；run_end 收", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    expect(state.runActive).toBe(true);
    expect(state.messages.at(-1)?.role).toBe("assistant");
    state = chatReducer(state, { type: "run_end" });
    expect(state.runActive).toBe(false);
  });

  it("thinking 增量累积", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, { type: "thinking", text: "先读" });
    state = chatReducer(state, { type: "thinking", text: "主线" });
    expect(state.thinkingText).toBe("先读主线");
  });

  it("step 乱序容错：step_end 先到也收敛同一 stepId", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, {
      type: "step_end", runId: "r1", stepId: "s-2", tool: "read_progress", resultNote: "第1章待写",
    });
    const m = state.messages.at(-1)!;
    expect(m.steps).toEqual([{ stepId: "s-2", tool: "read_progress", resultNote: "第1章待写" }]);
    // 后补的 step_start 同 id 不重复
    state = chatReducer(state, { type: "step_start", runId: "r1", stepId: "s-2", tool: "read_progress" });
    expect(state.messages.at(-1)!.steps).toHaveLength(1);
  });

  it("narration 追加到末条 assistant", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, { type: "narration", runId: "r1", text: "第一段" });
    state = chatReducer(state, { type: "narration", runId: "r1", text: "第二段" });
    expect(state.messages.at(-1)!.text).toBe("第一段\n第二段");
  });

  it("artifact 幂等：同 cardId 不重复；已有已采纳卡时新卡标 stale", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, { type: "artifact", runId: "r1", cardId: "c1", kind: "text", payload: { a: 1 } });
    state = chatReducer(state, { type: "artifact", runId: "r1", cardId: "c1", kind: "text", payload: { a: 1 } });
    expect(state.messages.filter((m) => m.kind === "card")).toHaveLength(1);
    state = chatReducer(state, { type: "adopt_card", cardId: "c1" });
    state = chatReducer(state, { type: "artifact", runId: "r1", cardId: "c2", kind: "text", payload: { a: 2 } });
    const cards = state.messages.filter((m) => m.kind === "card");
    expect(cards[0].cardStatus).toBe("adopted");
    expect(cards[1].cardStatus).toBe("stale");
  });

  it("授权卡：pending → resolved 只改同一 gateId", () => {
    state = chatReducer(state, {
      type: "permission_required", runId: "r1", gateId: "g1", preview: { tool: "write_volume_fields" }, humanOnly: false,
    });
    state = chatReducer(state, {
      type: "permission_required", runId: "r1", gateId: "g2", preview: {}, humanOnly: true,
    });
    state = chatReducer(state, { type: "gate_resolved", gateId: "g1", approved: true });
    const g1 = state.messages.find((m) => m.gateId === "g1")!;
    const g2 = state.messages.find((m) => m.gateId === "g2")!;
    expect(g1.gateState).toBe("approved");
    expect(g2.gateState).toBe("pending");
  });

  it("error 落一条错误消息（不重复堆叠）且停止流式", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, { type: "error", message: "断流" });
    state = chatReducer(state, { type: "error", message: "断流" });
    expect(state.messages.filter((m) => m.kind === "error")).toHaveLength(1);
    expect(state.runActive).toBe(false);
  });

  it("load_history 换入历史；reset 清空", () => {
    state = chatReducer(state, {
      type: "load_history",
      messages: [{ id: "h1", role: "user", kind: "text", text: "历史", steps: [] }],
    });
    expect(state.messages).toHaveLength(1);
    state = chatReducer(state, { type: "reset" });
    expect(state.messages).toHaveLength(0);
  });
});
