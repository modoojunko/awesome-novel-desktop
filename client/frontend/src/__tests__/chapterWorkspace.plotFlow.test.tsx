// 章剧情全链集成（c-plot-split 5.3/5.4）：门槛拦截（缺要素不发请求）／采纳整表替换＋
// 常驻回执／撤销只回滚 plots／编辑收掉回执／已润色章改剧情软提示／免费态锁定卡。
// 打桩层＝`@/lib/api`＋`@/lib/toast`（toast 断言回执与撤销语义）。
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  request: vi.fn(),
}));
vi.mock("@/lib/toast", () => ({
  toast: {
    success: vi.fn(() => 101),
    error: vi.fn(() => 102),
    info: vi.fn(() => 103),
    dismiss: vi.fn(),
  },
  useToasts: () => [],
  Toaster: () => null,
}));

import { api, request } from "@/lib/api";
import { toast } from "@/lib/toast";
import ChapterWorkspace from "@/components/novel/workbench/ChapterWorkspace";
import { INITIAL_PROSE_AI_STATE } from "@/components/novel/workbench/ProsePane";

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};
const mockReq = request as unknown as ReturnType<typeof vi.fn>;
const mockToast = toast as unknown as Record<string, ReturnType<typeof vi.fn>>;

const REF = "vol-1-ch-2";
const THREE = {
  ok: true,
  versions: [
    { items: ["起——接进场", "中段甲", "止——收章末"] },
    { items: ["起——接进场", "中段乙", "止——收章末"] },
    { items: ["起——接进场", "中段丙", "止——收章末"] },
  ],
  grades: ["S", "A", "B"],
  warnings: [],
};

/** outline/wb 最小桩：saveChapter 写回 chaptersMap（门槛读服务端值的依据） */
function makeOutline(server: Record<string, unknown>) {
  const map = new Map<string, any>([[REF, server]]);
  return {
    volumes: [
      { ref: "vol-1", title: "第一卷", chapters: [{ chapter: 2, title: "锚点", archived: false, has_prose: true, word_count: 10 }] },
    ],
    chaptersMap: map,
    loadChapterData: vi.fn(async (ref: string) => map.get(ref)),
    saveChapter: vi.fn(async (ref: string, data: Record<string, any>) => {
      const cur = map.get(ref) ?? { volume: 1, chapter: 2, title: "锚点", status: "draft" };
      map.set(ref, {
        ...cur,
        ...data,
        outline: { ...(cur.outline ?? {}), ...(data.outline ?? {}) },
      });
      return {};
    }),
    confirmChapter: vi.fn(async () => {}),
    unconfirmChapter: vi.fn(async () => {}),
    refetchTree: vi.fn(async () => {}),
  };
}

const wb = {
  volumes: [
    { name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] },
  ],
  refresh: vi.fn(async () => {}),
};

/** 挂载 ChapterWorkspace，捕获右栏数据（onPlotDraw 从这里触发） */
function mount(opts: {
  server: Record<string, unknown>;
  isPro?: boolean;
  onOpenAiModal?: () => void;
  /** 树行归档态（c-archived-readonly）：true＝本章已归档 */
  archived?: boolean;
}) {
  const outline = makeOutline(opts.server);
  // 每次挂载新建 wb 桩：归档态按用例覆写，不污染模块级 wb
  const wbStub = {
    ...wb,
    volumes: [
      {
        name: "vol-1",
        chapters: [{ chapter: 2, title: "锚点", archived: opts.archived ?? false }],
      },
    ],
  };
  let rail: any = null;
  render(
    <MemoryRouter>
      <ChapterWorkspace
        projectId="p1"
        chapterRef={REF}
        outline={outline as never}
        wb={wbStub as never}
        isPro={opts.isPro ?? true}
        proseRef={createRef()}
        aiState={INITIAL_PROSE_AI_STATE}
        onAIStateChange={() => {}}
        bookWords={10}
        onRailData={(d) => {
          rail = d;
        }}
        aiWriteSignal={0}
        onRevert={() => {}}
        onTreeRefresh={async () => {}}
        onOpenAiModal={opts.onOpenAiModal}
      />
    </MemoryRouter>,
  );
  return { outline, railData: () => rail };
}

/** 章纲查看/编辑两态（c-ch-og-readonly）：表单交互先点「编辑章纲」进编辑态 */
async function enterOgEdit() {
  fireEvent.click(await screen.findByTestId("og-edit"));
}

