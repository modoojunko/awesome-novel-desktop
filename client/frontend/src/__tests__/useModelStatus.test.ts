import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useModelStatus } from "@/hooks/useModelStatus";

// tasks 9.1.5：hook 只透传后端 ai_state，不做本地推导（D13）
const apiConfigs = vi.hoisted(() => ({ configs: [] as unknown[] }));

vi.mock("@/hooks/useApiConfigs", () => ({
  useApiConfigs: () => ({ configs: apiConfigs.configs, loading: false }),
}));

vi.mock("@/lib/auth", () => ({ getToken: () => "t" }));

function mockFetch(payload: Record<string, unknown>) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("useModelStatus · ai_state 透传", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    apiConfigs.configs = [];
  });

  it.each([
    ["ready", "configured"],
    ["no_key", "no_key"],
    ["missing_model", "no_model"],
    ["invalid", "invalid"],
    ["member_required", "no_key"],
  ])("ai_state=%s → status=%s（原样透传，无本地推导）", async (aiState, status) => {
    mockFetch({ ai_state: aiState, model: "gpt-4o", effective_model: "gpt-4o", message: "m" });
    const { result } = renderHook(() => useModelStatus("p1"));
    // 先等加载完成——no_key 是初始兜底值，直接等 aiState 会在 fetch 前就通过
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.aiState).toBe(aiState);
    expect(result.current.status).toBe(status);
    expect(result.current.aiMessage).toBe("m");
  });

  it("ai_config_id 有值但 ai_model 空时不得 ready（后端判 missing_model）", async () => {
    mockFetch({ ai_state: "missing_model", api_config_id: "c1", model: null });
    const { result } = renderHook(() => useModelStatus("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.aiState).toBe("missing_model");
    expect(result.current.status).not.toBe("configured");
  });

  it("接口失败时保持兜底 no_key（不误判就绪）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 500 }));
    const { result } = renderHook(() => useModelStatus("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.aiState).toBe("no_key");
  });
});
