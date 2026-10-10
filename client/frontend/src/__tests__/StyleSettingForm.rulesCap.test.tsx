// c-style-rules-cap-align — 硬约束上限对齐后端 `_MAX_RULES`（100）：
//   · 模板/迁移预填 ≈58 条（> 旧上限 5）时「添加一项」必须可用
//     （旧实现 items.length >= 5 恒隐藏 → 作者加不了新硬约束；测试反馈「57/5 条」定诊）
//   · 计数口径「N/100 条」；行数达 100（后端上限）才收起添加按钮
import { beforeEach, describe, expect, it, vi } from "vitest";
import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createRef } from "react";

configure({ testIdAttribute: "data-od-id" });

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

const RULES_PH = "可执行的硬规则。例：「突然」每章不超过 4 次";

function mockStyle(rules: string[]) {
  apiState.get.mockImplementation((url: string) => {
    if (url.endsWith("/settings/style")) return Promise.resolve({ role: "一位小说家", rules });
    if (url.endsWith("/settings/style-quant")) return Promise.resolve({});
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

/** 硬约束 ListEditor 块（data-od-id 与 e2e 同源）——避免命中禁用词/手法块的「添加一项」 */
function rulesBlock() {
  return within(screen.getByTestId("list-rules"));
}

function ruleRows(): HTMLInputElement[] {
  return screen.getAllByPlaceholderText(RULES_PH) as HTMLInputElement[];
}

beforeEach(() => {
  vi.clearAllMocks();
  apiState.put.mockResolvedValue({});
  apiState.post.mockResolvedValue({});
});

describe("硬约束上限（c-style-rules-cap-align）", () => {
  it("预填 58 条（>旧上限 5）：「添加一项」可见可用，计数 N/100，可保存", async () => {
    mockStyle(Array.from({ length: 58 }, (_, i) => `模板红线 ${i + 1}`));
    const ref = createRef<SettingSaveHandle>();
    render(<StyleSettingForm ref={ref} projectId="p1" settingKey="style" />);
    await waitFor(() => expect(ruleRows()).toHaveLength(58));
    expect(rulesBlock().getByText("58/100 条")).toBeTruthy();

    fireEvent.click(rulesBlock().getByText("添加一项"));
    await waitFor(() => expect(ruleRows()).toHaveLength(59));
    expect(rulesBlock().getByText("59/100 条")).toBeTruthy();

    fireEvent.change(ruleRows()[58], { target: { value: "「突然」每章不超过 4 次" } });
    expect(await ref.current!.save()).toBe(true);
    const body = apiState.put.mock.calls[0][1] as { rules: string[] };
    expect(body.rules).toHaveLength(59);
    expect(body.rules[58]).toBe("「突然」每章不超过 4 次");
  });

  it("行数达 100（后端上限）：「添加一项」收起", async () => {
    mockStyle(Array.from({ length: 100 }, (_, i) => `红线 ${i + 1}`));
    render(<StyleSettingForm projectId="p1" settingKey="style" />);
    await waitFor(() => expect(ruleRows()).toHaveLength(100));
    expect(rulesBlock().getByText("100/100 条")).toBeTruthy();
    expect(rulesBlock().queryByText("添加一项")).toBeNull();
  });
});
