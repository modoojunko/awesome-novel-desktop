// ProjectShell：软删/不存在的书 404 → 回书架并说明；其余失败仍留在工作台（不误踢）。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ProjectShell } from "@/components/novel/license/ProjectShell";

const apiState = vi.hoisted(() => ({ get: vi.fn() }));
const toastState = vi.hoisted(() => ({ info: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

function mount() {
  return render(
    <MemoryRouter initialEntries={["/novel/p-del"]}>
      <Routes>
        <Route
          path="/novel/:id"
          element={
            <ProjectShell>
              <div data-testid="child" />
            </ProjectShell>
          }
        />
        <Route path="/" element={<div data-testid="shelf" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiState.get.mockReset();
  toastState.info.mockReset();
});

describe("ProjectShell 软删书", () => {
  it("404：提示并回书架，不渲染空工作台", async () => {
    apiState.get.mockRejectedValue(
      Object.assign(new Error("Novel not found"), { status: 404 }),
    );
    mount();
    await waitFor(() => expect(screen.getByTestId("shelf")).toBeTruthy());
    expect(toastState.info).toHaveBeenCalledWith("作品不存在或已删除");
    expect(screen.queryByTestId("child")).toBeNull();
  });

  it("非 404 失败：留在原地，不误踢回书架", async () => {
    apiState.get.mockRejectedValue(new Error("网络连接失败，请重试"));
    mount();
    await waitFor(() => expect(apiState.get).toHaveBeenCalled());
    expect(screen.getByTestId("child")).toBeTruthy();
    expect(screen.queryByTestId("shelf")).toBeNull();
    expect(toastState.info).not.toHaveBeenCalled();
  });
});
