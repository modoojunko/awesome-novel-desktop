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

  it("review 钉：卡片之后的事件仍落本 run 文本气泡（收口不吞、轨迹不丢）", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, { type: "step_end", runId: "r1", stepId: "s1", tool: "read_outline", resultNote: "读了" });
    state = chatReducer(state, {
      type: "artifact", runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    // 卡片在末条；其后 narration/step 必须落回 run 气泡，而不是被吞进卡片
    state = chatReducer(state, { type: "narration", runId: "r1", text: "草案在卡里，过目后采纳。" });
    state = chatReducer(state, { type: "step_end", runId: "r1", stepId: "s2", tool: "write_volume_fields", resultNote: "已写入" });
    const bubble = state.messages.find((m) => m.kind === "text" && m.role === "assistant")!;
    expect(bubble.text).toBe("草案在卡里，过目后采纳。");
    expect(bubble.steps.map((s) => s.stepId)).toEqual(["s1", "s2"]);
    const card = state.messages.find((m) => m.kind === "card")!;
    expect(card.text).toBe(""); // 卡片不被污染
  });

  it("artifact 幂等：同 cardId 不重复；同目标已有已采纳卡时新卡标 stale", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, {
      type: "artifact", runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    state = chatReducer(state, {
      type: "artifact", runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    expect(state.messages.filter((m) => m.kind === "card")).toHaveLength(1);
    state = chatReducer(state, { type: "adopt_card", cardId: "c1" });
    state = chatReducer(state, {
      type: "artifact", runId: "r1", cardId: "c2", kind: "text",
      payload: { draft: { name: "卷一v2" }, vol_no: 1 },
    });
    const cards = state.messages.filter((m) => m.kind === "card");
    expect(cards[0].cardStatus).toBe("adopted"); // 旧卡保留已采纳徽标
    expect(cards[1].cardStatus).toBe("stale");
    // stale 卡可再采纳（walkthrough B2「再采纳第二版」＝替换写回）
    state = chatReducer(state, { type: "adopt_card", cardId: "c2" });
    expect(cards[0].cardStatus).toBe("adopted");
    expect(state.messages.filter((m) => m.kind === "card")[1].cardStatus).toBe("adopted");
  });

  it("review 钉：stale 只判同目标——不同卷的新卡照常 draft 可采纳", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, {
      type: "artifact", runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    state = chatReducer(state, { type: "adopt_card", cardId: "c1" });
    state = chatReducer(state, {
      type: "artifact", runId: "r1", cardId: "c2", kind: "text",
      payload: { draft: { name: "卷二" }, vol_no: 2 },
    });
    expect(state.messages.filter((m) => m.kind === "card")[1].cardStatus).toBe("draft");
    // 体检报告（不可采纳卡种）也不受已采纳卷纲影响
    state = chatReducer(state, { type: "artifact", runId: "r1", cardId: "c3", kind: "report", payload: { report: [] } });
    expect(state.messages.filter((m) => m.kind === "card")[2].cardStatus).toBe("draft");
  });

  it("thinking_flush 整段替换（节流通道：ref 攒量、低频刷入 state）", () => {
    state = chatReducer(state, { type: "run_start", runId: "r1" });
    state = chatReducer(state, { type: "thinking", text: "直连增量仍可用" });
    state = chatReducer(state, { type: "thinking_flush", text: "先读设定\n再起草" });
    expect(state.thinkingText).toBe("先读设定\n再起草");
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
