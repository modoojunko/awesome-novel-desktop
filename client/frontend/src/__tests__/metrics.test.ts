// 度量埋点单测（PRD §7 / tasks 5.3）：事件名、payload、可关开关、失败静默。
// 契约：埋点永不冒泡——api.post 拒绝也不能产生未处理 rejection 或用户可见副作用。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { metricsOff, track } from "@/lib/metrics";

describe("度量埋点（metrics）", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("track：POST /events 带事件名与 payload，quiet 不触发全局副作用", () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ ok: true });
    track("plan_entry_open", { tier: "pro" });
    expect(post).toHaveBeenCalledWith(
      "/events",
      { event_type: "plan_entry_open", payload: { tier: "pro" } },
      { quiet: true },
    );
  });

  it("track：缺省 payload 为空对象", () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ ok: true });
    track("pick_drawn");
    expect(post).toHaveBeenCalledWith(
      "/events",
      { event_type: "pick_drawn", payload: {} },
      { quiet: true },
    );
  });

  it("可关：localStorage 标记生效时零请求", () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ ok: true });
    localStorage.setItem("pref.metrics.off", "1");
    expect(metricsOff()).toBe(true);
    track("pick_select", { no: 2 });
    expect(post).not.toHaveBeenCalled();
  });

  it("可关：VITE_METRICS=off 构建级关闭优先生效", () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ ok: true });
    vi.stubEnv("VITE_METRICS", "off");
    expect(metricsOff()).toBe(true);
    track("pick_confirm_ok", { vol_no: 1 });
    expect(post).not.toHaveBeenCalled();
  });

  it("localStorage 不可用（隐私模式）按「不关」处理，不抛", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(metricsOff()).toBe(false);
  });

  it("失败静默：请求被拒不留未处理 rejection", async () => {
    const post = vi.spyOn(api, "post").mockRejectedValue(new Error("offline"));
    expect(() => track("desk_expand", { vol_no: 1 })).not.toThrow();
    await Promise.resolve(); // 让 .catch 跑完（无 catch 时此处会触发 unhandled rejection）
    expect(post).toHaveBeenCalledTimes(1);
  });
});
