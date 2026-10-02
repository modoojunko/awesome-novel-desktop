// 恢复导入弹窗（backup-restore）契约：
//   鉴权（四处调用都带 Authorization；书名单走 quiet）· 解析失败停在选包步 ·
//   恢复失败留在预览步并显示「恢复失败」（不再贴错标签、不再回退重解析）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    await act(async () => {});
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

  it("弹窗自身关闭路径：遮罩与 X 都走 onClose 包装（非 working 步放行）", async () => {
    const onClose = vi.fn();
    render(<RestoreModal open onClose={onClose} onGoConfig={vi.fn()} />);
    fireEvent.click(document.querySelector(".scrim") as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
    // 头部 X 关闭钮（icon-btn x）同样走包装
    const x = document.querySelector(".mcard-head .icon-btn.x") as HTMLElement;
    fireEvent.click(x);
    expect(onClose).toHaveBeenCalledTimes(2);
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

// ---------------------------------------------------------------------------
// 分支覆盖补齐：可选字段缺省 / 全失败汇总 / 接回数 > 0 / working 步锁关闭
// ---------------------------------------------------------------------------

describe("RestoreModal 分支补齐（分支覆盖率专项）", () => {
  const okJson3 = (data: unknown) => ({ ok: true, status: 200, json: async () => ({ code: 0, data }) });

  it("选包返回空数组：静默不选（files?.[0] ?? null 的 null 臂）", async () => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_open_file: vi.fn(async () => []) }, // 空数组 → files[0] 为 undefined
    };
    fetchMock.mockResolvedValue(okJson3({ books: [], config: null, warnings: [], schema_version: 1 }));
    mount();
    fireEvent.click(screen.getAllByText("选择文件")[0]);
    await act(async () => {});
    expect(fetchMock).not.toHaveBeenCalled();
    expect((screen.getByText("下一步") as HTMLButtonElement).disabled).toBe(true);
  });

  it("书清单非数组 / 条目缺 name：不炸、不标重名（?? 兜底臂）", async () => {
    armBridge();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return okJson3({ books: [{ name: "星海拾遗", path: "p", source_zip: "z" }], config: null, warnings: [], schema_version: 1 });
      }
      // 非数组 → Array.isArray 假分支；下一轮再给「条目缺 name」形态
      return { ok: true, status: 200, json: async () => ({ not: "an array" }) };
    });
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    expect(screen.queryByText("与现有书目重名·将以副本恢复")).toBeNull();
  });

  it("书清单条目缺 name：按空名处理（b.name ?? \"\" 兜底臂）", async () => {
    armBridge();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return okJson3({ books: [{ name: "星海拾遗", path: "p", source_zip: "z" }], config: null, warnings: [], schema_version: 1 });
      }
      return { ok: true, status: 200, json: async () => [{ path: "p" }] }; // 无 name 字段
    });
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
  });

  it("config 存在但无 api_configs：按 0 项渲染（?. ?? 兜底臂）", async () => {
    armBridge();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return okJson3({
          books: [],
          config: { format_version: 1, user: { display_name: "我" } }, // 无 api_configs
          warnings: [],
          schema_version: 1,
        });
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("模型配置（0 项）")).toBeTruthy());
  });

  it("只恢复配置包（0 本书）：完成页主叙事走「模型配置已恢复」分支", async () => {
    armBridge();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return okJson3({ books: [{ name: "书", path: "p", source_zip: "z" }], config: null, warnings: [], schema_version: 1 });
      }
      if (String(url).includes("/backup/import/persist")) {
        // 只选了配置包 → results 为空（okCount === 0），主叙事 = 模型配置已恢复
        return okJson3({ results: [], warnings: [], reattach: { mode: "auto", attached: 1 } });
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    fireEvent.click(screen.getByText("确认恢复"));
    await waitFor(() => expect(screen.getByText("模型配置已恢复")).toBeTruthy());
    // 注：`okCount === 0` 时即使有失败明细也显示「模型配置已恢复」，文案与实际不符
    // —— 属产品取舍，已登记在 docs/quality/coverage-baseline-2026-09-18.md 的遗留项
  });

  it("配置接回数 > 0：显示「模型配置已接回（N 本）」", async () => {
    armBridge();
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return okJson3({ books: [{ name: "书", path: "p", source_zip: "z" }], config: null, warnings: [], schema_version: 1 });
      }
      if (String(url).includes("/backup/import/persist")) {
        return okJson3({ results: [{ book_id: "b1", status: "ok" }], warnings: [], reattach: { mode: "auto", attached: 2 } });
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    mount();
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    fireEvent.click(screen.getByText("确认恢复"));
    await waitFor(() => expect(screen.getByText(/模型配置已接回（2 本）/)).toBeTruthy());
  });

  it("恢复中（working）点遮罩：锁定不放行 onClose（step !== working 的假臂）", async () => {
    const onClose = vi.fn();
    armBridge();
    let releasePersist: ((v: unknown) => void) | undefined;
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return okJson3({ books: [{ name: "书", path: "p", source_zip: "z" }], config: null, warnings: [], schema_version: 1 });
      }
      if (String(url).includes("/backup/import/persist")) {
        return new Promise((res) => {
          releasePersist = res;
        }) as Promise<unknown>;
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    render(<RestoreModal open onClose={onClose} onGoConfig={vi.fn()} />);
    await pickAssets();
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    fireEvent.click(screen.getByText("确认恢复"));
    await waitFor(() => expect(screen.getByText("恢复中…")).toBeTruthy());
    fireEvent.click(document.querySelector(".scrim") as HTMLElement);
    expect(onClose).not.toHaveBeenCalled(); // working 步锁关闭
    await act(async () => {
      releasePersist?.(okJson3({ results: [], warnings: [], reattach: { mode: "none", attached: 0 } }));
    });
  });
});

