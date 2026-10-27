// 文字层蒸馏（c-style-distill-full）：step4 补跑＋确认卡文字层两段＋分段采纳。
// 钉子：① 存量文件路 draft 补跑 step4、粘贴路 draft 不补跑（样本不保留原文）；
//       ② 分段采纳三态（全采纳/只采纳示范段/全弃按钮禁用）；
//       ③ 采纳 payload 防丢词（未保存禁用词并入）＋采纳后表单态同步（保存不回踩）；
//       ④ 回执撤销恢复采纳前三区/示范段并回写。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { configure } from "@testing-library/react";
configure({ testIdAttribute: "data-od-id" });
import { createRef } from "react";
import StyleSettingForm from "@/components/novel/settings/StyleSettingForm";
import type { SettingSaveHandle } from "@/components/novel/settings/FormField";
import type { ChangeReceiptState } from "@/components/novel/settings/ChangeReceipt";

const apiState = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));
const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

const SAMPLES_OK = {
  files: [{ name: "a.md", chars: 4000 }],
  chapters: [],
  total: 4000,
  min: 3000,
  max: 60000,
  in_range: true,
  hint: "",
};

const STEP4 = {
  role: "学来的身份",
  rules: ["规则A：照着做", "避免B：不要那样"],
  craft: ["手法C：这么用"],
  samples: ["他把账本合上，往桌上一拍，屋里人都静了。", "夜里落了雪，炉光照亮他半边脸。"],
};

function draftAt(options: { step4?: typeof STEP4; paste?: boolean }) {
  return {
    step: options.step4 ? 4 : 3,
    sample_chars: 4000,
    samples_used: options.paste ? ["粘贴文本"] : ["a.md"],
    step3: { portrait: "像你的写法", rows: {} },
    ...(options.step4 ? { step4: options.step4 } : {}),
  };
}

/** 量化 GET 的完整形状（quant 页签渲染要 history/updated_at/sample_chars）。 */
function quantWith(draft: Record<string, unknown>) {
  return {
    version: 1,
    confidence: 53,
    sample_chars: 4000,
    updated_at: "2026-10-26",
    baseline: {},
    details: {},
    portrait: "",
    history: [{ version: 1, updated_at: "2026-10-26", sample_chars: 4000, locks: {} }],
    draft,
  };
}

function renderWithReceipt(onReceipt?: (r: ChangeReceiptState | null) => void) {
  const ref = createRef<SettingSaveHandle>();
  render(<StyleSettingForm ref={ref} projectId="p1" settingKey="style" onReceiptChange={onReceipt} />);
  return ref;
}

async function openQuant() {
  fireEvent.click(await screen.findByTestId("ptab-quant"));
}

