import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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
