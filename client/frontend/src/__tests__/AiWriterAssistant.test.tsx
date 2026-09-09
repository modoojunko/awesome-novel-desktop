import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AiWriterAssistant from "@/components/novel/settings/AiWriterAssistant";

// AI 写作助手卡片（genre-signup-redesign tasks 3.2 / D4）
const ROWS = [
  { key: "check", name: "体检", desc: "六段逐项查达标 / 缺失", onClick: vi.fn() },
  { key: "fill", name: "补缺失", desc: "只补缺的段", onClick: vi.fn() },
  { key: "polish", name: "润色", desc: "保原意压 AI 味", onClick: vi.fn() },
];

describe("AiWriterAssistant", () => {
  it("渲染 PRO 徽标 + 标题 + 三个并列能力行（名称上/描述下）", () => {
    const { container } = render(<AiWriterAssistant rows={ROWS} footNote="输入：书名 + 简介本文" />);
    expect(screen.getByText("PRO")).toBeTruthy();
    expect(screen.getByText("AI 写作助手")).toBeTruthy();
    const steps = container.querySelectorAll(".ra-step");
    expect(steps).toHaveLength(3);
    for (const r of ROWS) {
      expect(screen.getByText(r.name)).toBeTruthy();
      expect(screen.getByText(r.desc)).toBeTruthy();
    }
    expect(screen.getByText(/输入：书名 \+ 简介本文/)).toBeTruthy();
  });

  it("每行整行可点且带 data-aiact（e2e 定位）", () => {
    const { container } = render(<AiWriterAssistant rows={ROWS} footNote="x" />);
    for (const r of ROWS) {
      const btn = container.querySelector(`[data-aiact="${r.key}"]`);
      expect(btn).toBeTruthy();
      expect(btn?.tagName).toBe("BUTTON");
    }
  });

  it("前置未满足的能力行置灰 + 「先体检」，点击不触发（D14/O-3）", () => {
    const onFill = vi.fn();
    const { container } = render(
      <AiWriterAssistant
        rows={[{ key: "fill", name: "补缺失", desc: "只补缺的段", onClick: onFill, disabled: true, hint: "先体检" }]}
        footNote="x"
      />,
    );
    const btn = container.querySelector('[data-aiact="fill"]') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.className).toContain("ra-off");
    expect(screen.getByText("先体检")).toBeTruthy();
    fireEvent.click(btn);
    expect(onFill).not.toHaveBeenCalled();
  });

  it("无 LicenseProvider（免费兜底）时卡片锁定，点击不触发能力回调", () => {
    const onClick = vi.fn();
    const { container } = render(
      <AiWriterAssistant rows={[{ ...ROWS[0], onClick }]} footNote="x" />,
    );
    // settings-ai-fields memberOnly=true，无 entitlement 快照时静态兜底＝未解锁
    expect(container.querySelector(".rail-assist.locked")).toBeTruthy();
    fireEvent.click(container.querySelector('[data-aiact="check"]')!);
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("AiWriterAssistant · ai_state 一次分派（D13）", () => {
  it("aiState=ready 时直接执行能力", () => {
    const onClick = vi.fn();
    render(
      <AiWriterAssistant
        rows={[{ key: "check", name: "体检", desc: "x", onClick }]}
        footNote="x"
        aiState="ready"
      />,
    );
    fireEvent.click(screen.getByText("体检"));
    expect(onClick).toHaveBeenCalled();
  });

  it("aiState=no_key → onBlocked('no_key')，能力不执行", () => {
    const onClick = vi.fn();
    const onBlocked = vi.fn();
    render(
      <AiWriterAssistant
        rows={[{ key: "check", name: "体检", desc: "x", onClick }]}
        footNote="x"
        aiState="no_key"
        onBlocked={onBlocked}
      />,
    );
    fireEvent.click(screen.getByText("体检"));
    expect(onClick).not.toHaveBeenCalled();
    expect(onBlocked).toHaveBeenCalledWith("no_key");
  });

  it("aiState=missing_model → 卡片文案提示先选模型", () => {
    render(
      <AiWriterAssistant
        rows={[{ key: "check", name: "体检", desc: "x", onClick: vi.fn() }]}
        footNote="x"
        aiState="missing_model"
      />,
    );
    expect(screen.getByText(/先在本书选择模型/)).toBeTruthy();
  });
});

describe("AiWriterAssistant · 在途禁用（tasks 9.4.14）", () => {
  it("请求在途时行禁用，重复点击不并发发请求", async () => {
    let resolve!: () => void;
    const pending = new Promise<void>((r) => {
      resolve = r;
    });
    const onClick = vi.fn(() => pending);
    const { container } = render(
      <AiWriterAssistant
        rows={[{ key: "check", name: "体检", desc: "x", onClick }]}
        footNote="x"
        aiState="ready"
      />,
    );

    const row = container.querySelector('[data-aiact="check"]') as HTMLButtonElement;
    fireEvent.click(row);
    await waitFor(() => expect(row.disabled).toBe(true));
    fireEvent.click(row);
    fireEvent.click(row);
    expect(onClick).toHaveBeenCalledTimes(1);

    resolve();
    await waitFor(() => expect(row.disabled).toBe(false));
  });
});
