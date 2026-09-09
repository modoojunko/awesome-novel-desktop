import { beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// 503 双轨统一：request() 不再强跳 /config，按响应体分型就地提示
//   app 级（JSON detail 含「未配置」）→ toast.error + 去配置 action
//   infra 级（HTML/空体=云托管冷启动）→ toast.info 唤醒提示
//   quiet / soft503 抑制全局提示；并发节流只弹一条
// ---------------------------------------------------------------------------

const toastMock = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));

vi.mock("@/lib/toast", () => ({ toast: toastMock }));

/** 503 响应桩：request() 的 503 分支只读 status/ok/text() */
function res503(body: string) {
  return { status: 503, ok: false, text: async () => body } as unknown as Response;
}

const APP_BODY = JSON.stringify({
  detail: "AI 服务未配置 — 请先在设置中填写 API Key",
});
const INFRA_BODY = "<html><body>503 Service Unavailable</body></html>";

let request: typeof import("@/lib/api")["request"];
let importParse: typeof import("@/lib/api")["importParse"];

beforeEach(async () => {
  vi.clearAllMocks();
  vi.resetModules();
  window.location.hash = "";
  const mod = await import("@/lib/api");
  request = mod.request;
  importParse = mod.importParse;
});

describe("request() 503 分型", () => {
  it("app 级（未配 Key）：抛错带 status、toast 带「去配置」action、不强跳", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res503(APP_BODY)));

    const err = await request("/novels/p1/chapters/c1/prompts").catch((e) => e);
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(503);
    expect(err.message).toContain("未配置");

    expect(toastMock.error).toHaveBeenCalledTimes(1);
    const [msg, opts] = toastMock.error.mock.calls[0];
    expect(msg).toContain("尚未配置模型 API Key");
    expect(opts?.action?.label).toBe("去配置");

    // 不强跳 /config（就地提示，保住编辑上下文）
    expect(window.location.hash).not.toBe("#/config");
    // action 点击才导航
    opts.action.onClick();
    expect(window.location.hash).toBe("#/config");
  });

  it("infra 级（冷启动 HTML 体）：toast.info 唤醒提示、错误信息兜底", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res503(INFRA_BODY)));

    const err = await request("/novels/p1/volumes").catch((e) => e);
    expect(err.status).toBe(503);
    expect(err.message).toBe("Service unavailable");

    expect(toastMock.info).toHaveBeenCalledTimes(1);
    expect(toastMock.info.mock.calls[0][0]).toContain("唤醒");
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(window.location.hash).not.toBe("#/config");
  });

  it("quiet: true 不弹全局提示，错误照抛", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res503(APP_BODY)));

    const err = await request("/x", { quiet: true }).catch((e) => e);
    expect(err.status).toBe(503);
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.info).not.toHaveBeenCalled();
  });

  it("soft503: true 不弹全局提示（调用方就地处理路径）", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res503(APP_BODY)));

    const err = await request("/x", { soft503: true }).catch((e) => e);
    expect(err.status).toBe(503);
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.info).not.toHaveBeenCalled();
  });

  it("节流：8s 内并发失败只弹一条", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res503(APP_BODY)));

    await request("/a").catch(() => {});
    await request("/b").catch(() => {});
    await request("/c").catch(() => {});

    expect(toastMock.error).toHaveBeenCalledTimes(1);
  });
});

describe("importParse() 503", () => {
  it("不强跳、不弹全局 toast，交由调用方就地提示", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res503(INFRA_BODY)));

    const file = new File(["# 卷一"], "book.md", { type: "text/markdown" });
    const err = await importParse(file).catch((e) => e);
    expect(err.status).toBe(503);
    expect(err.message).toContain("稍后重试");
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.info).not.toHaveBeenCalled();
    expect(window.location.hash).not.toBe("#/config");
  });
});

// ── 对象 detail（AI 前置三态）：按 reason 分流、不进 infra 全局提示（tasks 9.3.5）──
const OBJ_BODY = (reason: string, message: string) =>
  JSON.stringify({ detail: { reason, message } });

describe("request() 503 · 对象 detail 分流", () => {
  it.each(["no_key", "missing_model", "invalid"])(
    "reason=%s：透传 e.reason + message，不弹 infra 全局提示",
    async (reason) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(res503(OBJ_BODY(reason, `先处理 ${reason}`))),
      );

      const err = await request("/novels/p1/settings/ai/genre/track").catch((e) => e);
      expect(err.status).toBe(503);
      expect(err.reason).toBe(reason);
      expect(err.message).toBe(`先处理 ${reason}`);
      // no_key/missing_model 是可操作引导，不得弹「云端唤醒中」
      if (reason === "invalid") {
        expect(toastMock.info).toHaveBeenCalled();
      } else {
        expect(toastMock.info).not.toHaveBeenCalled();
      }
      expect(toastMock.error).not.toHaveBeenCalled();
      expect(window.location.hash).not.toBe("#/config");
    },
  );

  it("未知 reason：仍按 infra 全局提示（不静默）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(res503(OBJ_BODY("weird", "未知原因"))),
    );
    const err = await request("/x").catch((e) => e);
    expect(err.reason).toBe("weird");
    expect(toastMock.info).toHaveBeenCalledTimes(1);
  });
});
