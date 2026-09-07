import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const requestMock = vi.fn();

beforeEach(() => {
  requestMock.mockReset();
  vi.resetModules();
  vi.doMock("@/lib/api", () => ({ request: requestMock }));
});

async function mountProbe() {
  const mod = await import("@/lib/version");
  function Probe() {
    const v = mod.useClientVersion();
    return <div data-testid="v">{mod.formatVersion(v)}</div>;
  }
  return render(<Probe />);
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
});

describe("useClientVersion 应用级缓存", () => {
  it("首次挂载 quiet 取 current 并显示；同会话第二消费者吃缓存不再发请求", async () => {
    requestMock.mockResolvedValue({ current: "0.11", has_update: false });
    await mountProbe();
    expect(await screen.findByTestId("v")).toHaveTextContent("v0.11");
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
    expect(await screen.findByTestId("v")).toHaveTextContent("v0.13");
    expect(requestMock).toHaveBeenCalledTimes(2); // 失败未缓存，重试发生
  });

  it("响应缺失 current 视同失败：不缓存、显「版本未知」", async () => {
    requestMock.mockResolvedValue({ has_update: false });
    const first = await mountProbe();
    expect(await screen.findByTestId("v")).toHaveTextContent("版本未知");
    first.unmount();

    requestMock.mockResolvedValue({ current: "0.14", has_update: false });
    await mountProbe();
    expect(await screen.findByTestId("v")).toHaveTextContent("v0.14");
  });
});
