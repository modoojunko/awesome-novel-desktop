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

describe("行内「AI 帮我填」（基调第三问）", () => {
  it("结果进弹窗出卡，采纳才写回（确认写回＋toast）", async () => {
    apiState.runArcAi.mockResolvedValue({ value: { tone: "苦尽甘来" } });
    await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() =>
      expect(screen.getByText("苦尽甘来", { selector: ".ai-card-body p" })).toBeTruthy(),
    );
    expect(screen.getByText("AI 填 · 结局基调")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
    // 未采纳前不写入
    const tone = screen.getByPlaceholderText(/先悲后喜 \/ 苦尽甘来 \/ 意难平/) as HTMLInputElement;
    expect(tone.value).toBe("");
    fireEvent.click(screen.getByTestId("ai-card-adopt"));
    expect(tone.value).toBe("苦尽甘来");
    expect(toastState.success).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("arc-ai-card")).toBeNull()); // 确认后弹窗自动关
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

  it("在途：弹窗 loading 占位（首次无卡），入口按钮禁用", async () => {
    let resolveAi: (v: any) => void = () => {};
    apiState.runArcAi.mockReturnValue(
      new Promise((res) => {
        resolveAi = res;
      }),
    );
    await mount();
    const btn = screen.getByRole("button", { name: /AI 帮我填/ });
    fireEvent.click(btn);
    // 首跑无卡：卡体给 loading 占位（data-od-id 而非 testid）
    await waitFor(() => expect(document.querySelector('[data-od-id="ai-card-loading"]')).toBeTruthy());
    expect(screen.getByText("AI 正在生成…")).toBeTruthy();
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(true));
    await actasync(async () => {
      resolveAi({ value: { tone: "ok" } });
    });
    await waitFor(() =>
      expect(document.querySelector('[data-od-id="ai-card-loading"]')).toBeNull(),
    );
    expect(screen.getByTestId("ai-card-adopt")).toBeTruthy();
  });

  it("关闭即弃：打开→关闭，表单字段不变、无残留结果", async () => {
    apiState.runArcAi.mockResolvedValue({ value: { tone: "候选句" } });
    await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() => expect(screen.getByText("候选句")).toBeTruthy());
    fireEvent.click(footerClose());
    await waitFor(() => expect(screen.queryByTestId("arc-ai-card")).toBeNull());
    const tone = screen.getByPlaceholderText(/先悲后喜 \/ 苦尽甘来 \/ 意难平/) as HTMLInputElement;
    expect(tone.value).toBe("");
    expect(toastState.success).not.toHaveBeenCalled();
  });

  it("缓存重开：同一能力再触发＝重开弹窗展示缓存，不再发请求（D9）", async () => {
    apiState.runArcAi.mockResolvedValue({ value: { tone: "缓存版" } });
    await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() => expect(screen.getByText("缓存版")).toBeTruthy());
    fireEvent.click(screen.getByTestId("ai-card-adopt"));
    await waitFor(() => expect(screen.queryByTestId("arc-ai-card")).toBeNull());
    expect(apiState.runArcAi).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() => expect(screen.getByText(/上次生成结果/)).toBeTruthy());
    expect(document.querySelector('[data-od-id="ai-card-cache"]')).toBeTruthy();
    expect(screen.getByText("缓存版")).toBeTruthy();
    expect(apiState.runArcAi).toHaveBeenCalledTimes(1); // 没有再发请求
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

  it("check：落弹窗报告卡，四线渲染、无采纳键（只提醒）", async () => {
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
    expect(screen.getByTestId("arc-ai-card")).toBeTruthy();
    expect(screen.getByText("AI 体检 · 主线自检")).toBeTruthy();
    expect(screen.getByText("故事连贯")).toBeTruthy();
    expect(screen.getByText("开头接结局")).toBeTruthy();
    expect(screen.queryByTestId("ai-card-adopt")).toBeNull(); // 报告卡无写回
  });

  it("换一个：重新发请求且版数徽标 +1；在途期间旧版保持可读、确认键可点（D3）", async () => {
    let resolveSecond: (v: any) => void = () => {};
    apiState.runArcAi
      .mockResolvedValueOnce({ value: { tone: "第一次" } })
      .mockReturnValueOnce(
        new Promise((res) => {
          resolveSecond = res;
        }),
      );
    await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() => expect(screen.getByText("第一次")).toBeTruthy());
    expect(screen.getByText("第 1 版")).toBeTruthy();

    fireEvent.click(screen.getByTestId("ai-card-regen"));
    // 在途：旧版内容仍在、确认键不锁、重生成键防抖禁用
    expect(screen.getByText("第一次")).toBeTruthy();
    expect(screen.getByText(/正在生成新一版/)).toBeTruthy();
    expect((screen.getByTestId("ai-card-adopt") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId("ai-card-regen") as HTMLButtonElement).disabled).toBe(true);
    await actasync(async () => {
      resolveSecond({ value: { tone: "第二次" } });
    });
    await waitFor(() => expect(screen.getByText("第二次")).toBeTruthy());
    expect(screen.queryByText("第一次")).toBeNull();
    expect(screen.getByText("第 2 版")).toBeTruthy();
    expect(apiState.runArcAi).toHaveBeenCalledTimes(2);
  });

  it("clearAi()：确认后清空结果（弹窗关闭且不再展示）", async () => {
    apiState.runArcAi.mockResolvedValue({ value: { tone: "x" } });
    const { ref } = await mount();
    fireEvent.click(screen.getByRole("button", { name: /AI 帮我填/ }));
    await waitFor(() => expect(screen.getByText("AI 填 · 结局基调")).toBeTruthy());
    await actasync(async () => {
      ref.current.clearAi();
    });
    await waitFor(() => expect(screen.queryByTestId("arc-ai-card")).toBeNull());
    expect(screen.queryByText("AI 填 · 结局基调")).toBeNull();
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
