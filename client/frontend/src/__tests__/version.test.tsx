import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const requestMock = vi.fn();

// c-query-cache-layer：缓存并入 React Query——共享同一 QueryClient 才能复现
// 「应用级缓存跨消费方共享/失败不缓存/成功广播拉起」语义。
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

beforeEach(() => {
  requestMock.mockReset();
  queryClient.clear();
  vi.doMock("@/lib/api", () => ({ request: requestMock }));
});

async function mountProbe() {
  const mod = await import("@/lib/version");
  function Probe() {
    const v = mod.useClientVersion();
    return <div data-testid="v">{mod.formatVersion(v)}</div>;
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <Probe />
    </QueryClientProvider>,
  );
}

describe("formatVersion 文案单源", () => {
  it("正式版 / dev / 缺失三分支；不出现「vdev」", async () => {
    const { formatVersion } = await import("@/lib/version");
    expect(formatVersion("0.15.1")).toBe("v0.15.1");
    expect(formatVersion("dev")).toBe("开发版 dev");
    expect(formatVersion(null)).toBe("版本未知");
    expect(formatVersion(undefined)).toBe("版本未知");
    expect(formatVersion("")).toBe("版本未知");
  });

  it("c-version-build-info：dev＋构建信息显 {分支}@{commit前5位}；超长 commit 截前 5", async () => {
    const { formatVersion } = await import("@/lib/version");
    expect(formatVersion({ current: "dev", build: { branch: "main", commit: "f456e" } })).toBe("main@f456e");
    expect(formatVersion({ current: "dev", build: { branch: "feature/foo", commit: "f456e8fa9b" } })).toBe("feature/foo@f456e");
  });

  it("c-version-build-info：半残构建信息（缺 branch/commit）降级「开发版 dev」", async () => {
    const { formatVersion } = await import("@/lib/version");
    expect(formatVersion({ current: "dev", build: { branch: "", commit: "f456e" } })).toBe("开发版 dev");
    expect(formatVersion({ current: "dev", build: { branch: "main", commit: "" } })).toBe("开发版 dev");
    expect(formatVersion({ current: "dev", build: null })).toBe("开发版 dev");
    expect(formatVersion({ current: "dev", build: undefined as never })).toBe("开发版 dev");
  });

  it("c-version-build-info：正式版带构建信息仍显 v{X.Y.Z}（构建信息仅 dev 消费）", async () => {
    const { formatVersion } = await import("@/lib/version");
    expect(formatVersion({ current: "0.25", build: { branch: "main", commit: "f456e" } })).toBe("v0.25");
  });
});

describe("useClientVersion 应用级缓存", () => {
  it("首次挂载 quiet 取 current 并显示；同会话第二消费者吃缓存不再发请求", async () => {
    requestMock.mockResolvedValue({ current: "0.11", has_update: false });
    await mountProbe();
    // useQuery 数据到达是异步微任务——findByTestId 只等元素出现，不等数据
    await waitFor(() => expect(screen.getByTestId("v")).toHaveTextContent("v0.11"));
    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(requestMock).toHaveBeenCalledWith("/update-check", { quiet: true });

    await mountProbe();
    await waitFor(() =>
      expect(screen.getAllByTestId("v")[1]).toHaveTextContent("v0.11"),
    );
    expect(requestMock).toHaveBeenCalledTimes(1); // 缓存命中，零新增请求
  });

  it("失败静默显「版本未知」且不缓存：下次挂载自动重试", async () => {
    requestMock.mockRejectedValueOnce(new Error("backend not ready"));
    const first = await mountProbe();
    expect(await screen.findByTestId("v")).toHaveTextContent("版本未知");
    expect(requestMock).toHaveBeenCalledTimes(1);
    first.unmount();

    requestMock.mockResolvedValue({ current: "0.13", has_update: false });
    await mountProbe();
    await waitFor(() => expect(screen.getByTestId("v")).toHaveTextContent("v0.13"));
    expect(requestMock).toHaveBeenCalledTimes(2); // 失败未缓存，重试发生
  });

  it("响应缺失 current 视同失败：不缓存、显「版本未知」", async () => {
    requestMock.mockResolvedValue({ has_update: false });
    const first = await mountProbe();
    expect(await screen.findByTestId("v")).toHaveTextContent("版本未知");
    first.unmount();

    requestMock.mockResolvedValue({ current: "0.14", has_update: false });
    await mountProbe();
    await waitFor(() => expect(screen.getByTestId("v")).toHaveTextContent("v0.14"));
  });

  it("c-version-build-info：响应带 build 时缓存对象透传，状态条呈 {分支}@{commit前5位}", async () => {
    requestMock.mockResolvedValue({
      current: "dev", has_update: false,
      build: { branch: "main", commit: "f456e" },
    });
    await mountProbe();
    await waitFor(() => expect(screen.getByTestId("v")).toHaveTextContent("main@f456e"));
  });

  it("先挂载方失败后，后挂载方重试成功会广播拉起先挂载方（状态条不滞后于弹窗）", async () => {
    requestMock.mockRejectedValueOnce(new Error("backend not ready"));
    const statusbar = await mountProbe(); // 模拟根部状态条：先挂载、失败
    expect(await screen.findByTestId("v")).toHaveTextContent("版本未知");

    requestMock.mockResolvedValue({ current: "0.13", has_update: false });
    await mountProbe(); // 模拟后打开的弹窗：重试成功
    await waitFor(() =>
      expect(screen.getAllByTestId("v")[0]).toHaveTextContent("v0.13"), // 先挂载方无需重挂即被拉起
    );
    expect(screen.getAllByTestId("v")[1]).toHaveTextContent("v0.13");
    statusbar.unmount();
  });
});
