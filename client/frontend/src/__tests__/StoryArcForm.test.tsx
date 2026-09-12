import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// StoryArcForm — 主线面板（storyline-settings-v2：全景 fullstory + 结局三问）
// - 挂载拉卡回显（legacy premise 归一进 fullstory）；保存走 PUT
// - 结局三问：三输入框（问题句为 label、例句进占位符）；基调自由输入
// - 无分卷区、无基调选择题（tone-opt 退役）；textarea 无 maxLength（600 软上限）
// - 行内「AI 帮我填」：结果落输入框下方、采纳才写回、在途互斥、免费拦截
// - AI 四能力 runAi 句柄：draft/calibrate/check 结果区复用 AiSink（5 次历史）
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

async function mount() {
  const ref = { current: null as any };
  const utils = render(
    <StoryArcForm ref={ref as any} projectId="p1" />,
  );
  await waitFor(() => expect(screen.queryByText("加载主线卡…")).toBeNull());
  return { ...utils, ref };
}

async function actasync(fn: () => Promise<void>) {
  const { act } = await import("@testing-library/react");
  await act(fn);
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
});

describe("行内「AI 帮我填」（基调第三问）", () => {
  it("建议落输入框下方，采纳才写回", async () => {
    apiState.runArcAi.mockResolvedValue({ value: { tone: "苦尽甘来" } });
    await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() =>
      expect(screen.getByText("苦尽甘来", { selector: ".ai-sink p" })).toBeTruthy(),
    );
    // 未采纳前不写入
    const tone = screen.getByPlaceholderText(/先悲后喜 \/ 苦尽甘来 \/ 意难平/) as HTMLInputElement;
    expect(tone.value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: /采纳/ }));
    expect(tone.value).toBe("苦尽甘来");
    expect(toastState.success).toHaveBeenCalled();
  });

  it("在途互斥：tone 在途时再次触发被忽略（仍 1 请求）", async () => {
    let resolveAi: (v: any) => void = () => {};
    apiState.runArcAi.mockReturnValue(
      new Promise((res) => {
        resolveAi = res;
      }),
    );
    await mount();
    const btn = screen.getByRole("button", { name: /AI 帮我填/ });
    fireEvent.click(btn);
    fireEvent.click(btn); // 在途重复点击
    await actasync(async () => {
      resolveAi({ value: { tone: "x" } });
    });
    expect(apiState.runArcAi).toHaveBeenCalledTimes(1);
  });

  it("免费拦截：member_required 给统一升级提示，不写回", async () => {
    apiState.runArcAi.mockRejectedValue(
      Object.assign(new Error("403"), { reason: "member_required" }),
    );
    await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() =>
      expect(toastState.info).toHaveBeenCalledWith(
        "这是会员功能，升级 PRO 后解锁——免费版写作能力完整",
      ),
    );
    const tone = screen.getByPlaceholderText(/先悲后喜 \/ 苦尽甘来 \/ 意难平/) as HTMLInputElement;
    expect(tone.value).toBe("");
  });

  it("在途 loading 占位与按钮禁用", async () => {
    let resolveAi: (v: any) => void = () => {};
    apiState.runArcAi.mockReturnValue(
      new Promise((res) => {
        resolveAi = res;
      }),
    );
    await mount();
    const btn = screen.getByRole("button", { name: /AI 帮我填/ });
    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText(/正在生成，请稍候/)).toBeTruthy());
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(true));
    await actasync(async () => {
      resolveAi({ value: { tone: "ok" } });
    });
    expect(screen.queryByText(/正在生成，请稍候/)).toBeNull();
  });
});

describe("AI 四能力 runAi 句柄（右栏三行分发）", () => {
  it("draft：结果区落全景下方，采纳覆盖全景与三问", async () => {
    apiState.runArcAi.mockResolvedValue({
      value: {
        fullstory: "AI 全景",
        ending: { scene: "AI 画面", hero: "AI 归宿", tone: "AI 感觉" },
      },
    });
    const { ref } = await mount();
    await actasync(async () => {
      await ref.current.runAi("draft");
    });
    expect(screen.getByText("AI 填 · 起草主线")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /采纳 · 覆盖全景与结局/ }));
    const ta = screen.getAllByRole("textbox")[0] as HTMLTextAreaElement;
    expect(ta.value).toBe("AI 全景");
    expect((screen.getByPlaceholderText(/先悲后喜 \/ 苦尽甘来 \/ 意难平/) as HTMLInputElement).value).toBe("AI 感觉");
  });

  it("check：落面板级结果区，四线渲染、无采纳按钮（只提醒）", async () => {
    apiState.runArcAi.mockResolvedValue({
      value: {
        checks: [
          { name: "故事连贯", status: "ok", note: "一条线到底" },
          { name: "开头接结局", status: "warn", note: "闭环差一点" },
        ],
        summary: "主线立得住",
      },
    });
    const { ref } = await mount();
    await actasync(async () => {
      await ref.current.runAi("check");
    });
    expect(screen.getByText("AI 体检 · 主线自检")).toBeTruthy();
    expect(screen.getByText("故事连贯")).toBeTruthy();
    expect(screen.getByText("开头接结局")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /采纳/ })).toBeNull();
  });

  it("重试：同一能力再跑一次，历史 +1 且可切回", async () => {
    apiState.runArcAi
      .mockResolvedValueOnce({ value: { tone: "第一次" } })
      .mockResolvedValueOnce({ value: { tone: "第二次" } });
    await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() => expect(screen.getByText("第一次")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.getByText("第二次")).toBeTruthy());
    // 两条历史：切回第 1 次
    fireEvent.click(screen.getByRole("button", { name: "第 1 次" }));
    await waitFor(() => expect(screen.getByText("第一次")).toBeTruthy());
  });

  it("clearAi()：确认后清空结果区", async () => {
    apiState.runArcAi.mockResolvedValue({ value: { tone: "x" } });
    const { ref } = await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() => expect(screen.getByText("AI 填 · 结局基调")).toBeTruthy());
    await actasync(async () => {
      ref.current.clearAi();
    });
    expect(screen.queryByText("AI 填 · 结局基调")).toBeNull();
  });
});
