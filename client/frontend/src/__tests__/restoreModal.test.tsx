// 恢复导入弹窗（backup-restore）契约：
//   鉴权（四处调用都带 Authorization；书名单走 quiet）· 解析失败停在选包步 ·
//   恢复失败留在预览步并显示「恢复失败」（不再贴错标签、不再回退重解析）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import RestoreModal from "@/components/RestoreModal";

const fetchMock = vi.fn();

function armBridge(path = "/tmp/pkg.zip") {
  (window as unknown as { pywebview?: unknown }).pywebview = {
    api: { pick_open_file: vi.fn(async () => [path]) },
  };
}

/** 选「作品备份包」（第一个 Slot 的「选择文件」）→ 主按钮解除禁用 */
async function pickAssets() {
  const btns = screen.getAllByText("选择文件");
  fireEvent.click(btns[0]);
  await waitFor(() => expect((screen.getByText("下一步") as HTMLButtonElement).disabled).toBe(false));
}

function mount() {
  return render(<RestoreModal open onClose={vi.fn()} onGoConfig={vi.fn()} />);
}

const okJson = (data: unknown) => ({
  ok: true,
  status: 200,
  json: async () => ({ code: 0, data }),
});

const PARSE_OK = {
  books: [{ name: "星海拾遗", path: "p", source_zip: "z" }],
  config: null,
  warnings: [],
  schema_version: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("auth_token", "restore-token");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.removeItem("auth_token");
  window.location.hash = "";
  delete (window as unknown as { pywebview?: unknown }).pywebview;
});

describe("RestoreModal 恢复链路", () => {
  it("解析与恢复的请求都带 Authorization（裸 fetch 曾致 401）", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) return okJson(PARSE_OK);
      if (String(url).includes("/backup/import/persist")) {
        return okJson({ results: [{ book_id: "b1", status: "ok" }], warnings: [], reattach: { mode: "none", attached: 0 } });
      }
      return { ok: true, status: 200, json: async () => [] }; // GET /novels
    });
    armBridge();
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    fireEvent.click(screen.getByText("确认恢复"));
    await waitFor(() => expect(screen.getByText(/已恢复 1 本书/)).toBeTruthy());

    const urls = fetchMock.mock.calls.map(([u]) => String(u));
    expect(urls.some((u) => u.includes("/api/backup/import/parse"))).toBe(true);
    expect(urls.some((u) => u.includes("/api/backup/import/persist"))).toBe(true);
    for (const [, init] of fetchMock.mock.calls as Array<[string, RequestInit]>) {
      expect((init?.headers as Record<string, string>)?.Authorization).toBe("Bearer restore-token");
    }
  });

  it("书名单命中同名著：标记「与现有书目重名·将以副本恢复」", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) return okJson(PARSE_OK);
      return { ok: true, status: 200, json: async () => [{ name: "星海拾遗" }] }; // GET /novels
    });
    armBridge();
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() =>
      expect(screen.getByText("与现有书目重名·将以副本恢复")).toBeTruthy(),
    );
  });

  it("解析失败：停在选包步，错误块标题「解析失败」+ 后端中文原因", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "备份包格式不受支持" }),
    });
    armBridge();
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("解析失败");
    expect(alert.textContent).toContain("备份包格式不受支持");
    expect(screen.queryByText("确认恢复")).toBeNull(); // 未进入预览步
  });

  it("恢复失败：留在预览步、标题「恢复失败」（不再贴「解析失败」标签）", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) return okJson(PARSE_OK);
      if (String(url).includes("/backup/import/persist")) {
        return { ok: false, status: 422, json: async () => ({ detail: "恢复失败：磁盘空间不足" }) };
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    armBridge();
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    fireEvent.click(screen.getByText("确认恢复"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("恢复失败");
    expect(alert.textContent).toContain("磁盘空间不足");
    // 仍在预览步：可直接重试，不必重新选包重解析
    expect(screen.getByText("确认恢复")).toBeTruthy();
  });

  it("书名单（可选富化）走 quiet：401 不清凭据、不跳登录（静默预取不得踢人）", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) return okJson(PARSE_OK);
      return { ok: false, status: 401, json: async () => ({ detail: "登录状态无效，请重新登录" }) };
    });
    armBridge();
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    expect(localStorage.getItem("auth_token")).toBe("restore-token");
    expect(window.location.hash).not.toBe("#/login");
  });
});

