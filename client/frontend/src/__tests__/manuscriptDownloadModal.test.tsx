// 下载成稿弹层（manuscript-download）组件契约：
//   表单态（位置/文件名/格式多选/摘要/无壳降级）· 未选格式禁用 ·
//   409 按 running_kind 提示 · 轮询到 done 呈完成态 · 运行中关弹层=后台运行 ·
//   鉴权（Authorization 头）· 轮询 quiet 语义 · 停滞守卫 · 发起双击防护。
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import ManuscriptDownloadModal from "@/components/novel/workbench/ManuscriptDownloadModal";
import { toast } from "@/lib/toast";

vi.mock("@/lib/toast", () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

const fetchMock = vi.fn();

// 默认无壳（window.pywebview 不存在）
function renderModal(props: Partial<Record<string, unknown>> = {}) {
  return render(
    <ManuscriptDownloadModal
      open
      onClose={vi.fn()}
      projectId="p1"
      bookName="星海拾遗"
      stats={{ chapters: 3, words: 725 }}
      {...props}
    />,
  );
}

/** 装壳桥 + 填目录，返回后可直接点「开始下载」 */
function armForm(dir = "/tmp/out") {
  (window as unknown as { pywebview?: unknown }).pywebview = {
    api: { pick_folder: vi.fn(), open_folder: vi.fn(), default_dirs: vi.fn(async () => []) },
  };
  fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, {
    target: { value: dir },
  });
}

const idleRes = () => ({
  ok: true,
  status: 200,
  json: async () => ({ code: 0, data: { state: "idle" } }),
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  localStorage.removeItem("auth_token");
  window.location.hash = "";
});

