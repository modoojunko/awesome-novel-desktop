// c-style-kb-fill：右栏「按题材填文风」→ 知识库草稿勾选卡 → 采纳填表 / 回执撤销。
// 只测前端编排（后端映射在 tests/test_style_kb_draft.py）；不触真实网络。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
configure({ testIdAttribute: "data-od-id" });
import { createRef } from "react";
import StyleSettingForm, { type StylePanelHandle } from "@/components/novel/settings/StyleSettingForm";
import type { ChangeReceiptState } from "@/components/novel/settings/ChangeReceipt";
import type { StyleKbDraft } from "@/lib/styleApi";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

const DRAFT: StyleKbDraft = {
  theme: "悬疑",
  sub_genre: "",
  role: "贴着主角写的第三人称，语气克制。",
  rules: ["规则一", "规则二", "规则三", "规则四", "规则五", "规则六"],
  craft: ["手法一", "手法二", "手法三", "手法四"],
  banned_words: ["与此同时", "他感到"],
  tic_patterns: [
    { pattern: "不是.{1,10}而是", name: "不是而是", threshold: 3, severity: "high", description: "" },
  ],
  style_samples: ["示范段一", "示范段二"],
  counts: { role: 1, rules: 6, craft: 4, banned_words: 2, tic_patterns: 1, style_samples: 2, total: 16 },
};