// ---------------------------------------------------------------------------
// 覆盖补齐（覆盖率专项）：浏览器模式手动输入路径（无原生文件弹窗的 B/S 兜底）
// —— 键盘 Enter 与「填入作品包」按钮两条路，含各自「空值不生效」的假臂
// ---------------------------------------------------------------------------

describe("RestoreModal 手动路径输入（浏览器模式兜底）", () => {
  const nextBtn = () => screen.getByText("下一步") as HTMLButtonElement;
  const manualInput = () =>
    screen.getByPlaceholderText("或输入文件完整路径（浏览器模式）") as HTMLInputElement;

  it("输入框 Enter 填入路径；非 Enter 键与纯空白输入不生效", async () => {
    mount();
    // 非 Enter 键：不填入（if e.key === "Enter" 的假臂）
    fireEvent.change(manualInput(), { target: { value: "/tmp/kb.zip" } });
    fireEvent.keyDown(manualInput(), { key: "a" });
    expect(nextBtn().disabled).toBe(true);
    // 纯空白 + Enter：裁剪后为空，不填入（if v 的假臂）
    fireEvent.change(manualInput(), { target: { value: "   " } });
    fireEvent.keyDown(manualInput(), { key: "Enter" });
    expect(nextBtn().disabled).toBe(true);
    // 有效路径 + Enter：填入作品包，主按钮解除禁用
    fireEvent.change(manualInput(), { target: { value: "/tmp/kb.zip" } });
    fireEvent.keyDown(manualInput(), { key: "Enter" });
    await waitFor(() => expect(nextBtn().disabled).toBe(false));
  });

  it("「填入作品包」按钮：填入裁剪后的路径；空白输入点击不生效", async () => {
    mount();
    // 空白输入点击：不填入（if v 的假臂）
    fireEvent.change(manualInput(), { target: { value: "   " } });
    fireEvent.click(screen.getByText("填入作品包"));
    expect(nextBtn().disabled).toBe(true);
    // 有效路径点击：填入并裁剪首尾空白（Slot 里展示裁剪结果）
    fireEvent.change(manualInput(), { target: { value: "  /tmp/manual.zip  " } });
    fireEvent.click(screen.getByText("填入作品包"));
    await waitFor(() => expect(nextBtn().disabled).toBe(false));
    expect(screen.getByText("/tmp/manual.zip")).toBeTruthy();
  });
});
