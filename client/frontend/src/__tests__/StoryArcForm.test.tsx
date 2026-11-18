import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// StoryArcForm — 主线面板（storyline-settings-v2：全景 fullstory + 结局三问）
// - 挂载拉卡回显（legacy premise 归一进 fullstory）；保存走 PUT
// - 结局三问：三输入框（问题句为 label、例句进占位符）；基调自由输入
// - 无分卷区、无基调选择题（tone-opt 退役）；textarea 无 maxLength（600 软上限）
// - 行内「AI 帮我填」：结果进弹窗出卡（arc-ai-card）、确认才写回、在途互斥、免费拦截
// - AI 四能力 runAi 句柄：draft/calibrate/check 统一进弹窗出卡（c-settings-ai-confirm-modal：
//   关闭即弃；缓存重开免请求 D9；「换一个」version+1 且在途旧版保持可读 D3）
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  fetchStoryArc: vi.fn(),
  updateStoryArc: vi.fn(),
  runArcAi: vi.fn(),
}));
const toastState = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

import StoryArcForm from "@/components/novel/settings/StoryArcForm";

const EMPTY = {
  fullstory: "",
  ending: { scene: "", hero: "", tone: "" },
  volumes: [],
  has_content: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  apiState.fetchStoryArc.mockResolvedValue(EMPTY);
  apiState.updateStoryArc.mockResolvedValue({ ok: true, has_content: false });
});

async function mount(_opts?: { withAsk?: boolean }) {
  const ref = { current: null as any };
  const asks: string[] = [];
  const utils = render(
    <StoryArcForm ref={ref as any} projectId="p1" onAskAssistant={(m) => asks.push(m)} />,
  );
  await waitFor(() => expect(screen.queryByText("加载主线卡…")).toBeNull());
  const lastAsk = () => asks[asks.length - 1] ?? null;
  return { ...utils, ref, lastAsk };
}

async function actasync(fn: () => Promise<void>) {
  const { act } = await import("@testing-library/react");
  await act(fn);
}

/** 弹窗 footer 的「关闭」键（头部 X 的 aria-label 同名，取 DOM 序最后一个＝footer）。 */
function footerClose() {
  const btns = screen.getAllByRole("button", { name: "关闭" });
  return btns[btns.length - 1];
}

describe("主线面板（全景＋结局三问）", () => {
  it("挂载拉卡回显：fullstory 与三问", async () => {
    apiState.fetchStoryArc.mockResolvedValue({
      fullstory: "陆征追查失踪案，从坊市查进警队，最后在听证会上揭开真相。",
      ending: { scene: "侦探所里看着旧卷宗", hero: "破案但心里装了更多", tone: "苍凉但平静" },
      volumes: [],
      has_content: true,
    });
    await mount();
    const ta = screen
      .getAllByRole("textbox")
      .find((el) => (el as HTMLTextAreaElement).value.includes("陆征")) as HTMLTextAreaElement;
    expect(ta.value).toContain("听证会上揭开真相");
    expect((screen.getByPlaceholderText(/丹阁首座在戒律堂认罪/) as HTMLInputElement).value).toBe(
      "侦探所里看着旧卷宗",
    );
    expect((screen.getByPlaceholderText(/从怕事的杂役成为青梧宗执卷人/) as HTMLInputElement).value).toBe(
      "破案但心里装了更多",
    );
    expect((screen.getByPlaceholderText(/先悲后喜 \/ 苦尽甘来 \/ 意难平/) as HTMLInputElement).value).toBe(
      "苍凉但平静",
    );
  });

  it("legacy 形状（只有 premise）：归一进 fullstory 显示", async () => {
    apiState.fetchStoryArc.mockResolvedValue({
      premise: "旧一句话主线",
      ending: { scene: "", hero: "", tone: "" },
      volumes: [],
      has_content: true,
    });
    await mount();
    const ta = screen
      .getAllByRole("textbox")
      .find((el) => (el as HTMLTextAreaElement).value === "旧一句话主线") as HTMLTextAreaElement;
    expect(ta).toBeTruthy();
  });

  it("无分卷区、无基调选择题（tone-opt 退役）", async () => {
    await mount();
    expect(screen.queryByText("加一卷")).toBeNull();
    expect(screen.queryByText("分卷规划")).toBeNull();
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
  });

  it("全景 textarea 无 maxLength：700 字可输入并保存（600 软上限不硬拦）", async () => {
    const { ref } = await mount();
    const ta = screen.getAllByRole("textbox")[0] as HTMLTextAreaElement;
    expect(ta.getAttribute("maxlength")).toBeNull();
    const long = "字".repeat(700);
    fireEvent.change(ta, { target: { value: long } });
    expect(ta.value).toHaveLength(700);
    let ok = false;
    await actasync(async () => {
      ok = await ref.current.save();
    });
    expect(ok).toBe(true);
    expect(apiState.updateStoryArc).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ fullstory: long }),
    );
  });

  it("基调旧数据「待定」：按空显示，保存清成空", async () => {
    apiState.fetchStoryArc.mockResolvedValue({
      fullstory: "p",
      ending: { scene: "", hero: "", tone: "待定" },
      volumes: [],
      has_content: true,
    });
    const { ref } = await mount();
    const tone = screen.getByPlaceholderText(/先悲后喜 \/ 苦尽甘来 \/ 意难平/) as HTMLInputElement;
    expect(tone.value).toBe("");
    let ok = false;
    await actasync(async () => {
      ok = await ref.current.save();
    });
    expect(ok).toBe(true);
    expect(apiState.updateStoryArc).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ ending: expect.objectContaining({ tone: "" }) }),
    );
  });

  it("面板 save() 走 PUT 整卡保存（fullstory 契约）", async () => {
    const { ref } = await mount();
    const ta = screen.getAllByRole("textbox")[0] as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "新全景主线" } });
    let ok = false;
    await actasync(async () => {
      ok = await ref.current.save();
    });
    expect(ok).toBe(true);
    expect(apiState.updateStoryArc).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ fullstory: "新全景主线" }),
    );
  });

  it("保存失败透出后端原因（带响应的 400），不泛化成「保存失败」", async () => {
    apiState.updateStoryArc.mockRejectedValue(
      Object.assign(new Error("主线全文过长（2100/2000 字）——建议 600 字以内"), { status: 400 }),
    );
    const { ref } = await mount();
    const ta = screen.getAllByRole("textbox")[0] as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "超长内容" } });
    let ok = true;
    await actasync(async () => {
      ok = await ref.current.save();
    });
    expect(ok).toBe(false);
    expect(toastState.error).toHaveBeenCalledWith(
      "主线全文过长（2100/2000 字）——建议 600 字以内",
    );
  });

  it("断网类失败（无后端响应）回落中文兜底，不透出英文原文", async () => {
    apiState.updateStoryArc.mockRejectedValue(new TypeError("Failed to fetch"));
    const { ref } = await mount();
    const ta = screen.getAllByRole("textbox")[0] as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "x" } });
    let ok = true;
    await actasync(async () => {
      ok = await ref.current.save();
    });
    expect(ok).toBe(false);
    expect(toastState.error).toHaveBeenCalledWith("主线保存失败");
  });
});