describe("ManuscriptDownloadModal — 下载成稿", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ data: { state: "idle" } }),
      status: 200,
    });
    vi.stubGlobal("fetch", fetchMock);
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("表单态：摘要章数/字数 + 不含旧稿口径", () => {
    renderModal();
    expect(screen.getByText(/本次下载 3 章/).textContent).toContain("本次下载 3 章 · 725 字");
    expect(screen.getByText(/本次下载 3 章/).textContent).toContain("不含旧稿支线");
  });

  it("无壳环境：呈现需要桌面版说明（可点击出口），不静默", () => {
    renderModal();
    const note = screen.getAllByText(/下载成稿需要桌面版应用/)[0];
    expect(note.querySelector("a")).toBeTruthy();
  });

  it("未选任何格式时主按钮禁用", () => {
    renderModal();
    fireEvent.click(document.querySelector('[data-od-id="download-fmt-md"]')!);
    fireEvent.click(document.querySelector('[data-od-id="download-fmt-docx"]')!);
    expect((screen.getByText("开始下载") as HTMLButtonElement).disabled).toBe(true);
  });

  it("409 按 running_kind 说人话（备份在跑）且停留在表单态", async () => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: vi.fn(), default_dirs: vi.fn(async () => []) },
    };
    fetchMock.mockResolvedValueOnce({
      status: 409,
      json: async () => ({ detail: { message: "已有备份任务在进行中", running_kind: "backup" } }),
    });
    renderModal();
    await act(async () => {
      fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, {
        target: { value: "/tmp/out" },
      });
    });
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("已有备份任务在进行中"));
    // 仍在表单态
    expect(screen.getByText("开始下载")).toBeTruthy();
  });

  it("轮询到 done：完成态列出产出文件（重开弹层可读回）", async () => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: vi.fn(), default_dirs: vi.fn(async () => []) },
    };
    // start 成功 → running；随后 status 返回 done
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          code: 0,
          data: {
            state: "done",
            pct: 100,
            files: ["星海拾遗 · 主线全稿.md", "星海拾遗 · 主线全稿.docx"],
            steps: [
              { format: "md", state: "完成", error: null },
              { format: "docx", state: "完成", error: null },
            ],
            target_dir: "/tmp/out",
          },
        }),
      };
    });
    renderModal();
    await act(async () => {
      fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, {
        target: { value: "/tmp/out" },
      });
    });
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByText("下载完成")).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByText("打开文件夹")).toBeTruthy();
    // 完成页列出逐格式产出
    expect(screen.getByText((_, el) => el?.textContent === "星海拾遗 · 主线全稿.md")).toBeTruthy();
  });

  it("运行中「后台运行」关闭弹层不取消（onClose 被调、无重置）", async () => {
    const onClose = vi.fn();
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: vi.fn(), default_dirs: vi.fn(async () => []) },
    };
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          code: 0,
          data: { state: "running", pct: 40, steps: [{ format: "md", state: "下载中", error: null }] },
        }),
      };
    });
    renderModal({ onClose });
    await act(async () => {
      fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, {
        target: { value: "/tmp/out" },
      });
    });
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByText("后台运行")).toBeTruthy(), { timeout: 3000 });
    fireEvent.click(screen.getByText("后台运行"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("ManuscriptDownloadModal — 评审补强（PR #409 评审 findings）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ data: { state: "idle" } }),
      status: 200,
    });
    vi.stubGlobal("fetch", fetchMock);
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("无壳环境：开始下载禁用（不发请求双保险）", () => {
    renderModal();
    expect((screen.getByText("开始下载") as HTMLButtonElement).disabled).toBe(true);
  });

  it("409 下载在跑：文案区分任务类型", async () => {
    fetchMock.mockResolvedValueOnce({
      status: 409,
      json: async () => ({ detail: { message: "已有下载任务在进行中", running_kind: "download" } }),
    });
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: vi.fn(), default_dirs: vi.fn(async () => []) },
    };
    renderModal();
    fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, {
      target: { value: "/tmp/out" },
    });
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("已有下载任务在进行中"));
    expect(screen.getByText("开始下载")).toBeTruthy();
  });

  it("下载失败：err 文案 + 返回修改/重试出口", async () => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: vi.fn(), default_dirs: vi.fn(async () => []) },
    };
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          code: 0,
          data: {
            state: "error",
            error: { code: "permission_denied", message: "无法写入所选目录：/tmp/out" },
            steps: [{ format: "md", state: "失败", error: "无法写入所选目录：/tmp/out" }],
          },
        }),
      };
    });
    renderModal();
    fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, {
      target: { value: "/tmp/out" },
    });
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByRole("alert").textContent).toContain("无法写入所选目录");
    expect(screen.getByText("返回修改")).toBeTruthy();
    expect(screen.getByText("重试")).toBeTruthy();
  });

  it("鉴权回归：发起与轮询都带 Authorization（裸 fetch 曾 401 全线不通）", async () => {
    localStorage.setItem("auth_token", "regress-token");
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: vi.fn(), default_dirs: vi.fn(async () => []) },
    };
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ code: 0, data: { state: "running", pct: 10, steps: [] } }),
      };
    });
    renderModal();
    fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, {
      target: { value: "/tmp/out" },
    });
    fireEvent.click(screen.getByText("开始下载"));
    // 等到轮询也发过一轮（发起 + 至少一次 status）
    await waitFor(
      () =>
        expect(
          fetchMock.mock.calls.some(([u]) => String(u).includes("/download/status")),
        ).toBe(true),
      { timeout: 3000 },
    );
    const calls = fetchMock.mock.calls as Array<[string, RequestInit]>;
    expect(calls.length).toBeGreaterThanOrEqual(2);
    for (const [url, init] of calls) {
      // 两个端点都必须带 Bearer（后端 auth_local.get_current_user 无头即 401）
      expect(String(url)).toContain("/api/manuscript/download/");
      expect((init?.headers as Record<string, string>)?.Authorization).toBe("Bearer regress-token");
    }
    localStorage.removeItem("auth_token");
  });

  it("文件名默认值跟随书名（首挂 bookName 为空后就绪的场景）", async () => {
    const first = render(<ManuscriptDownloadModal open onClose={vi.fn()} projectId="p1" bookName="" stats={{ chapters: 0, words: 0 }} />);
    await waitFor(() => expect(document.querySelector('[data-od-id="download-filename"]')).toBeTruthy());
    // bookName 就绪（props 变化）→ 默认名跟随补全
    first.rerender(<ManuscriptDownloadModal open onClose={vi.fn()} projectId="p1" bookName="星海拾遗" stats={{ chapters: 3, words: 725 }} />);
    await waitFor(() =>
      expect((document.querySelector('[data-od-id="download-filename"]') as HTMLInputElement).value).toBe("星海拾遗 · 主线全稿"),
    );
    first.unmount();
  });
});