// ---------------------------------------------------------------------------
// 覆盖补齐（覆盖率专项）：无壳选包 / config 槽位 / 取消接线 / 预览与完成态渲染
// ---------------------------------------------------------------------------

describe("RestoreModal 分支补齐", () => {
  const okJson2 = (data: unknown) => ({ ok: true, status: 200, json: async () => ({ code: 0, data }) });
  const PARSE_FULL = {
    books: [{ name: "星海拾遗", path: "/tmp/a", source_zip: "z" }],
    config: {
      format_version: 1,
      user: { display_name: "别的账号" },
      api_configs: [{ name: "DeepSeek", api_key: "sk-****" }],
    },
    warnings: ["本机记账不随包"],
    schema_version: 1,
  };

  it("无壳环境点「选择文件」：静默不炸（调用方负责提示）", async () => {
    delete (window as unknown as { pywebview?: unknown }).pywebview;
    fetchMock.mockResolvedValue(okJson2(PARSE_FULL));
    mount();
    fireEvent.click(screen.getAllByText("选择文件")[0]);
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("配置包槽位：选中后主按钮可用，且清除上一次解析错误", async () => {
    armBridge("/tmp/config.zip");
    fetchMock.mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "坏包" }) });
    mount();
    // 先制造一次解析错误
    fireEvent.click(screen.getAllByText("选择文件")[0]);
    await waitFor(() => expect((screen.getByText("下一步") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText("下一步"));
    await screen.findByRole("alert");
    // 再选配置包槽位 → setConfigPath + 清错误（66/68/69）
    fireEvent.click(screen.getAllByText("选择文件")[1]);
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("弹窗自身关闭路径（X / 遮罩）走 onClose 包装：非 working 步放行", async () => {
    const onClose = vi.fn();
    const { container } = render(<RestoreModal open onClose={onClose} onGoConfig={vi.fn()} />);
    expect(container).toBeTruthy();
    const scrim = document.querySelector(".scrim") as HTMLElement;
    fireEvent.click(scrim);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("预览步渲染配置项与警告，可「上一步」回选包", async () => {
    localStorage.setItem("auth_username", "我自己"); // 与包内账号不同 → 触发账号不一致提示
    armBridge();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) return okJson2(PARSE_FULL);
      return { ok: true, status: 200, json: async () => [] };
    });
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("DeepSeek")).toBeTruthy());
    expect(screen.getByText("本机记账不随包")).toBeTruthy();
    expect(screen.getByText(/备份来自账号「别的账号」/)).toBeTruthy();
    fireEvent.click(screen.getByText("上一步"));
    await waitFor(() => expect(screen.getByText("下一步")).toBeTruthy());
  });

  it("完成步渲染失败明细与警告；「完成」回选包并关窗", async () => {
    const onClose = vi.fn();
    armBridge();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) return okJson2(PARSE_FULL);
      if (String(url).includes("/backup/import/persist")) {
        return okJson2({
          results: [
            { book_id: "ok-1", status: "ok" },
            { book_id: "bad-2", status: "failed" },
          ],
          warnings: ["有一本未恢复"],
          reattach: { mode: "none", attached: 0 },
        });
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    render(<RestoreModal open onClose={onClose} onGoConfig={vi.fn()} />);
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    fireEvent.click(screen.getByText("确认恢复"));
    await waitFor(() => expect(screen.getByText(/已恢复 1 本书/)).toBeTruthy());
    expect(screen.getByText("bad-2")).toBeTruthy(); // 失败明细
    expect(screen.getByText("有一本未恢复")).toBeTruthy(); // 汇总警告
    fireEvent.click(screen.getByText("完成"));
    expect(onClose).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText("下一步")).toBeTruthy()); // setStep("pick")
  });
});
