// ToolsMenu（c-deconstruct-book 5.1）：徽标口径、三项菜单（任务清单/拆书/角色库）＋扩展位、Esc/点外收起。
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
  it("无任务：无徽标；展开显三项＋扩展位；Esc 收起；点外收起", async () => {
    state.list.mockResolvedValue({ tasks: [], heartbeat: { running: 0, queued: 0 }, badge: 0 });
    renderMenu();
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("写作工具"));
    expect(screen.getByText("任务清单")).toBeInTheDocument();
    expect(screen.getByText("拆书")).toBeInTheDocument();
    // 第三项：角色库（c-character-library）
    expect(screen.getByText("角色库")).toBeInTheDocument();
    expect(screen.getByText("书里的角色收进来，换本小说改个名字接着用")).toBeInTheDocument();
    expect(screen.getByText("更多写作工具陆续上线")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Enter" }); // 非 Esc 键不关（假臂）
    expect(screen.getByText("任务清单")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument(); // （document 级监听）
    fireEvent.click(screen.getByText("写作工具"));
    // 菜单内 mousedown 不收起（点外面才收）
    fireEvent.mouseDown(screen.getByText("任务清单"));
    expect(screen.getByText("任务清单")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
    // 拆书菜单项点击 → 导航创建页（go 分支）
    fireEvent.click(screen.getByText("写作工具"));
    fireEvent.click(screen.getByText("拆书"));
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
    // 角色库菜单项点击 → 导航 /tools/characters（go 分支；c-character-library）
    fireEvent.click(screen.getByText("写作工具"));
    fireEvent.click(screen.getByText("角色库"));
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
  });

  it("有任务显示徽标计数；菜单项点击导航并收起", async () => {
    state.list.mockResolvedValue({
      tasks: [
        { id: "t1", status: "running" },
        { id: "t2", status: "completed" },
      ],
      heartbeat: { running: 1, queued: 0 },
      badge: 2,
    });
    renderMenu();
    await waitFor(() => expect(screen.getAllByText("2").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText("写作工具"));
    expect(screen.getAllByText("2").length).toBeGreaterThanOrEqual(2); // 触发钮＋菜单行内
    fireEvent.click(screen.getByText("任务清单"));
    // MemoryRouter 下 navigate 生效（无路由匹配则空渲染，不断言 URL）
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument(); // 选完收起
  });
});