describe("文字层蒸馏（c-style-distill-full）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiState.put.mockResolvedValue({});
    apiState.post.mockResolvedValue({ ok: true });
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "旧身份", rules: ["旧规则"], craft: [], banned_words: [], tic_patterns: [] });
      if (url.endsWith("/settings/style-quant")) return Promise.resolve({ confidence: 0 });
      if (url.endsWith("/settings/style-samples")) return Promise.resolve(SAMPLES_OK);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
  });

  it("存量文件路 draft 停在 step3：重开自动补跑 step4，确认卡呈现文字层两段", async () => {
    let quant: Record<string, unknown> = quantWith(draftAt({}));
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "旧身份" });
      if (url.endsWith("/settings/style-quant")) return Promise.resolve(quant);
      if (url.endsWith("/settings/style-samples")) return Promise.resolve(SAMPLES_OK);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    apiState.post.mockImplementation((url: string) => {
      if (url.endsWith("/step4")) {
        quant = quantWith(draftAt({ step4: STEP4 }));
        return Promise.resolve({ ok: true, step: 4 });
      }
      return Promise.resolve({ ok: true });
    });
    renderWithReceipt();
    await openQuant();
    fireEvent.click(await screen.findByTestId("btn-redistill"));
    // 补跑：step4 被调用且 body 携带样本上下文（文件勾选）
    await waitFor(() => {
      const step4 = apiState.post.mock.calls.find(([u]) => String(u).endsWith("/step4"));
      expect(step4).toBeTruthy();
      expect((step4![1] as { files: string[] }).files).toContain("a.md");
    });
    expect(await screen.findByTestId("learn-text-layer")).toBeTruthy();
    expect((screen.getByTestId("learn-role") as HTMLInputElement).value).toBe("学来的身份");
    expect(screen.getByTestId("learn-samples").textContent).toContain("屋里人都静了");
  });

  it("粘贴路 draft 无 step4：不自动补跑（原文不保留），卡内给提示", async () => {
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "旧身份" });
      if (url.endsWith("/settings/style-quant")) return Promise.resolve(quantWith(draftAt({ paste: true })));
      if (url.endsWith("/settings/style-samples")) return Promise.resolve(SAMPLES_OK);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    renderWithReceipt();
    await openQuant();
    fireEvent.click(await screen.findByTestId("btn-redistill"));
    await screen.findByTestId("author-portrait");
    await waitFor(() => expect(screen.getByTestId("learn-unavailable")).toBeTruthy());
    expect(screen.getByTestId("learn-unavailable").textContent).toContain("粘贴样本不保留原文");
    expect(apiState.post.mock.calls.some(([u]) => String(u).endsWith("/step4"))).toBe(false);
  });

  it("分段采纳·全采纳：三区替换＋示范段写入＋禁用词并入不丢", async () => {
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "旧身份", rules: ["旧规则"], craft: [], banned_words: ["服务端新词"], tic_patterns: [] });
      if (url.endsWith("/settings/style-quant"))
        return Promise.resolve(quantWith(draftAt({ step4: STEP4 })));
      if (url.endsWith("/settings/style-samples")) return Promise.resolve(SAMPLES_OK);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    renderWithReceipt();
    await openQuant();
    fireEvent.click(await screen.findByTestId("btn-redistill"));
    fireEvent.click(await screen.findByTestId("btn-learn-adopt"));
    await waitFor(() => expect(apiState.put).toHaveBeenCalled());
    const body = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(body.role).toBe("学来的身份");
    expect(body.rules).toEqual(["规则A：照着做", "避免B：不要那样"]);
    expect(body.style_samples).toEqual(STEP4.samples);
    // D4 防丢词：表单态「旧词」（无）∪ 服务端「服务端新词」→ 并集写入
    expect(body.banned_words).toContain("服务端新词");
    expect(screen.getByTestId("learn-text-layer")).toBeTruthy();
  });

  it("只采纳示范段：三区不动；全弃：按钮禁用", async () => {
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "旧身份", rules: ["旧规则"], craft: [], banned_words: [], tic_patterns: [] });
      if (url.endsWith("/settings/style-quant"))
        return Promise.resolve(quantWith(draftAt({ step4: STEP4 })));
      if (url.endsWith("/settings/style-samples")) return Promise.resolve(SAMPLES_OK);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    renderWithReceipt();
    await openQuant();
    fireEvent.click(await screen.findByTestId("btn-redistill"));
    await screen.findByTestId("learn-text-layer");
    fireEvent.click(screen.getByTestId("learn-adopt-rules"));
    fireEvent.click(await screen.findByTestId("btn-learn-adopt"));
    await waitFor(() => expect(apiState.put).toHaveBeenCalled());
    const body = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(body.role).toBe("旧身份");
    expect(body.rules).toEqual(["旧规则"]);
    expect(body.style_samples).toEqual(STEP4.samples);

    // 全弃：按钮禁用
    fireEvent.click(screen.getByTestId("learn-adopt-samples"));
    expect(screen.getByTestId("btn-learn-adopt")).toBeDisabled();
  });

  it("采纳后表单态同步：随后的表单保存不回踩（PUT 仍为采纳值）＋回执撤销恢复并回写", async () => {
    const receipts: ChangeReceiptState[] = [];
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "旧身份", rules: ["旧规则"], craft: [], banned_words: [], tic_patterns: [] });
      if (url.endsWith("/settings/style-quant"))
        return Promise.resolve(quantWith(draftAt({ step4: STEP4 })));
      if (url.endsWith("/settings/style-samples")) return Promise.resolve(SAMPLES_OK);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    const ref = renderWithReceipt((r) => r && receipts.push(r));
    await openQuant();
    fireEvent.click(await screen.findByTestId("btn-redistill"));
    fireEvent.click(await screen.findByTestId("btn-learn-adopt"));
    await waitFor(() => expect(apiState.put).toHaveBeenCalled());

    // 采纳后保存：PUT 仍为采纳值（表单态已同步，不回踩旧身份）
    await ref.current!.save();
    const saveBody = apiState.put.mock.calls[1][1] as Record<string, unknown>;
    expect(saveBody.role).toBe("学来的身份");
    expect(saveBody.style_samples).toEqual(STEP4.samples);
    // 七键 payload：style_samples 非空时随存
    expect(Object.keys(saveBody).sort()).toEqual([
      "banned_words", "craft", "few_shot_examples", "role", "rules", "style_samples", "tic_patterns",
    ]);

    // 回执撤销：恢复采纳前三区/示范段并回写服务端
    expect(receipts.length).toBeGreaterThan(0);
    receipts[receipts.length - 1].undo?.();
    await waitFor(() => expect(apiState.put.mock.calls.length).toBeGreaterThanOrEqual(3));
    const undoBody = apiState.put.mock.calls[apiState.put.mock.calls.length - 1][1] as Record<string, unknown>;
    expect(undoBody.role).toBe("旧身份");
    expect(undoBody.style_samples).toBeUndefined();
  });
});
