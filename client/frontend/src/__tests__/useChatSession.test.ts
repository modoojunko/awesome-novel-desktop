import { beforeEach, describe, expect, it } from "vitest";
import { chatReducer, type ChatState } from "@/hooks/useChatSession";

const T1 = "ch:og";
const T2 = "ch:prose";

function fresh(): ChatState {
  return { threads: {}, activeThread: T1, runActive: false, thinkingText: "", error: "" };
}

/** 便捷取桶（默认章纲线程）。 */
function bucket(state: ChatState, t = T1) {
  return state.threads[t] ?? [];
}

describe("useChatSession reducer（线程化 run 模型）", () => {
  let state: ChatState;
  beforeEach(() => {
    state = fresh();
  });

  it("user_send 入列并清错误（落发起线程）", () => {
    state = chatReducer({ ...state, error: "旧的" }, { type: "user_send", thread: T1, id: "s1", text: "你好", page: "volume" });
    expect(bucket(state)).toHaveLength(1);
    expect(bucket(state)[0].role).toBe("user");
    expect(state.error).toBe("");
  });

  it("run_start 建 assistant 占位并置流式；run_end 收", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    expect(state.runActive).toBe(true);
    expect(bucket(state).at(-1)?.role).toBe("assistant");
    state = chatReducer(state, { type: "run_end", thread: T1 });
    expect(state.runActive).toBe(false);
  });

  it("线程隔离钉（boss 拍板 2026-11-15）：两线程各聊各的，互不串桶", () => {
    state = chatReducer(state, { type: "user_send", thread: T1, id: "a1", text: "章纲话题", page: "og" });
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, { type: "narration", thread: T1, runId: "r1", text: "章纲回复" });
    // 切到正文线程发消息
    state = chatReducer(state, { type: "user_send", thread: T2, id: "b1", text: "正文话题", page: "prose" });
    expect(bucket(state, T2)).toHaveLength(1);
    expect(bucket(state, T2)[0].text).toBe("正文话题");
    // 章纲线程原样保留（切回接续；narration 并入 run 气泡）
    expect(bucket(state, T1)).toHaveLength(2);
    expect(bucket(state, T1).at(-1)?.text).toBe("章纲回复");
    // 正文线程没有章纲的内容
    expect(bucket(state, T2).some((m) => m.text === "章纲回复")).toBe(false);
  });

  it("thinking 增量累积", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, { type: "thinking", text: "先读" });
    state = chatReducer(state, { type: "thinking", text: "主线" });
    expect(state.thinkingText).toBe("先读主线");
  });

  it("step 乱序容错：step_end 先到也收敛同一 stepId", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, {
      type: "step_end", thread: T1, runId: "r1", stepId: "s-2", tool: "read_progress", resultNote: "第1章待写",
    });
    const m = bucket(state).at(-1)!;
    expect(m.steps).toEqual([{ stepId: "s-2", tool: "read_progress", resultNote: "第1章待写" }]);
    // 后补的 step_start 同 id 不重复
    state = chatReducer(state, { type: "step_start", thread: T1, runId: "r1", stepId: "s-2", tool: "read_progress" });
    expect(bucket(state).at(-1)!.steps).toHaveLength(1);
  });

  it("narration 追加到本 run 气泡", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, { type: "narration", thread: T1, runId: "r1", text: "第一段" });
    state = chatReducer(state, { type: "narration", thread: T1, runId: "r1", text: "第二段" });
    expect(bucket(state).at(-1)!.text).toBe("第一段\n第二段");
  });

  it("review 钉：卡片之后的事件仍落本 run 文本气泡（收口不吞、轨迹不丢）", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, { type: "step_end", thread: T1, runId: "r1", stepId: "s1", tool: "read_outline", resultNote: "读了" });
    state = chatReducer(state, {
      type: "artifact", thread: T1, runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    // 卡片在末条；其后 narration/step 必须落回 run 气泡，而不是被吞进卡片
    state = chatReducer(state, { type: "narration", thread: T1, runId: "r1", text: "草案在卡里，过目后采纳。" });
    state = chatReducer(state, { type: "step_end", thread: T1, runId: "r1", stepId: "s2", tool: "write_volume_fields", resultNote: "已写入" });
    const bubble = bucket(state).find((m) => m.kind === "text" && m.role === "assistant")!;
    expect(bubble.text).toBe("草案在卡里，过目后采纳。");
    expect(bubble.steps.map((s) => s.stepId)).toEqual(["s1", "s2"]);
    const card = bucket(state).find((m) => m.kind === "card")!;
    expect(card.text).toBe(""); // 卡片不被污染
  });

  it("artifact 幂等：同 cardId 不重复；同目标已有已采纳卡时新卡标 stale", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, {
      type: "artifact", thread: T1, runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    state = chatReducer(state, {
      type: "artifact", thread: T1, runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    expect(bucket(state).filter((m) => m.kind === "card")).toHaveLength(1);
    state = chatReducer(state, { type: "adopt_card", cardId: "c1" });
    state = chatReducer(state, {
      type: "artifact", thread: T1, runId: "r1", cardId: "c2", kind: "text",
      payload: { draft: { name: "卷一v2" }, vol_no: 1 },
    });
    const cards = bucket(state).filter((m) => m.kind === "card");
    expect(cards[0].cardStatus).toBe("adopted"); // 旧卡保留已采纳徽标
    expect(cards[1].cardStatus).toBe("stale");
    // stale 卡可再采纳（walkthrough B2「再采纳第二版」＝替换写回）
    state = chatReducer(state, { type: "adopt_card", cardId: "c2" });
    expect(bucket(state).filter((m) => m.kind === "card")[1].cardStatus).toBe("adopted");
  });

  it("review 钉：stale 只判同目标——不同卷的新卡照常 draft 可采纳", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, {
      type: "artifact", thread: T1, runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    state = chatReducer(state, { type: "adopt_card", cardId: "c1" });
    state = chatReducer(state, {
      type: "artifact", thread: T1, runId: "r1", cardId: "c2", kind: "text",
      payload: { draft: { name: "卷二" }, vol_no: 2 },
    });
    expect(bucket(state).filter((m) => m.kind === "card")[1].cardStatus).toBe("draft");
    // 体检报告（不可采纳卡种）也不受已采纳卷纲影响
    state = chatReducer(state, { type: "artifact", thread: T1, runId: "r1", cardId: "c3", kind: "report", payload: { report: [] } });
    expect(bucket(state).filter((m) => m.kind === "card")[2].cardStatus).toBe("draft");
  });

  it("thinking_flush 整段替换（节流通道：ref 攒量、低频刷入 state）", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, { type: "thinking", text: "直连增量仍可用" });
    state = chatReducer(state, { type: "thinking_flush", text: "先读设定\n再起草" });
    expect(state.thinkingText).toBe("先读设定\n再起草");
  });

  it("run_end 思考回挂发起线程的本 run 气泡（收口后可回看，实时面板清零）", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, { type: "thinking_flush", text: "先读设定，再起草" });
    state = chatReducer(state, { type: "run_end", thread: T1 });
    expect(state.runActive).toBe(false);
    expect(state.thinkingText).toBe("");
    const bubble = bucket(state).find((m) => m.kind === "text" && m.role === "assistant")!;
    expect(bubble.thinking).toBe("先读设定，再起草");
  });

  it("step_end 透传 apiCalls（模型调用随步可见）", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    const apiCalls = [{ op: "draft_expand", model: "glm-5.3", ms: 820, ok: true }];
    state = chatReducer(state, {
      type: "step_end", thread: T1, runId: "r1", stepId: "s1", tool: "draft_volume_expand",
      resultNote: "出卡", apiCalls,
    });
    expect(bucket(state).at(-1)!.steps[0].apiCalls).toEqual(apiCalls);
  });

  it("授权卡：pending → resolved 只改同一 gateId（跨线程可达）", () => {
    state = chatReducer(state, {
      type: "permission_required", thread: T1, runId: "r1", gateId: "g1", preview: { tool: "write_volume_fields" }, humanOnly: false,
    });
    state = chatReducer(state, {
      type: "permission_required", thread: T2, runId: "r2", gateId: "g2", preview: {}, humanOnly: true,
    });
    state = chatReducer(state, { type: "gate_resolved", gateId: "g1", approved: true });
    const g1 = bucket(state).find((m) => m.gateId === "g1")!;
    const g2 = bucket(state, T2).find((m) => m.gateId === "g2")!;
    expect(g1.gateState).toBe("approved");
    expect(g2.gateState).toBe("pending");
  });

  it("adopt_card 跨线程置已采纳（卡在别的线程也能被宿主回执）", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, {
      type: "artifact", thread: T1, runId: "r1", cardId: "c1", kind: "text",
      payload: { draft: { name: "卷一" }, vol_no: 1 },
    });
    state = chatReducer(state, { type: "adopt_card", cardId: "c1" });
    expect(bucket(state).find((m) => m.kind === "card")!.cardStatus).toBe("adopted");
  });

  it("error 落一条错误消息（不重复堆叠）且停止流式", () => {
    state = chatReducer(state, { type: "run_start", thread: T1, runId: "r1" });
    state = chatReducer(state, { type: "error", thread: T1, message: "断流" });
    state = chatReducer(state, { type: "error", thread: T1, message: "断流" });
    expect(bucket(state).filter((m) => m.kind === "error")).toHaveLength(1);
    expect(state.runActive).toBe(false);
  });

  it("load_history 换入线程历史；clear_thread 只清本线程", () => {
    state = chatReducer(state, { type: "user_send", thread: T1, id: "a1", text: "章纲", page: "og" });
    state = chatReducer(state, {
      type: "load_history",
      thread: T2,
      messages: [{ id: "h1", role: "user", kind: "text", text: "正文历史", steps: [] }],
    });
    expect(bucket(state, T2)).toHaveLength(1);
    expect(bucket(state, T1)).toHaveLength(1); // 其他线程不动
    state = chatReducer(state, { type: "clear_thread", thread: T2 });
    expect(bucket(state, T2)).toHaveLength(0);
    expect(bucket(state, T1)).toHaveLength(1);
  });
});
