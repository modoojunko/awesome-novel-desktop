// 书工作台布局层（NovelLayout）契约（覆盖率专项·批 1 第二波）：
//   只做「项目上下文壳 + 子路由出口」——权益/鉴权已上移到 App 路由根壳（c-s-entitlement-sync）。
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import NovelLayout from "@/pages/NovelLayout";

vi.mock("@/components/novel/license/ProjectShell", () => ({
  ProjectShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="project-shell">{children}</div>
  ),
}));

describe("NovelLayout", () => {
  it("包在 ProjectShell 内并渲染子路由（Outlet）", () => {
    render(
      <MemoryRouter initialEntries={["/novel/n1"]}>
        <Routes>
          <Route path="/novel/:id" element={<NovelLayout />}>
            <Route index element={<div data-testid="child" />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    const shell = screen.getByTestId("project-shell");
    expect(shell).toBeTruthy();
    expect(screen.getByTestId("child")).toBeTruthy();
    expect(shell.contains(screen.getByTestId("child"))).toBe(true); // 子是壳的后代
  });
});