describe("ManuscriptDownloadModal — 轮询语义与降级（PR #414 评审 findings）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockResolvedValue(idleRes());
    vi.stubGlobal("fetch", fetchMock);
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("quiet 轮询：401 不清凭据、不跳登录页（frontend-auth-heal 规范）", async () => {
    localStorage.setItem("auth_token", "keep-me");
    fetchMock.mockImplementation(async (_u: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) };
      }
      return { ok: false, status: 401, json: async () => ({ detail: "未提供认证信息" }) };
    });
    renderModal();
    act(() => armForm());
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/download/status"))).toBe(true),
    );
    // 轮询是"后台刷新"探测类请求：瞬时 401 只静默重试，绝不把正在写作的用户踢回登录页
    expect(localStorage.getItem("auth_token")).toBe("keep-me");
    expect(window.location.hash).not.toBe("#/login");
  });

  it("停滞守卫：连续 idle 到阈值 → 可见降级（不再无限假进度）", async () => {
    fetchMock.mockImplementation(async (_u: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) };
      }
      return idleRes(); // 任务在后端消失（重启/被顶掉）→ 恒 idle
    });
    // 阈值注入小值 + 真实定时器（假定时器与 React 19 调度打架，第一版即栽在这）
    renderModal({ pollStallLimit: 2 });
    act(() => armForm());
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("下载进度已中断"), {
      timeout: 6000,
    });
  });

  it("停滞守卫：连续失败到阈值 → 可见降级（不弹跳登录页、也不假死）", async () => {
    fetchMock.mockImplementation(async (_u: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) };
      }
      throw new TypeError("Failed to fetch");
    });
    renderModal({ pollStallLimit: 2 });
    act(() => armForm());
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("网络连接中断"), {
      timeout: 6000,
    });
  });

  it("发起中禁用按钮：双击只发一个 POST", async () => {
    let resolvePost: ((v: unknown) => void) | undefined;
    fetchMock.mockImplementation(async (_u: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return new Promise((res) => {
          resolvePost = res;
        }) as Promise<unknown>;
      }
      return idleRes();
    });
    renderModal();
    act(() => armForm());
    const btn = screen.getByText("开始下载") as HTMLButtonElement;
    fireEvent.click(btn);
    fireEvent.click(btn);
    await waitFor(() => expect(btn.disabled).toBe(true));
    const posts = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    await act(async () => {
      resolvePost?.({ ok: true, status: 200, json: async () => ({ code: 0, data: { state: "running" } }) });
    });
  });

  it("非 409 的 4xx：透出后端可行动中文（404「作品不存在」）", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: "作品不存在" }),
    });
    renderModal();
    act(() => armForm());
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("作品不存在"));
    // 仍在表单态
    expect(screen.getByText("开始下载")).toBeTruthy();
  });

  it("5xx 与网络层失败：回落中文兜底（不漏英文 statusText）", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => {
        throw new Error("not json");
      },
    });
    renderModal();
    act(() => armForm());
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("下载发起失败，请重试"));
  });
});

// ---------------------------------------------------------------------------
// 完成态出口（#414 评审遗留 P2）：弹层挂壳层常驻、phase 不随 open 复位，
// 没有回表单出口就只能切回书架再进书才能再下载一次。
// ---------------------------------------------------------------------------