/** 服务端三要素齐备的章（门槛放行） */
const FULL = {
  volume: 1,
  chapter: 2,
  title: "锚点",
  status: "draft",
  outline: { summary: "陆沉查舱段结构" },
  challenge: "旧档堆不对活人开放",
  ladder_exit: "拿到半张地图，连夜出门",
  plot_items: ["旧的手写剧情甲", "旧的手写剧情乙", ""],
  prose: "",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockToast.success.mockReturnValue(101);
  // 默认取数：章 payload + 角色列表 + 提示词探测 + 润色探测
  mockApi.get.mockImplementation(async (url: string) => {
    if (url.includes("/characters")) return [];
    return { ...FULL };
  });
  mockReq.mockResolvedValue({ polished: false });
});

describe("门槛拦截（拍板⑦三样：概要/挑战/结尾）", () => {
  it("缺「碰到的挑战」：拦住不发请求，提示可点去补填", async () => {
    const { railData } = mount({
      server: { ...FULL, challenge: "" },
    });
    await waitFor(() => expect(railData()).not.toBeNull());
    await act(async () => {
      await railData().onPlotDraw();
    });
    expect(mockApi.post).not.toHaveBeenCalled();
    expect(mockToast.error).toHaveBeenCalledWith(
      expect.stringContaining("「碰到的挑战」还没填"),
      expect.objectContaining({
        action: expect.objectContaining({ label: "去补填" }),
      }),
    );
  });

  it("三要素齐备才开抽（发出 plot/ai-draw 请求）", async () => {
    mockApi.post.mockResolvedValue(THREE);
    const { railData } = mount({ server: { ...FULL } });
    await waitFor(() => expect(railData()).not.toBeNull());
    await act(async () => {
      await railData().onPlotDraw();
    });
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith(
        `/novels/p1/chapters/${REF}/plot/ai-draw`,
        {},
      ),
    );
  });

  it("补完最后一格立即点抽卡不误拦（flush 成功读表单值，评审 P2）", async () => {
    mockApi.post.mockResolvedValue(THREE);
    const { railData } = mount({ server: { ...FULL, challenge: "" } });
    await waitFor(() => expect(railData()).not.toBeNull());
    // 进编辑态（默认查看态），等表单载入（剧情行回显）再补挑战，模拟「填完立刻点」的主流程
    await enterOgEdit();
    await waitFor(() =>
      expect(screen.getByLabelText("第 1 条剧情")).toHaveValue("旧的手写剧情甲"),
    );
    fireEvent.change(document.getElementById("wf-challenge")!, {
      target: { value: "刚补上的挑战" },
    });
    await act(async () => {
      await railData().onPlotDraw();
    });
    // 不误拦：直接开抽（无「还没填」拦截 toast）
    expect(mockToast.error).not.toHaveBeenCalledWith(
      expect.stringContaining("「碰到的挑战」还没填"),
      expect.anything(),
    );
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith(
        `/novels/p1/chapters/${REF}/plot/ai-draw`,
        {},
      ),
    );
  });
});

describe("采纳与撤销（拍板②）", () => {
  it("就填这版＝整表替换＋常驻回执；撤销只回滚 plots", async () => {
    mockApi.post.mockResolvedValue(THREE);
    const { railData, outline } = mount({ server: { ...FULL } });
    await waitFor(() => expect(railData()).not.toBeNull());
    await enterOgEdit();
    await act(async () => {
      await railData().onPlotDraw();
    });
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    // 采纳按钮明示「将替换已写的 2 条」（非空 2 条）
    const adopt = screen.getByTestId("plot-adopt");
    expect(adopt).toHaveTextContent("将替换已写的 2 条");
    fireEvent.click(screen.getByTestId("plot-card-1"));
    fireEvent.click(adopt);
    await waitFor(() =>
      expect(outline.saveChapter).toHaveBeenCalledWith(
        REF,
        expect.objectContaining({ plot_items: THREE.versions[1].items }),
      ),
    );
    // 回执常驻（sticky）＋带撤销动作
    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringContaining("剧情已由 AI 填好（3 条）"),
      expect.objectContaining({
        sticky: true,
        action: expect.objectContaining({ label: "撤销 · 恢复填写前的列表" }),
      }),
    );
    // 撤销：恢复填写前列表（含非空）
    const undo = mockToast.success.mock.calls.at(-1)![1].action;
    act(() => undo.onClick());
    expect(mockToast.info).toHaveBeenCalledWith(
      expect.stringContaining("已恢复到 AI 填写前的列表"),
    );
    // 只回滚 plots：中栏剧情行回旧内容，其它格子不动（概要还在）
    await waitFor(() =>
      expect(screen.getByLabelText("第 1 条剧情")).toHaveValue("旧的手写剧情甲"),
    );
    expect(screen.getByLabelText("第 2 条剧情")).toHaveValue("旧的手写剧情乙");
    expect(outline.saveChapter).toHaveBeenLastCalledWith(
      REF,
      expect.not.objectContaining({ challenge: "" }),
    );
  });

  it("编辑任一条目即收掉回执（toast.dismiss）", async () => {
    mockApi.post.mockResolvedValue(THREE);
    const { railData } = mount({ server: { ...FULL } });
    await waitFor(() => expect(railData()).not.toBeNull());
    await enterOgEdit();
    await act(async () => {
      await railData().onPlotDraw();
    });
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("plot-card-0"));
    fireEvent.click(screen.getByTestId("plot-adopt"));
    await waitFor(() => expect(mockToast.success).toHaveBeenCalled());
    expect(mockToast.dismiss).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("第 1 条剧情"), {
      target: { value: "改一条" },
    });
    expect(mockToast.dismiss).toHaveBeenCalledWith(101);
  });

  it("采纳保存失败：弹层留在原地、选中版还在，可直接重试（评审 P3）", async () => {
    mockApi.post.mockResolvedValue(THREE);
    const { railData, outline } = mount({ server: { ...FULL } });
    await waitFor(() => expect(railData()).not.toBeNull());
    await enterOgEdit();
    await act(async () => {
      await railData().onPlotDraw();
    });
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("plot-card-0"));
    outline.saveChapter.mockRejectedValueOnce(new Error("boom"));
    fireEvent.click(screen.getByTestId("plot-adopt"));
    await waitFor(() =>
      expect(mockToast.error).toHaveBeenCalledWith("章纲保存失败，请重试"),
    );
    // 弹层未关：候选与选中都在，无需重抽
    expect(screen.getByTestId("plot-grid")).toBeInTheDocument();
    expect(screen.getByTestId("plot-card-0")).toHaveClass("on");
    // 重试（saveChapter 已恢复 resolve）：落库＋回执照常
    fireEvent.click(screen.getByTestId("plot-adopt"));
    await waitFor(() =>
      expect(outline.saveChapter).toHaveBeenLastCalledWith(
        REF,
        expect.objectContaining({ plot_items: THREE.versions[0].items }),
      ),
    );
    await waitFor(() =>
      expect(mockToast.success).toHaveBeenCalledWith(
        expect.stringContaining("剧情已由 AI 填好（3 条）"),
        expect.anything(),
      ),
    );
  });
});