describe("基调第三问 · 让助手办（c-agent-panel-consolidate）", () => {
  beforeEach(() => {
    apiState.fetchStoryArc.mockResolvedValue(EMPTY);
    apiState.updateStoryArc.mockResolvedValue({ ok: true, has_content: false });
  });

  it("收编分派：四动作全部让助手办（对话卡过目，面板不再出弹窗）", async () => {
    const { ref, lastAsk, container } = await mount({ withAsk: true });
    await actasync(async () => ref.current!.runAi("draft"));
    expect(lastAsk()).toBe("帮我起草主线。");
    await actasync(async () => ref.current!.runAi("calibrate"));
    expect(lastAsk()).toBe("对照主线，帮我校准「结局是什么」三问的建议。");
    await actasync(async () => ref.current!.runAi("check"));
    expect(lastAsk()).toBe("做一次主线自检。");
    await actasync(async () => ref.current!.runAi("tone"));
    expect(lastAsk()).toBe("给「合上书那一刻的感觉」一句建议——贴本书题材基调。");
    // 旧弹窗路径退役：不出确认卡、不直调生成核
    expect(screen.queryByTestId("arc-ai-card")).toBeNull();
    expect(apiState.runArcAi).not.toHaveBeenCalled();
  });

  it("按钮文案家法：格头 tone 钮＝让助手办（禁「AI 帮我填」黑话）", async () => {
    const { container } = await mount();
    expect(screen.getByText("让助手办")).toBeTruthy();
    expect(container.textContent).not.toContain("AI 帮我填");
  });

});

describe("主线面板 · 加载失败守卫（c-silent-data-guards）", () => {
  it("加载失败：面板换失败态，表单不可达且不产生 PUT；重试成功恢复", async () => {
    apiState.fetchStoryArc.mockRejectedValue(new Error("网络挂了"));
    render(<StoryArcForm projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("arc-load-error")).toBeInTheDocument());
    expect(screen.queryByTestId("arc-fullstory")).toBeNull();
    expect(apiState.updateStoryArc).not.toHaveBeenCalled();
    // 重试成功 → 失败态退场、表单恢复（fullstory 用 od-id 定位）
    apiState.fetchStoryArc.mockResolvedValue({ ...EMPTY, fullstory: "恢复后的主线" });
    fireEvent.click(screen.getByTestId("arc-reload"));
    await waitFor(() => expect(screen.queryByTestId("arc-load-error")).toBeNull());
    await waitFor(() =>
      expect(
        document.querySelector('[data-od-id="arc-fullstory"]') as HTMLTextAreaElement,
      ).toHaveValue("恢复后的主线"),
    );
  });
});
