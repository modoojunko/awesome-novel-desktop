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