describe("已润色章改剧情软提示（拍板⑥）", () => {
  it("润色产物＋剧情被编辑 → 软提示带「去重新润色」出口，不自动重算", async () => {
    mockReq.mockResolvedValue({ polished: true });
    const onOpenAiModal = vi.fn();
    const { railData } = mount({ server: { ...FULL }, onOpenAiModal });
    await waitFor(() => expect(railData()).not.toBeNull());
    await enterOgEdit();
    fireEvent.change(screen.getByLabelText("第 1 条剧情"), {
      target: { value: "新剧情" },
    });
    await waitFor(
      () =>
        expect(mockToast.info).toHaveBeenCalledWith(
          expect.stringContaining("可以重新润色"),
          expect.objectContaining({
            action: expect.objectContaining({ label: "去重新润色" }),
          }),
        ),
      { timeout: 3000 },
    );
    // 不自动重算：没有发出任何生成请求
    expect(mockApi.post).not.toHaveBeenCalled();
    // 出口可点
    const action = mockToast.info.mock.calls.at(-1)![1].action;
    act(() => action.onClick());
    expect(onOpenAiModal).toHaveBeenCalled();
  });

  it("非润色提示词（粗组稿）不提示", async () => {
    mockReq.mockResolvedValue({ polished: false });
    const { railData } = mount({ server: { ...FULL } });
    await waitFor(() => expect(railData()).not.toBeNull());
    await enterOgEdit();
    fireEvent.change(screen.getByLabelText("第 1 条剧情"), {
      target: { value: "新剧情" },
    });
    await waitFor(() => expect(mockReq).toHaveBeenCalled(), { timeout: 3000 });
    await new Promise((r) => setTimeout(r, 100));
    expect(mockToast.info).not.toHaveBeenCalledWith(
      expect.stringContaining("可以重新润色"),
      expect.anything(),
    );
  });
});

describe("头部 meta 行（2026-09-27 章纲统计自右栏 AI 助手上移）", () => {
  it("e-meta 展示归档门槛/剧情/出场角色（计划字数/完成度/总字数迁页签行，c-workbench-density）；seg 退役、版本历史在页签行、归档在操作页签", async () => {
    mount({
      server: {
        ...FULL,
        memo: { required_changes: ["旧契作废"] },
        emotional_design: { primary_mood: "压抑" },
      },
    });
    await waitFor(() =>
      expect(document.querySelector(".e-meta")?.textContent).toContain("归档门槛 2/2"),
    );
    const meta = document.querySelector(".e-meta")?.textContent ?? "";
    expect(meta).toContain("剧情 2 条");
    expect(meta).toContain("出场角色 0 人");
    // 三枚重复徽章退役：完成度/总字数唯一承载位＝页签行 ch-progress
    expect(meta).not.toContain("计划字数");
    expect(meta).not.toContain("完成度");
    expect(meta).not.toContain("本书总字数");
    expect(document.querySelector(".ch-tabs .ch-progress")?.textContent).toContain("完成度");
    // 字号/行距 seg 退役（改值入口在账号菜单「本书偏好」）
    expect(document.querySelector(".e-head .seg")).toBeNull();
    // 版本历史入口移页签行右端（不在头部右侧）
    expect(document.querySelector(".e-head .ch-history")).toBeNull();
    expect(document.querySelector(".ch-tabs .ch-history")?.textContent).toContain("版本历史");
    // 归档入口移操作页签：默认章纲页签下头部无归档按钮
    expect(screen.queryByRole("button", { name: "归档本章" })).toBeNull();
  });
});

