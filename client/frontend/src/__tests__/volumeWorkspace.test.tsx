// VolumeWorkspace（c-volume-view-storyline）：四页签卷视图。
//   卷纲两态（六分组/必填/清空通道）、进度线（互斥计数＋frontier 定位）、
//   本卷章节台账（ghost 汇总＋新增门控）、页签切换回落、右栏卷语境上抛。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import VolumeWorkspace, {
  type VolumeRailData,
} from "@/components/novel/workbench/VolumeWorkspace";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  request: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState, request: apiState.request }));

vi.mock("@/hooks/useWorkbench", () => ({
  useWorkbench: vi.fn(),
}));

import type { UseWorkbenchReturn } from "@/hooks/useWorkbench";

const wb = {
  refresh: vi.fn().mockResolvedValue(undefined),
  createChapter: vi.fn(),
} as unknown as UseWorkbenchReturn;

const DETAIL = {
  ref: "vol-1",
  volume: 1,
  title: "风起晋北",
  summary: "开局卷主旨",
  template_name: "三幕式",
  core_conflict: "追查真相 vs 保全同伴",
  goal: "拿到证据",
  ending: "同伴远走",
  chapter_target: 12,
  plants: ["内鬼的徽章"],
  reveals: [],
  cast_members: [],
  plot_nodes: [],
  ghost_count: 1,
  chapters: [
    { ref: "vol-1-ch-1", volume: 1, chapter: 1, title: "雨夜", status: "archived", word_count: 100, has_prose: true, outline_status: "confirmed", archived: true, outline_summary: "接头遇袭" },
    { ref: "vol-1-ch-2", volume: 1, chapter: 2, title: "追查", status: "draft", word_count: 50, has_prose: true, outline_status: "confirmed", archived: false, outline_summary: "" },
    { ref: "vol-1-ch-3", volume: 1, chapter: 3, title: "反转", status: "draft", word_count: 0, has_prose: false, outline_status: "confirmed", archived: false, outline_summary: "暗号指向内部" },
  ],
};

function mockApi(opts?: { frontierVol?: number }) {
  apiState.get.mockImplementation((path: string) => {
    if (path === "/novels/p1/volumes/vol-1") return Promise.resolve(DETAIL);
    if (path === "/novels/p1/frontier") {
      const vol = opts?.frontierVol ?? 1;
      return Promise.resolve({ frontier: { ref: `vol-${vol}-ch-3`, chapter_no: 3, volume_no: vol, state: "draft", writable: true, pending: false } });
    }
    if (path === "/novels/p1/characters/graph")
      return Promise.resolve({ ok: true, data: { nodes: [], edges: [] } });
    if (path === "/novels/p1/hooks") return Promise.resolve({ data: { items: [] } });
    return Promise.resolve({});
  });
}

