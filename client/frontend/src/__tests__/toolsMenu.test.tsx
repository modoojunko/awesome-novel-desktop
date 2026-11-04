// ToolsMenu（c-deconstruct-book 5.1）：徽标口径、三项菜单（任务清单/拆书/知识库）＋扩展位、Esc/点外收起。
// c-charlib-into-kb：角色库项退役（角色实例进知识库「角色设定」视角）。
// c-tools-badge-seen：已完成未取任务「看过不再引导」——本地账里已看的 id 不计数，新 id 重亮。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/lib/deconstructApi", () => ({
  listDeconstructTasks: state.list,
  deleteDeconstructTask: vi.fn(), // TaskListPage 同挂载集成用（评审 P2 实时性用例）
}));

import ToolsMenu from "@/components/tools/ToolsMenu";
import TaskListPage from "@/components/tools/TaskListPage";

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
  localStorage.clear();
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
    // 第三项：知识库（c-charlib-into-kb：角色库项退役，角色收在知识库 desc 里）
    expect(screen.getByText("知识库")).toBeInTheDocument();
    expect(screen.getByText("拆书拆出的好写法和收进来的角色，写新书时能用上")).toBeInTheDocument();
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
    // 知识库菜单项点击 → 导航 /tools/kb（go 分支；c-knowledge-base）
    fireEvent.click(screen.getByText("写作工具"));
    expect(screen.getByText("知识库")).toBeInTheDocument();
    fireEvent.click(screen.getByText("知识库"));
    expect(screen.queryByText("任务清单")).not.toBeInTheDocument();
  });

  it("有任务显示徽标计数；菜单项点击导航并收起", async () => {
    state.list.mockResolvedValue({
      tasks: [
        { id: "t1", status: "running" },
        { id: "t2", status: "completed", unpicked: true },
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

  it("已完成未取任务看过后不再引导（只计活跃态）；新任务完成重亮", async () => {
    state.list.mockResolvedValue({
      tasks: [
        { id: "t1", status: "running" },
        { id: "t2", status: "completed", unpicked: true },
      ],
      heartbeat: { running: 1, queued: 0 },
      badge: 2,
    });
    // 预置本地账：t2 已看过 → 徽标只剩活跃态 t1
    localStorage.setItem("tools_badge_seen_v1", JSON.stringify(["t2"]));
    renderMenu();
    await waitFor(() => expect(screen.getAllByText("1").length).toBeGreaterThan(0));
    cleanup();
    // 新任务完成＝没看过的 id → 引导重亮（新挂载重取，React Query 缓存不背旧数据）
    state.list.mockResolvedValue({
      tasks: [
        { id: "t1", status: "running" },
        { id: "t2", status: "completed", unpicked: true },
        { id: "t3", status: "completed", unpicked: true },
      ],
      heartbeat: { running: 1, queued: 0 },
      badge: 3,
    });
    renderMenu();
    await waitFor(() => expect(screen.getAllByText("2").length).toBeGreaterThan(0));
  });

  it("清单页消账后徽标当场归零——同挂载订阅广播，无任何交互（评审 P2）；重启重亮", async () => {
    // 全终态任务：轮询停表＋focus 重取关闭——徽标归零只能靠账变广播（非订阅实现停死在 2）
    state.list.mockResolvedValue({
      tasks: [
        { id: "t2", status: "completed", unpicked: true, book_name: "星海远征" },
        { id: "t3", status: "completed", unpicked: true, book_name: "万川归海" },
      ],
      heartbeat: { running: 0, queued: 0 },
      badge: 2,
    });
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ToolsMenu />
          <TaskListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("万川归海")).toBeInTheDocument()); // 清单回包
    await waitFor(() => expect(screen.queryByText("2")).not.toBeInTheDocument()); // 消账即时生效
    expect(JSON.parse(localStorage.getItem("tools_badge_seen_v1") ?? "[]")).toEqual(["t2", "t3"]);
    cleanup();
    // 重启（重挂载）后新任务完成＝没看过的 id → 引导重亮
    state.list.mockResolvedValue({
      tasks: [
        { id: "t2", status: "completed", unpicked: true },
        { id: "t4", status: "completed", unpicked: true },
      ],
      heartbeat: { running: 0, queued: 0 },
      badge: 1,
    });
    renderMenu();
    await waitFor(() => expect(screen.getAllByText("1").length).toBeGreaterThan(0));
  });

  it("徽标口径只认 unpicked 标记：已建书/已导出（无 unpicked） completed 不计数", async () => {
    state.list.mockResolvedValue({
      tasks: [
        { id: "c1", status: "completed" }, // 已取（无 unpicked）
        { id: "c2", status: "imported" }, // 已建书
        { id: "c3", status: "import_failed", unpicked: true }, // 建书失败仍引导
        { id: "q1", status: "queued" },
      ],
      heartbeat: { running: 0, queued: 1 },
      badge: 3,
    });
    renderMenu();
    await waitFor(() => expect(screen.getAllByText("2").length).toBeGreaterThan(0)); // q1＋c3
  });
});