describe("保存草稿不确认＋撤回确认（c-og-draft-no-autconfirm）", () => {
  it("保存草稿只落库：confirmChapter 零调用，toast 恒「草稿已保存」", async () => {
    const { outline } = mount({ server: { ...FULL } });
    await enterOgEdit();
    fireEvent.click(await screen.findByRole("button", { name: "保存草稿" }));
    await waitFor(() =>
      expect(mockToast.success).toHaveBeenCalledWith("草稿已保存"),
    );
    expect(outline.saveChapter).toHaveBeenCalled();
    // 旧「无缺项自动确认」退役：保存草稿不得触发确认端点
    expect(outline.confirmChapter).not.toHaveBeenCalled();
  });

  it("已确认章查看态「撤回确认」→ 弹窗确认 → unconfirmChapter＋refetchTree＋toast", async () => {
    const server = { ...FULL, status: "confirmed" };
    const { outline } = mount({ server });
    // 已确认徽标在场（无缺口），撤回入口仅确认态出现
    const btn = await screen.findByTestId("og-unconfirm");
    fireEvent.click(btn);
    // 弹窗双出口：先「保留确认」不触发
    fireEvent.click(await screen.findByText("保留确认"));
    expect(outline.unconfirmChapter).not.toHaveBeenCalled();
    // 再开 →「撤回」触发全链；撤回后 reloadStatus 读同一对象（现回 draft）决定 toast
    server.status = "draft";
    fireEvent.click(await screen.findByTestId("og-unconfirm"));
    fireEvent.click(await screen.findByTestId("og-unconfirm-go"));
    await waitFor(() =>
      expect(mockToast.success).toHaveBeenCalledWith("已撤回确认，章纲回到草稿态"),
    );
    expect(outline.unconfirmChapter).toHaveBeenCalledWith(REF);
    expect(outline.refetchTree).toHaveBeenCalled();
  });
});

describe("归档章章纲只读（c-archived-readonly）", () => {
  it("归档章停在章纲页签：横幅（小改「恢复编辑」＋重写指路）在场，动作区四入口不在场，一页纸本体保留", async () => {
    mount({ server: { ...FULL, status: "confirmed" }, archived: true });
    expect(await screen.findByTestId("og-view")).toBeInTheDocument();
    // 状态机终态徽：页签条章纲 chip＝「已归档」（不报草稿/缺项/已确认）
    expect(document.querySelector(".ch-tabs .cnt")?.textContent).toBe("已归档");
    // 面板头徽同口径（og-view 内唯一「已归档」）
    expect(within(screen.getByTestId("og-view")).getByText("已归档")).toBeInTheDocument();
    // 横幅（正文/章纲两页签同款）：小改路径＝「恢复编辑」出口，整体重写指路「重写本章」
    expect(screen.getByText(/本章已归档/)).toBeInTheDocument();
    expect(screen.getByText(/重写本章/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "恢复编辑" })).toBeInTheDocument();
    // 动作区整排不提供（确认/撤回对归档章后端本就 409），解锁后才恢复
    expect(screen.queryByRole("button", { name: "确认章纲" })).toBeNull();
    expect(screen.queryByRole("button", { name: "去写正文" })).toBeNull();
    expect(screen.queryByTestId("og-edit")).toBeNull();
    expect(screen.queryByTestId("og-unconfirm")).toBeNull();
    // 一页纸本体仍在（只读呈现，不白屏）
    expect(screen.getByTestId("og-view")).toBeInTheDocument();
  });

  it("归档章点缺口 chip 不进编辑态（编辑入口哑火，无保存草稿表单）", async () => {
    mount({ server: { ...FULL }, archived: true });
    expect(await screen.findByTestId("og-view")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "必须完成的变化" }));
    // 仍在查看态：编辑态的保存草稿按钮不在场
    expect(screen.queryByRole("button", { name: "保存草稿" })).toBeNull();
    expect(screen.getByTestId("og-view")).toBeInTheDocument();
  });
});
