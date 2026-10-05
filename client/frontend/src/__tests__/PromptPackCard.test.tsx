import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import PromptPackCard from "@/components/novel/license/PromptPackCard";

// c-prompt-pack-client 4.2：写作能力四态卡——文案口径与出口（§13「写作能力」，
// 内部术语零出现）
const tierState = { pack: null as unknown };

vi.mock("@/hooks/useTier", () => ({
  useTier: () => ({ refetch: vi.fn(), pack: tierState.pack }),
}));
vi.mock("@/lib/auth", () => ({
  isLoggedIn: () => true,
}));
vi.mock("@/lib/api", () => ({
  api: { post: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({ phase: "ready" }) },
}));
vi.mock("@/lib/toast", () => ({
  toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

describe("PromptPackCard", () => {
  beforeEach(() => {
    tierState.pack = null;
  });

  it("已就绪不渲染（全静默）", () => {
    tierState.pack = { phase: "ready", version: "7" };
    const { container } = render(<PromptPackCard />);
    expect(container.firstChild).toBeNull();
  });

  it("获取中不渲染（不打扰）", () => {
    tierState.pack = { phase: "syncing" };
    const { container } = render(<PromptPackCard />);
    expect(container.firstChild).toBeNull();
  });

  it("失败态出「重新获取」＋「复制诊断信息」，无内部术语", () => {
    tierState.pack = { phase: "failed", reason: "cdn_unreachable" };
    render(<PromptPackCard />);
    expect(screen.getByText("写作能力没有就绪")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新获取" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "复制诊断信息" })).toBeTruthy();
    const body = document.body.textContent ?? "";
    for (const banned of ["提示词包", "manifest", "验签", "prompt", "pack"]) {
      expect(body.includes(banned)).toBe(false);
    }
  });

  it("档位不够出升级出口", () => {
    tierState.pack = { phase: "tier_denied", reason: "tier" };
    render(<PromptPackCard />);
    expect(screen.getByText("该能力随 MAX 提供")).toBeTruthy();
    expect(screen.getByRole("button", { name: "去升级" })).toBeTruthy();
  });

  it("未装（missing）出登录语义卡（已登录则为重新获取）", () => {
    tierState.pack = { phase: "missing" };
    render(<PromptPackCard />);
    expect(screen.getByText("登录后获取写作能力")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新获取" })).toBeTruthy();
  });
});