function mockGet(style: Record<string, unknown>, kb: StyleKbDraft | Error = DRAFT) {
  apiState.get.mockImplementation((url: string) => {
    if (url.endsWith("/settings/style/kb-draft")) {
      return kb instanceof Error ? Promise.reject(kb) : Promise.resolve(kb);
    }
    if (url.endsWith("/settings/style")) return Promise.resolve(style);
    if (url.endsWith("/settings/style-quant")) return Promise.resolve({});
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function renderForm(
  onReceiptChange?: (r: ChangeReceiptState | null) => void,
  onDirtyChange?: (dirty: boolean) => void,
) {
  const ref = createRef<StylePanelHandle>();
  render(
    <StyleSettingForm
      ref={ref}
      projectId="p1"
      settingKey="style"
      onReceiptChange={onReceiptChange}
      onDirtyChange={onDirtyChange}
    />,
  );
  return ref;
}

async function openKb(ref: React.RefObject<StylePanelHandle | null>) {
  await act(async () => {
    await ref.current!.runAi!("kb");
  });
}

function checkboxes(): HTMLInputElement[] {
  const card = screen.getByTestId("kb-pick-card");
  return within(card).getAllByRole("checkbox") as HTMLInputElement[];
}

beforeEach(() => {
  vi.clearAllMocks();
  apiState.put.mockResolvedValue({});
  apiState.post.mockResolvedValue({});
});

describe("按题材填文风（c-style-kb-fill）", () => {
  it("开卡默认只勾推荐量：身份 1＋硬约束前 5＋手法前 3＋禁用词/句式全勾，示范段不勾", async () => {
    mockGet({ role: "", rules: [], banned_words: ["与此同时"] });
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);
    expect(screen.getByText("按题材填文风 · 悬疑")).toBeTruthy();
    // 1 身份 + 5 硬约束 + 3 手法 + 2 禁用词 + 1 句式 = 12
    expect(checkboxes().filter((b) => b.checked)).toHaveLength(12);
    expect(screen.getByText(/这些是从知识库找出来的「悬疑」写法/)).toBeTruthy();
  });

  it("采纳后填进表单（三区替换、护栏合并），保存 payload 带上；可一步撤销", async () => {
    const receipts: Array<ChangeReceiptState | null> = [];
    mockGet({ role: "", rules: [], banned_words: ["与此同时"] }, DRAFT);
    const ref = renderForm((r) => receipts.push(r));
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);

    fireEvent.click(screen.getByRole("button", { name: /采纳，填进文风/ }));
    await waitFor(() => expect(screen.queryByTestId("kb-pick-card")).toBeNull());

    expect((screen.getByTestId("input-style-role") as HTMLTextAreaElement).value).toBe(DRAFT.role);

    await act(async () => {
      await ref.current!.save!();
    });
    const body = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(body.rules).toEqual(["规则一", "规则二", "规则三", "规则四", "规则五"]);
    expect(body.craft).toEqual(["手法一", "手法二", "手法三"]);
    expect(body.banned_words).toEqual(["与此同时", "他感到"]);
    expect((body.tic_patterns as Array<{ pattern: string }>)[0].pattern).toBe("不是.{1,10}而是");
    expect(body.style_samples).toBeUndefined(); // 示范段默认不勾

    // 回执文案 + 撤销恢复空白三区
    const receipt = receipts.filter(Boolean).at(-1)!;
    expect(receipt.text).toContain("还没保存");
    await act(async () => {
      await receipt.undo!();
    });
    expect((screen.getByTestId("input-style-role") as HTMLTextAreaElement).value).toBe("");
  });

  it("身份可以在弹窗里直接改；采纳用改过的文字", async () => {
    mockGet({ role: "" }, DRAFT);
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);

    const card = screen.getByTestId("kb-pick-card");
    fireEvent.change(within(card).getByLabelText("叙事身份"), {
      target: { value: "我改过的身份" },
    });
    fireEvent.click(screen.getByRole("button", { name: /采纳，填进文风/ }));
    await waitFor(() => expect(screen.queryByTestId("kb-pick-card")).toBeNull());
    expect((screen.getByTestId("input-style-role") as HTMLTextAreaElement).value).toBe("我改过的身份");
  });

  it("没定题材：只提示，不开空卡", async () => {
    mockGet({ role: "" }, { ...DRAFT, theme: "", counts: { ...DRAFT.counts, total: 0 }, role: "", rules: [], craft: [], banned_words: [], tic_patterns: [], style_samples: [] });
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);
    expect(toastState.info).toHaveBeenCalledWith("先去定题材，再来按题材填文风。");
    expect(screen.queryByTestId("kb-pick-card")).toBeNull();
  });

  it("库里没有同题材写法：提示去哪补，不开空卡", async () => {
    mockGet({ role: "" }, {
      ...DRAFT,
      counts: { role: 0, rules: 0, craft: 0, banned_words: 0, tic_patterns: 0, style_samples: 0, total: 0 },
      role: "",
      rules: [],
      craft: [],
      banned_words: [],
      tic_patterns: [],
      style_samples: [],
    });
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);
    expect(toastState.info).toHaveBeenCalledWith(
      "知识库里还没有悬疑的写法——先拆一本同题材的书，或者去知识库记几条。",
    );
    expect(screen.queryByTestId("kb-pick-card")).toBeNull();
  });

  it("知识库读取失败：toast 报错，不弹卡", async () => {
    mockGet({ role: "" }, new Error("boom"));
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);
    expect(toastState.error).toHaveBeenCalled();
    expect(screen.queryByTestId("kb-pick-card")).toBeNull();
  });

  it("至少勾一条才能采纳", async () => {
    mockGet({ role: "" }, DRAFT);
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);
    // 全部取消：逐个点掉默认勾选
    for (const b of checkboxes()) {
      if (b.checked) fireEvent.click(b);
    }
    expect((screen.getByRole("button", { name: /采纳，填进文风/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("描写手法最多勾 8 条：全选只勾前 8，落表也是 8", async () => {
    const manyCraft = { ...DRAFT, craft: Array.from({ length: 12 }, (_, i) => `手法${i + 1}`) };
    mockGet({ role: "" }, manyCraft);
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);

    const card = screen.getByTestId("kb-pick-card");
    const craftSection = within(card).getByText("描写手法").closest("section")!;
    fireEvent.click(within(craftSection).getByText("全选"));
    expect(
      (within(craftSection).getAllByRole("checkbox") as HTMLInputElement[]).filter((b) => b.checked),
    ).toHaveLength(8);
    // 到顶后未勾项禁用
    expect(
      (within(craftSection).getAllByRole("checkbox") as HTMLInputElement[]).filter(
        (b) => !b.checked && b.disabled,
      ),
    ).toHaveLength(4);

    fireEvent.click(screen.getByRole("button", { name: /采纳，填进文风/ }));
    await waitFor(() => expect(screen.queryByTestId("kb-pick-card")).toBeNull());
    await act(async () => {
      await ref.current!.save!();
    });
    const body = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect((body.craft as string[]).length).toBe(8);
  });

  it("只勾示范段采纳也标脏：切面板会触发未保存确认", async () => {
    const samplesOnly: StyleKbDraft = {
      ...DRAFT,
      role: "",
      rules: [],
      craft: [],
      banned_words: [],
      tic_patterns: [],
      style_samples: ["示范段一"],
      counts: {
        role: 0,
        rules: 0,
        craft: 0,
        banned_words: 0,
        tic_patterns: 0,
        style_samples: 1,
        total: 1,
      },
    };
    mockGet({ role: "" }, samplesOnly);
    const dirty = vi.fn();
    const ref = renderForm(undefined, dirty);
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    await openKb(ref);

    const card = screen.getByTestId("kb-pick-card");
    const sampleSection = within(card).getByText("示范段").closest("section")!;
    fireEvent.click(within(sampleSection).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /采纳，填进文风/ }));
    await waitFor(() => expect(dirty).toHaveBeenCalledWith(true));
  });
});