describe("ManuscriptDownloadModal — 完成态再下载", () => {
  const fetchMock2 = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock2);
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem("auth_token");
  });

  const runningRes = () => ({
    ok: true,
    status: 200,
    json: async () => ({ code: 0, data: { state: "running", pct: 40, steps: [] } }),
  });
  const doneRes = () => ({
    ok: true,
    status: 200,
    json: async () => ({
      code: 0,
      data: {
        state: "done",
        pct: 100,
        files: ["星海拾遗 · 主线全稿.md"],
        steps: [{ format: "md", state: "完成", error: null }],
        target_dir: "/tmp/out",
      },
    }),
  });

  /**
   * 第一单直接完成；第 2 单起先回 N 拍 running 再回 done。
   * 不能"GET 恒 done"：那样 running 只是几毫秒的中间态，任何对进度态的断言都是
   * 竞态（#415 评审 P1 实测 18~22% 红，加长超时还会被 vitest 5s 上限伪装成超时超时）。
   */
  function mockDoneFlow(secondRoundRunningPolls = 3) {
    let posts = 0;
    let polls = 0;
    fetchMock2.mockImplementation(async (_u: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        posts += 1;
        polls = 0;
        return runningRes();
      }
      if (posts >= 2) {
        polls += 1;
        return polls <= secondRoundRunningPolls ? runningRes() : doneRes();
      }
      return doneRes();
    });
  }

  it(
    "完成态「再次下载」回表单：沿用用户改过的目录/文件名/格式，且能立刻跑完第二单",
    async () => {
      mockDoneFlow();
      renderModal();
      act(() => armForm());
      // 全部改成**非默认值**（默认名/默认格式即使被重置也照样"通过"，那是假绿——
      // #415 评审 P2）：文件名自定义，格式点掉 md、点开 txt
      fireEvent.change(document.querySelector('[data-od-id="download-filename"]')!, {
        target: { value: "我的稿子" },
      });
      fireEvent.click(document.querySelector('[data-od-id="download-fmt-md"]')!);
      fireEvent.click(document.querySelector('[data-od-id="download-fmt-txt"]')!);

      fireEvent.click(screen.getByText("开始下载"));
      await waitFor(() => expect(screen.getByText("下载完成")).toBeTruthy(), { timeout: 3000 });

      // 完成态同时给出「再次下载」与「打开文件夹」两个出口
      fireEvent.click(screen.getByText("再次下载"));

      // 回表单且会话记忆沿用（断言非默认值才有区分度）
      expect((document.querySelector('[data-od-id="download-dir"]') as HTMLInputElement).value).toBe("/tmp/out");
      expect((document.querySelector('[data-od-id="download-filename"]') as HTMLInputElement).value).toBe("我的稿子");
      expect(document.querySelector('[data-od-id="download-fmt-md"]')?.getAttribute("aria-checked")).toBe("false");
      expect(document.querySelector('[data-od-id="download-fmt-txt"]')?.getAttribute("aria-checked")).toBe("true");
      const btn = screen.getByText("开始下载") as HTMLButtonElement;
      expect(btn.disabled).toBe(false);

      // 立刻再发起：第二单先经稳定的进度态（3 拍 running）再到完成——两端都是稳定态，不赌瞬态
      fireEvent.click(btn);
      await waitFor(() => expect(screen.getByText("后台运行")).toBeTruthy(), { timeout: 3000 });
      await waitFor(
        () =>
          expect(
            fetchMock2.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === "POST"),
          ).toHaveLength(2),
        { timeout: 3000 },
      );
      await waitFor(() => expect(screen.getByText("下载完成")).toBeTruthy(), { timeout: 3000 });
    },
    15000,
  );

  it("完成态「打开文件夹」：走壳桥并带上保存目录", async () => {
    mockDoneFlow();
    const openFolder = vi.fn(async () => true);
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: openFolder, default_dirs: vi.fn(async () => []) },
    };
    renderModal();
    fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, { target: { value: "/tmp/out" } });
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByText("下载完成")).toBeTruthy(), { timeout: 3000 });
    fireEvent.click(screen.getByText("打开文件夹"));
    await waitFor(() => expect(openFolder).toHaveBeenCalledWith("/tmp/out"));
  });

  it("完成态打开文件夹失败：可读提示（不静默、不报错）", async () => {
    mockDoneFlow();
    const openFolder = vi.fn(async () => false);
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(), open_folder: openFolder, default_dirs: vi.fn(async () => []) },
    };
    renderModal();
    fireEvent.change(document.querySelector('[data-od-id="download-dir"]')!, { target: { value: "/tmp/out" } });
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByText("下载完成")).toBeTruthy(), { timeout: 3000 });
    fireEvent.click(screen.getByText("打开文件夹"));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("无法打开文件夹，可手动前往保存位置"));
  });

  it("重开弹层仍读到完成态（规格「完成后进度仍可读」不被这次改动破坏）", async () => {
    mockDoneFlow();
    const { rerender } = renderModal();
    act(() => armForm());
    fireEvent.click(screen.getByText("开始下载"));
    await waitFor(() => expect(screen.getByText("下载完成")).toBeTruthy(), { timeout: 3000 });

    const props = {
      onClose: vi.fn(),
      projectId: "p1",
      bookName: "星海拾遗",
      stats: { chapters: 3, words: 725 },
    };
    // 关闭再打开（壳层常驻，phase 不清）——包 act 等退场结束，否则断言落在退场窗口里
    await act(async () => {
      rerender(<ManuscriptDownloadModal open={false} {...props} />);
    });
    await act(async () => {
      rerender(<ManuscriptDownloadModal open {...props} />);
    });
    expect(screen.getByText("下载完成")).toBeTruthy();
    expect(screen.getByText("再次下载")).toBeTruthy();
  });
});
