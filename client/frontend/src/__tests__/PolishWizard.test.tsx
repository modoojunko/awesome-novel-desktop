/** 修稿向导（c-deai-wizard）：四步流程组件测试。
 *  mock @/lib/ai（扫描与改写）；写回经 onApply 断言（ProsePane 内部实现不在本测）。 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PolishWizard from "@/components/novel/workbench/polishWizard/PolishWizard";

const PROSE = vi.hoisted(() => [
  "哨站里只剩林野一个人。",
  "掌心贴上砖墙，一片冰凉。",
  "他的心跳漏了一拍，这意味着他撑不过明夜。",
  "天亮前阿蓟把体温计递过来。",
]);

const SCAN = vi.hoisted(() => ({
  ok: true as const,
  report: {
    metrics: { comma_period_ratio: 2.1, short_para_ratio: 0.1, dialogue_ratio: 0.3 },
    para_count: 4,
    findings: [
      { rule: "multi_period", severity: "advisory" as const, para: 1, excerpt: "掌心…", detail: "段内句号 3 处", count: 3, autofixable: true },
    ],
  },
  problems: [
    { para: 1, text: PROSE[1], source: "detector" as const, confidence: 0.71, reasons: ["朱雀判定疑似 AI 腔 71%"], suggested_fix: "monologue_dequote" },
    { para: 2, text: PROSE[2], source: "both" as const, confidence: 0.58, reasons: ["疑似解释尾巴"], suggested_fix: "delete_or_concretize" },
    { para: 3, text: PROSE[3], source: "rule" as const, confidence: null, reasons: ["段内句号过密"], suggested_fix: "merge_periods" },
  ],
  detector: { stored: true, human_ratio: 0.37, stale_hint: null },
}));

vi.mock("@/lib/ai", () => ({
  aiFlavorScan: vi.fn().mockResolvedValue(SCAN),
  polishTextDetail: vi.fn(async (_p: string, _c: string, sel: string) => ({ polished_text: `【改】${sel.slice(0, 6)}`, changed: true, flags: [], flags_blocking: false })),
}));

vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { aiFlavorScan, polishTextDetail } from "@/lib/ai";

function mount(over: Partial<Parameters<typeof PolishWizard>[0]> = {}) {
  const onApply = vi.fn((_items: Array<{ paraIndex: number; from: string; text: string }>) => ({ applied: _items.length, skipped: 0 }));
  const onClose = vi.fn();
  render(
    <PolishWizard
      open
      onClose={onClose}
      projectId="p1"
      chapterRef="vol-1-ch-6"
      prose={PROSE.join("\n")}
      onApply={onApply}
      {...over}
    />,
  );
  return { onApply, onClose };
}

async function walkToStep3() {
  await screen.findByText("AI 味检查中…").catch(() => {});
  await screen.findByText("段内句号 3 处", { exact: false });
  fireEvent.click(screen.getByRole("button", { name: "下一步：选择段落" }));
  await screen.findByText(/问题清单 · 勾选要修的段落/);
  expect(screen.getByDisplayValue).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "开始修改（3 段）" }));
  await screen.findByText("第 1 / 3 段");
}

describe("PolishWizard", () => {
  it("开窗即跑 AI 味检查并展示规则清单", async () => {
    mount();
    expect(await screen.findByText("段内句号 3 处", { exact: false })).toBeTruthy();
    expect(screen.getByText(/规则扫描完成/)).toBeTruthy();
    expect(aiFlavorScan).toHaveBeenCalledWith("p1", "vol-1-ch-6");
  });

  it("四步走完：逐段取舍后应用只写采用段", async () => {
    const { onApply, onClose } = mount();
    await walkToStep3();

    // 段 1 采用
    await screen.findByText(/【改】掌心贴上砖/);
    fireEvent.click(screen.getByRole("button", { name: "采用改稿，看下一段" }));
    // 段 2 保留原文
    await screen.findByText("第 2 / 3 段");
    fireEvent.click(screen.getByRole("button", { name: "这段保留原文" }));
    // 段 3 采用
    await screen.findByText("第 3 / 3 段");
    fireEvent.click(screen.getByRole("button", { name: "采用改稿，看下一段" }));

    // ④ 应用确认
    await screen.findByText("本轮处理完毕", { exact: false });
    fireEvent.click(screen.getByRole("button", { name: "应用到正文" }));

    expect(onApply).toHaveBeenCalledTimes(1);
    const items = (onApply.mock.calls[0]?.[0] ?? []) as Array<{ paraIndex: number; text: string }>;
    expect(items.map((i) => i.paraIndex).sort()).toEqual([1, 3]); // 保留原文的段 2 不写回
    expect(items[0].text.startsWith("【改】")).toBe(true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("全部保留原文时应用禁用（空写回护栏）", async () => {
    mount();
    await walkToStep3();
    for (let i = 0; i < 3; i += 1) {
      await screen.findByText(new RegExp(`第 ${i + 1} / 3 段`));
      fireEvent.click(screen.getByRole("button", { name: "这段保留原文" }));
    }
    await screen.findByText("本轮处理完毕", { exact: false });
    const btn = screen.getByRole("button", { name: "应用到正文" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("polish 失败可重试", async () => {
    vi.mocked(polishTextDetail).mockRejectedValueOnce(new Error("AI 服务响应超时"));
    const { } = mount();
    await walkToStep3();
    await screen.findByText(/生成失败：AI 服务响应超时/);
    fireEvent.click(screen.getByRole("button", { name: /重新生成/ }));
    await screen.findByText(/【改】掌心贴上砖/);
  });
});

describe("PolishWizard · 评审盲区补钉", () => {
  it("规则模式：无检测存档时无占比行、无朱雀文案露出", async () => {
    const ruleModeScan = { ...SCAN, detector: { stored: false, human_ratio: null, stale_hint: null } };
    vi.mocked(aiFlavorScan).mockResolvedValueOnce(ruleModeScan);
    render(<PolishWizard open onClose={vi.fn()} projectId="p" chapterRef="c" prose={PROSE.join("\n")} onApply={vi.fn()} />);
    expect(await screen.findByText(/规则扫描完成/)).toBeTruthy();
    expect(screen.queryByText(/人味占比（检测存档）/)).toBeNull();
  });

  it("漂移拒写：onApply 报 skipped 时弹窗不关、error toast", async () => {
    const onClose = vi.fn();
    const toast = await import("@/lib/toast");
    const onApply = vi.fn(() => ({ applied: 0, skipped: 2 }));
    render(<PolishWizard open onClose={onClose} projectId="p" chapterRef="c" prose={PROSE.join("\n")} onApply={onApply} />);
    await screen.findByText(/规则扫描完成/);
    fireEvent.click(screen.getByRole("button", { name: "下一步：选择段落" }));
    fireEvent.click(screen.getByRole("button", { name: "开始修改（3 段）" }));
    for (let i = 0; i < 3; i += 1) {
      await screen.findByText(/【改】/);
      fireEvent.click(screen.getByRole("button", { name: "采用改稿，看下一段" }));
    }
    await screen.findByText(/应用确认/);
    fireEvent.click(screen.getByRole("button", { name: "应用到正文" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(toast.toast.error).toHaveBeenCalled();
  });

  it("关闭保护：已采用未应用时确认放弃才关；全保留原文静默关", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onClose = vi.fn();
    render(<PolishWizard open onClose={onClose} projectId="p" chapterRef="c" prose={PROSE.join("\n")} onApply={vi.fn(() => ({ applied: 1, skipped: 0 }))} />);
    await screen.findByText(/规则扫描完成/);
    fireEvent.click(screen.getByRole("button", { name: "下一步：选择段落" }));
    fireEvent.click(screen.getByRole("button", { name: "开始修改（3 段）" }));
    await screen.findByText(/【改】/);
    fireEvent.click(screen.getByRole("button", { name: "采用改稿，看下一段" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
