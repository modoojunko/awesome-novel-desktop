// 二次蒸馏进度复位（内测反馈#13）：粘贴重启（显式带 text 从 step1 起跑）时进度 UI
// 同步归零——上一轮/旧 draft 的步数不得冒充本轮（否则进度条恒「已完成」、按钮恒
// 「继续蒸馏」）。同时钉住：复位后粘贴链重试不被「样本不齐」拦死。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { configure } from "@testing-library/react";
configure({ testIdAttribute: "data-od-id" });
import { createRef } from "react";
import StyleSettingForm from "@/components/novel/settings/StyleSettingForm";
import type { SettingSaveHandle } from "@/components/novel/settings/FormField";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiState }));
const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

const PASTE_TEXT = "雨点砸在铁皮棚上，他没有抬头。".repeat(200); // 3600 字（去空白）：在 3000-10000 区间内

/** 旧 draft 停在 step2（无画像）：重开蒸馏即「上轮已完成两步」的现场。 */
const DRAFT_STEP2 = { step: 2, sample_chars: 3600 };
const SAMPLES_IN_RANGE = {
  files: [{ name: "a.md", chars: 4000 }],
  chapters: [],
  total: 4000,
  min: 3000,
  max: 60000,
  in_range: true,
  hint: "",
};

function mockGet(quant: Record<string, unknown>) {
  apiState.get.mockImplementation((url: string) => {
    if (url.endsWith("/settings/style")) return Promise.resolve({ role: "一位小说家" });
    if (url.endsWith("/settings/style-quant")) return Promise.resolve(quant);
    if (url.endsWith("/settings/style-samples")) return Promise.resolve(SAMPLES_IN_RANGE);
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function renderForm() {
  const ref = createRef<SettingSaveHandle>();
  render(<StyleSettingForm ref={ref} projectId="p1" settingKey="style" />);
  return ref;
}

/** 进「量化参数」页签 → 打开蒸馏面板（走 openDistill 的续跑分支）。 */
async function openDistillView() {
  const tab = await screen.findByTestId("ptab-quant");
  fireEvent.click(tab);
  const open = await screen.findByTestId("btn-open-distill");
  fireEvent.click(open);
  await screen.findByTestId("distill-samples");
}

/** 粘贴链：开弹窗→填文本→提交。 */
async function startPaste(text: string) {
  fireEvent.click(screen.getByTestId("btn-open-paste"));
  const ta = await screen.findByTestId("input-paste-sample");
  fireEvent.change(ta, { target: { value: text } });
  fireEvent.click(screen.getByTestId("btn-paste-start"));
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiState.put.mockResolvedValue({});
});

describe("粘贴重启的进度复位", () => {
  it("重启在飞时三步全为未开始（不再显示上一轮已完成），按钮「蒸馏中…」", async () => {
    mockGet({ ...DRAFT_STEP2 && { draft: DRAFT_STEP2 }, confidence: 0 });
    const step1 = deferred<{ ok: boolean; step: number }>();
    apiState.post.mockImplementation((url: string) => {
      if (url.endsWith("/step1")) return step1.promise;
      return Promise.resolve({ ok: true });
    });
    renderForm();
    await openDistillView();

    // 前置：旧 draft 挂在 step2 → 进度条显示两步已完成（这是被报告的旧现场）
    const box = await screen.findByTestId("distill-steps");
    expect(box.querySelectorAll(".ds-ok")).toHaveLength(2);

    await startPaste(PASTE_TEXT);
    // 复位：本轮三步全未开始（无任何「完成」标）
    await waitFor(() => {
      const steps = screen.getByTestId("distill-steps");
      expect(steps.querySelectorAll(".ds-ok")).toHaveLength(0);
      expect(steps.querySelectorAll(".dist-step.pending")).toHaveLength(3);
    });
    expect(screen.getByTestId("btn-run-distill")).toHaveTextContent("蒸馏中…");
    // 在飞期按钮按既有口径随 distillBusy 禁用（防重入）——复位不改变这一点
    expect(screen.getByTestId("btn-run-distill")).toBeDisabled();

    // 放行 step1：本轮从 0 起跑走满三步（而不是挂着旧 draft 的两步当已完成）
    step1.resolve({ ok: true, step: 1 });
    await waitFor(() => {
      expect(screen.getByTestId("distill-steps").querySelectorAll(".ds-ok")).toHaveLength(3);
    });
  });

  it("重启失败后按钮回「开始蒸馏」（不再挂「继续蒸馏」），进度归零", async () => {
    mockGet({ draft: DRAFT_STEP2, confidence: 0 });
    apiState.post.mockImplementation((url: string) => {
      if (url.endsWith("/step1")) return Promise.reject(new Error("AI 学习失败，可重试"));
      return Promise.resolve({ ok: true });
    });
    renderForm();
    await openDistillView();
    await screen.findByTestId("distill-steps");

    await startPaste(PASTE_TEXT);
    await waitFor(() => expect(screen.getByTestId("style-error")).toBeTruthy());
    // 进度 UI 归零：不再残留上一轮/旧 draft 的「已完成」；按钮回初始文案
    expect(screen.queryByTestId("distill-steps")).toBeNull();
    expect(screen.getByTestId("btn-run-distill")).toHaveTextContent("开始蒸馏");
  });

  it("样本不齐 + 活动粘贴样本：重启（甚至失败后）按钮不被禁用", async () => {
    // 无旧 draft（distillStep 从 0 起）＝「样本不齐禁用」门槛真正生效的现场
    mockGet({ confidence: 0 });
    apiState.get.mockImplementation((url: string) => {
      if (url.endsWith("/settings/style")) return Promise.resolve({ role: "一位小说家" });
      if (url.endsWith("/settings/style-quant")) return Promise.resolve({ confidence: 0 });
      if (url.endsWith("/settings/style-samples")) {
        return Promise.resolve({ ...SAMPLES_IN_RANGE, files: [{ name: "a.md", chars: 100 }], total: 100, in_range: false, hint: "样本太少" });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    apiState.post.mockRejectedValue(new Error("AI 学习失败，可重试"));
    renderForm();
    await openDistillView();
    // 样本不齐：无粘贴样本时按钮禁用（既有口径）
    const btn = screen.getByTestId("btn-run-distill");
    expect(btn).toBeDisabled();

    await startPaste(PASTE_TEXT);
    await waitFor(() => expect(screen.getByTestId("style-error")).toBeTruthy());
    // 复位到 0 后仍可重试（粘贴文本供样本，不被区间门槛拦死）
    expect(screen.getByTestId("btn-run-distill")).not.toBeDisabled();
    expect(
      within(screen.getByTestId("distill-panel")).queryByText("样本太少"),
    ).toBeNull();
  });
});