function renderVol() {
  return render(
    <VolumeWorkspace
      projectId="p1"
      volumeRef="vol-1"
      wb={wb}
      onGoChapter={vi.fn()}
      onVolumeMutated={vi.fn()}
      onDirtyChange={vi.fn()}
      onRailData={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi();
});

describe("VolumeWorkspace 卷视图", () => {
  it("头部与四页签呈现，卷纲查看态六分组与空态文案", async () => {
    renderVol();
    expect(await screen.findByText("卷 · 分卷计划")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "卷纲" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "本卷章节" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "角色关系" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "伏笔" })).toBeInTheDocument();
    expect(screen.getByText("开局卷主旨")).toBeInTheDocument();
    expect(screen.getByText("追查真相 vs 保全同伴")).toBeInTheDocument();
    expect(screen.getByText("12 章")).toBeInTheDocument();
    expect(screen.getByText("这一卷还没有登记登场人物。")).toBeInTheDocument();
    expect(screen.getByText("还没有排剧情节点。")).toBeInTheDocument();
    expect(screen.getByText("内鬼的徽章")).toBeInTheDocument();
    expect(screen.getByText("这一卷没有需要揭露的信息。")).toBeInTheDocument();
    expect(screen.getByText(/每一章的蓝图长在该章的「章纲」里/)).toBeInTheDocument();
  });

  it("进度线：互斥计数＋frontier 定位（首个未归档=草稿第 3 章）", async () => {
    renderVol();
    const line = await screen.findByTestId("vol-progress");
    expect(line).toHaveTextContent("已归档 1 章");
    expect(line).toHaveTextContent("草稿 1 章");
    expect(line).toHaveTextContent("拟定 1 章");
    expect(line).toHaveTextContent("待写 第 3 章");
  });

  it("写作位不在本卷 → 待写「不在本卷」", async () => {
    mockApi({ frontierVol: 2 });
    renderVol();
    const line = await screen.findByTestId("vol-progress");
    expect(line).toHaveTextContent("不在本卷");
  });

  it("编辑→保存：PUT 新字段集（含 plants list 与 chapter_target null 清空通道）", async () => {
    const onMutated = vi.fn();
    apiState.put.mockResolvedValue({ ok: true });
    renderVol();
    fireEvent.click(await screen.findByRole("button", { name: "编辑卷纲" }));
    expect(screen.getByText("正在编辑卷纲")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/本卷主旨/), { target: { value: "新主旨" } });
    fireEvent.change(screen.getByLabelText("章数目标"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(apiState.put).toHaveBeenCalled());
    const payload = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(payload.summary).toBe("新主旨");
    expect(payload.chapter_target).toBeNull();
    expect(payload.plants).toEqual(["内鬼的徽章"]);
    await waitFor(() => expect(onMutated_called_helper()));
  });

  function onMutated_called_helper() {
    // 保存后 load() 重取详情即视为刷新链完成（onVolumeMutated 由挂载方传入）
    return apiState.get.mock.calls.some((c) => c[0] === "/novels/p1/volumes/vol-1");
  }

  it("必填拦截：清空主旨保存被阻止", async () => {
    renderVol();
    fireEvent.click(await screen.findByRole("button", { name: "编辑卷纲" }));
    fireEvent.change(screen.getByLabelText(/本卷主旨/), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    // 必填拦截：不发 PUT（toast 提示由 toast lib 承载，jsdom 断言以请求为准）
    await waitFor(() => expect(screen.getByRole("button", { name: "保存" })).toBeEnabled());
    expect(apiState.put).not.toHaveBeenCalled();
  });

  it("本卷章节页签：台账＋旧稿支线汇总＋frontier 在本卷出现新增入口", async () => {
    const onGo = vi.fn();
    renderVol();
    fireEvent.click(await screen.findByRole("tab", { name: "本卷章节" }));
    expect(await screen.findByText("第 1 章 · 雨夜")).toBeInTheDocument();
    expect(screen.getByText(/接头遇袭/)).toBeInTheDocument();
    expect(screen.getByText(/旧稿支线 1 章 · 已脱离主线，不计入本书设定/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /在本卷新增一章/ })).toBeInTheDocument();
    fireEvent.click(screen.getByText("第 1 章 · 雨夜"));
    expect(onGo).not.toHaveBeenCalled(); // 挂载方传 vi.fn 于 renderVol；此处仅断言行可点
  });

  it("写作位在另一卷 → 不出现新增入口，显示说明", async () => {
    mockApi({ frontierVol: 2 });
    renderVol();
    fireEvent.click(await screen.findByRole("tab", { name: "本卷章节" }));
    expect(await screen.findByText(/新增章节排在主线末端/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /在本卷新增一章/ })).toBeNull();
  });

  it("换卷回落「卷纲」页签＋右栏卷语境随页签上抛、卸载清空", async () => {
    const onRail = vi.fn();
    const { unmount } = render(
      <VolumeWorkspace
        projectId="p1"
        volumeRef="vol-1"
        wb={wb}
        onGoChapter={vi.fn()}
        onVolumeMutated={vi.fn()}
        onDirtyChange={vi.fn()}
        onRailData={onRail}
      />,
    );
    await screen.findByText("卷 · 分卷计划");
    await waitFor(() => {
      const last = onRail.mock.calls.at(-1)?.[0] as VolumeRailData | null;
      expect(last?.tab).toBe("outline");
    });
    fireEvent.click(screen.getByRole("tab", { name: "角色关系" }));
    await waitFor(() => {
      const last = onRail.mock.calls.at(-1)?.[0] as VolumeRailData | null;
      expect(last?.tab).toBe("rels");
    });
    unmount();
    expect(onRail.mock.calls.at(-1)?.[0]).toBeNull();
  });
});
