import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

const requestMock = vi.fn();
const setTokenMock = vi.fn();

beforeEach(() => {
  requestMock.mockReset();
  setTokenMock.mockReset();
  localStorage.clear();
  vi.resetModules();
  vi.doMock("@/lib/api", () => ({ request: requestMock }));
  vi.doMock("@/lib/auth", () => ({ setToken: setTokenMock }));
});

async function mountHeal() {
  const { useAuthHeal } = await import("@/hooks/useAuthHeal");
  return renderHook(() => useAuthHeal());
}

describe("useAuthHeal", () => {
  it("后端会话有效时写回 localStorage token/username", async () => {
    requestMock.mockResolvedValue({
      code: 0,
      data: { token: "healed-token", username: "modoojunko" },
    });
    await mountHeal();
    await vi.waitFor(() => expect(requestMock).toHaveBeenCalledWith("/auth/check-auth"));

    expect(setTokenMock).toHaveBeenCalledWith("healed-token", "modoojunko");
  });

  it("未登录（code!==0）不清除/不覆盖现有 localStorage", async () => {
    localStorage.setItem("auth_token", "existing-token");
    requestMock.mockResolvedValue({ code: 1, data: { message: "未登录" } });
    await mountHeal();
    await vi.waitFor(() => expect(requestMock).toHaveBeenCalled());

    expect(setTokenMock).not.toHaveBeenCalled();
    expect(localStorage.getItem("auth_token")).toBe("existing-token");
  });

  it("dev-token 不写回（开发占位）", async () => {
    localStorage.setItem("auth_token", "existing-token");
    requestMock.mockResolvedValue({
      code: 0,
      data: { token: "dev-token", username: "dev" },
    });
    await mountHeal();
    await vi.waitFor(() => expect(requestMock).toHaveBeenCalled());

    expect(setTokenMock).not.toHaveBeenCalled();
  });

  it("网络失败静默：不抛错、不修改 localStorage", async () => {
    localStorage.setItem("auth_token", "existing-token");
    requestMock.mockRejectedValue(new Error("network down"));
    await mountHeal();
    await vi.waitFor(() => expect(requestMock).toHaveBeenCalled());

    expect(setTokenMock).not.toHaveBeenCalled();
    expect(localStorage.getItem("auth_token")).toBe("existing-token");
  });
});

describe("useAuthHeal 冷启动重试", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("code -1（S端冷启动 503）后重试，成功即写回 token", async () => {
    requestMock
      .mockResolvedValueOnce({ code: -1, msg: "S端响应异常（HTTP 503）" })
      .mockResolvedValue({ code: 0, data: { token: "healed-token", username: "modoojunko" } });
    await mountHeal();
    await vi.advanceTimersByTimeAsync(0);
    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(setTokenMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(20_000);
    expect(requestMock).toHaveBeenCalledTimes(2);
    expect(setTokenMock).toHaveBeenCalledWith("healed-token", "modoojunko");
    // 成功后不再重试
    await vi.advanceTimersByTimeAsync(60_000);
    expect(requestMock).toHaveBeenCalledTimes(2);
  });

  it("pairing_broken（c-pack-auth-selfheal D8）：清凭据＋持久化提示＋回登录页", async () => {
    localStorage.setItem("auth_token", "stale-token");
    localStorage.setItem("auth_username", "writer");
    requestMock.mockResolvedValue({
      code: 1,
      data: { pairing_broken: true, message: "登录状态已过期，请重新登录；本地作品不受影响" },
    });
    await mountHeal();
    await vi.waitFor(() =>
      expect(sessionStorage.getItem("auth_notice")).toContain("重新登录"),
    );
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(localStorage.getItem("auth_username")).toBeNull();
    expect(window.location.hash).toBe("#/login");
  });

  it("code 1（明确未登录）不重试", async () => {
    requestMock.mockResolvedValue({ code: 1, data: { message: "未登录" } });
    await mountHeal();
    await vi.advanceTimersByTimeAsync(0);
    expect(requestMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(120_000);
    expect(requestMock).toHaveBeenCalledTimes(1);
  });

  it("请求失败（后端不可达）同样重试直至成功", async () => {
    requestMock
      .mockRejectedValueOnce(new Error("backend down"))
      .mockResolvedValue({ code: 0, data: { token: "healed-token", username: "u" } });
    await mountHeal();
    await vi.advanceTimersByTimeAsync(0);
    expect(requestMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(20_000);
    expect(requestMock).toHaveBeenCalledTimes(2);
    expect(setTokenMock).toHaveBeenCalledWith("healed-token", "u");
  });

  it("持续失败最多 4 次（首次 + 3 重试）后放弃，保持静默", async () => {
    requestMock.mockResolvedValue({ code: -1, msg: "S端 不可达" });
    await mountHeal();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(requestMock).toHaveBeenCalledTimes(4);
    expect(setTokenMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(120_000);
    expect(requestMock).toHaveBeenCalledTimes(4);
  });
});
