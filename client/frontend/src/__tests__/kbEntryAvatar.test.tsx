// 知识库条目头像（角色设定）：有字节出图；无字节出姓氏 SVG 占位（列表恒有框）。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ fetchLibraryAvatar: vi.fn() }));

vi.mock("@/lib/libraryApi", async (orig) => ({
  ...(await orig<typeof import("@/lib/libraryApi")>()),
  fetchLibraryAvatar: api.fetchLibraryAvatar,
}));

import KbEntryAvatar from "@/components/tools/KbEntryAvatar";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KbEntryAvatar", () => {
  it("无头像字节：姓氏 SVG 占位，不发请求", () => {
    render(<KbEntryAvatar entry={{ id: "e1", title: "刘望津" }} />);
    expect(screen.getByTestId("kb-entry-avatar-fallback").textContent).toContain("刘");
    expect(api.fetchLibraryAvatar).not.toHaveBeenCalled();
  });

  it("空标题兜底「角」", () => {
    render(<KbEntryAvatar entry={{ id: "e2", title: "   " }} />);
    expect(screen.getByTestId("kb-entry-avatar-fallback").textContent).toContain("角");
  });

  it("有头像：按条目 id 拉字节出图", async () => {
    api.fetchLibraryAvatar.mockResolvedValue("blob:1");
    render(<KbEntryAvatar entry={{ id: "e3", title: "刘望津", has_avatar: true }} />);
    await waitFor(() => expect(screen.getByTestId("kb-entry-avatar-img")).toBeTruthy());
    const ref = api.fetchLibraryAvatar.mock.calls[0][0];
    expect(ref.id).toBe("e3");
    expect(ref.avatar.thumb_url).toBe("/api/character-library/e3/avatar?variant=thumb");
  });

  it("拉取失败：回落姓氏占位", async () => {
    api.fetchLibraryAvatar.mockRejectedValue(new Error("404"));
    render(<KbEntryAvatar entry={{ id: "e4", title: "周沉舟", has_avatar: true }} />);
    await waitFor(() =>
      expect(screen.getByTestId("kb-entry-avatar-fallback").textContent).toContain("周"),
    );
  });

  it("标题为空串：同样兜底「角」", () => {
    render(<KbEntryAvatar entry={{ id: "e6", title: "" }} />);
    expect(screen.getByTestId("kb-entry-avatar-fallback").textContent).toContain("角");
  });

  it("卸载后失败返回不更新（catch 的 alive=false 分支）", async () => {
    let reject!: (e: Error) => void;
    api.fetchLibraryAvatar.mockImplementation(
      () => new Promise<string>((_r, j) => { reject = j; }),
    );
    const { unmount } = render(
      <KbEntryAvatar entry={{ id: "e7", title: "董少游", has_avatar: true }} />,
    );
    unmount();
    reject(new Error("late"));
    await Promise.resolve();
    expect(screen.queryByTestId("kb-entry-avatar-fallback")).toBeNull();
  });

  it("卸载后返回不当场更新（alive=false 分支）", async () => {
    let resolve!: (v: string) => void;
    api.fetchLibraryAvatar.mockImplementation(
      () => new Promise<string>((r) => { resolve = r; }),
    );
    const { unmount } = render(
      <KbEntryAvatar entry={{ id: "e5", title: "谢逐月", has_avatar: true }} />,
    );
    unmount();
    resolve("blob:late");
    await Promise.resolve();
    expect(screen.queryByTestId("kb-entry-avatar-img")).toBeNull();
  });
});
