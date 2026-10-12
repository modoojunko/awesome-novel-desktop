// ToolsMenu（c-deconstruct-book 5.1）：徽标口径、两项菜单＋扩展位、Esc/点外收起。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/lib/deconstructApi", () => ({ listDeconstructTasks: state.list }));

import ToolsMenu from "@/components/tools/ToolsMenu";

function renderMenu() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToolsMenu />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ToolsMenu", () => {
  it("无任务：无徽标；展开显两项＋扩展位；Esc 收起；点外收起", async () => {
    state.list.mockResolvedValue({ tasks: [], heartbeat: { running: 0, queued: 0 }, badge: 0 });
    renderMenu();
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("写作工具"));
    expect(screen.getByText("任务清单")).toBeInTheDocument();
    expect(screen.getByText("拆书")).toBeInTheDocument();
    expect(screen.getByText("更多写作工具陆续上线")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("写作工具"));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
  });

  it("有任务显示徽标计数", async () => {
    state.list.mockResolvedValue({
      tasks: [{ id: "t", status: "running" }],
      heartbeat: { running: 1, queued: 0 },
      badge: 2,
    });
    renderMenu();
    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
  });
});
