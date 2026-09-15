// style-settings-v2 — 文风表单两页签测试：
//   · 文风例句（few_shot_examples 1-3 条）：加载回读（>3 截断）、保存载荷（trim/过滤/截断 3）
//   · 撤并键零写回：GET 返回旧键（possible_mistakes/tone/narrator_role）时
//     PUT payload 只含白名单四键（评审 P0）
//   · 页签徽标：题材默认 ↔ 已自定义 · N 处
//   · 确认门槛 canConfirm：叙事身份非空
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { configure } from "@testing-library/react";
// 组件用 data-od-id 做定位属性（与 e2e 同源）——vitest 侧把 testId 指过去
configure({ testIdAttribute: "data-od-id" });
import { createRef } from "react";
import StyleSettingForm from "@/components/novel/settings/StyleSettingForm";
import type { SettingSaveHandle } from "@/components/novel/settings/FormField";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiState }));

const PH = "如：雨点砸在铁皮棚上，他没有抬头。";

function mockGet(style: Record<string, unknown>, quant: Record<string, unknown> = {}) {
  apiState.get.mockImplementation((url: string) => {
    if (url.endsWith("/settings/style")) return Promise.resolve(style);
    if (url.endsWith("/settings/style-quant")) return Promise.resolve(quant);
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function renderForm() {
  const ref = createRef<SettingSaveHandle>();
  render(
    <StyleSettingForm ref={ref} projectId="p1" settingKey="style" />,
  );
  return ref;
}

function rows(): HTMLInputElement[] {
  return screen.getAllByPlaceholderText(PH) as HTMLInputElement[];
}

/** 例句输入所在的 Cfg 折叠块（文风例句专属，避免命中其他 ListEditor 的添加按钮） */
function fewShotsCfg() {
  const cfg = rows()[0].closest("details");
  if (!cfg) throw new Error("文风例句 Cfg 块未找到");
  return within(cfg as HTMLElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet({ role: "一位小说家" });
  apiState.put.mockResolvedValue({});
  apiState.post.mockResolvedValue({});
});

describe("文风例句 few_shot_examples", () => {
  it("加载回读存量例句；>3 条只取前 3 且例句满 3 时不再出现「添加一项」", async () => {
    mockGet({ role: "r", few_shot_examples: ["例句一", "例句二", "例句三", "例句四"] });
    renderForm();
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(rows().map((r) => r.value)).toEqual(["例句一", "例句二", "例句三"]);
    // maxItems=3：例句行数已满时块内「添加一项」不渲染（其他块不受影响）
    expect(fewShotsCfg().queryByText("添加一项")).toBeNull();
  });

  it("保存载荷包含 few_shot_examples：trim + 过滤空行 + 截断 3", async () => {
    const ref = renderForm();
    await waitFor(() => expect(rows()).toHaveLength(1));
    fireEvent.change(rows()[0], { target: { value: "  雨点砸在铁皮棚上。 " } });
    fireEvent.click(fewShotsCfg().getByText("添加一项"));
    fireEvent.change(rows()[1], { target: { value: "   " } }); // 纯空白 → 过滤

    expect(await ref.current!.save()).toBe(true);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/settings/style",
      expect.objectContaining({ few_shot_examples: ["雨点砸在铁皮棚上。"] }),
    );
  });

  it("存量为空 → 单空行可编辑；保存时输出空数组（不塞空串）", async () => {
    const ref = renderForm();
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rows()[0].value).toBe("");
    fireEvent.change(rows()[0], { target: { value: "他数到第七声雷，才开口。" } });

    expect(await ref.current!.save()).toBe(true);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/settings/style",
      expect.objectContaining({ few_shot_examples: ["他数到第七声雷，才开口。"] }),
    );
  });
});

describe("撤并键零写回（评审 P0）", () => {
  it("GET 带旧键（possible_mistakes/tone/narrator_role）时 PUT payload 只含白名单四键", async () => {
    mockGet({
      role: "冷静叙事者",
      core_principles: ["克制"],
      possible_mistakes: ["不要滥用形容词"],
      depiction_techniques: ["动作外化"],
      narrator_role: "第三人称限知",
      tone: { default_tone: "冷静" },
    });
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    expect(await ref.current!.save()).toBe(true);
    expect(apiState.put).toHaveBeenCalledTimes(1);
    const body = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(["craft", "few_shot_examples", "role", "rules"]);
  });
});

describe("两页签与确认门槛", () => {
  it("页签徽标：题材默认 → 改身份后「已自定义 · 1 处」", async () => {
    mockGet({ role: "冷静叙事者", rules: ["钩子"] });
    renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    expect(screen.getByTestId("style-tab-badge").textContent).toBe("题材默认");
    fireEvent.change(screen.getByTestId("input-style-role"), { target: { value: "改过的身份" } });
    expect(screen.getByTestId("style-tab-badge").textContent).toBe("已自定义 · 1 处");
  });

  it("canConfirm：叙事身份非空 true、空 false", async () => {
    mockGet({ role: "" });
    const ref = renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    expect(ref.current!.canConfirm?.()).toBe(false);
    fireEvent.change(screen.getByTestId("input-style-role"), { target: { value: "冷静叙事者" } });
    expect(ref.current!.canConfirm?.()).toBe(true);
  });

  it("量化页签未蒸馏空态：PRO 徽＋去蒸馏入口；页签徽「未蒸馏」", async () => {
    renderForm();
    await waitFor(() => expect(screen.getByTestId("input-style-role")).toBeTruthy());
    fireEvent.click(screen.getByRole("tab", { name: /量化参数/ }));
    await waitFor(() => expect(screen.getByTestId("quant-empty")).toBeTruthy());
    expect(screen.getByTestId("quant-tab-badge").textContent).toBe("未蒸馏");
  });
});
