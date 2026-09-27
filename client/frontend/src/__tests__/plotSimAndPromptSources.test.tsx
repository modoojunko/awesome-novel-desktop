import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { strategyLineOf } from "@/components/novel/workbench/SimModal";
import SimModal from "@/components/novel/workbench/SimModal";
import type { SimResult } from "@/lib/plotSim";

// ---------------------------------------------------------------------------
// plot-sim（剧情推演弹窗）
// c-prompt-tab-retire：PromptPane 六来源展示随提示词页签退役删除
// 四期尾行为：回合推进需先选走法；走完全程才出现「收进章纲」；
// 走法行 = 任一回合一「拗」则中途接意外（原型 simAdopt 口径）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api", () => ({ request: apiState.request }));
vi.mock("@/lib/toast", () => ({
  toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

const SIM: SimResult = {
  ok: true,
  source: "ai",
  entry: "她解开了最后一根系泊。",
  exit: "她把信交给了陌生人",
  prev_label: "第 1 章",
  cast: ["林晚"],
  rounds: [
    {
      n: 1,
      beat: "匿名信被尾随",
      who: "林晚",
      place: "渡口",
      time: "清晨",
      at: "承上：她解开了最后一根系泊。",
      shift: "她决定不再等船",
      moves: [
        { k: "顺", tone: "ok", label: "林晚顺着当前节奏动手", out: "顺线落地" },
        { k: "拗", tone: "warn", label: "林晚先被外力打断一下", out: "被船夫叫住" },
      ],
    },
    {
      n: 2,
      beat: "渡口对质",
      who: "林晚",
      place: "渡口",
      time: "清晨",
      at: "推向本章结尾",
      shift: "信到了陌生人手里",
      moves: [
        { k: "顺", tone: "ok", label: "林晚顺着当前节奏动手", out: "对质完成" },
        { k: "拗", tone: "warn", label: "林晚先被外力打断一下", out: "对质被打断" },
      ],
    },
  ],
};

beforeEach(() => {
  apiState.request.mockReset();
});

describe("strategyLineOf", () => {
  it("任一回合一拗 → 中途先接一次意外；全顺 → 顺着章纲节奏推进", () => {
    expect(strategyLineOf({ 1: "ok", 2: "ok" })).toBe(
      "推演走法 · 顺着章纲节奏推进，不多加波折",
    );
    expect(strategyLineOf({ 1: "ok", 2: "warn" })).toBe(
      "推演走法 · 中途先接一次意外，再拉回主线",
    );
  });
});

describe("SimModal", () => {
  const openWith = async (onAdopt = vi.fn().mockResolvedValue(true)) => {
    apiState.request.mockResolvedValue(SIM);
    render(
      <SimModal
        open
        onClose={() => {}}
        projectId="p1"
        chapterRef="vol-1-ch-2"
        chapterLabel="第 2 章 · 风起渡口"
        planWords={2500}
        onAdopt={onAdopt}
      />,
    );
    await screen.findByTestId("sim-round-1");
    return onAdopt;
  };

  it("回合按步展开；未选走法不能推进；展开末回合即出「收进章纲」", async () => {
    await openWith();
    expect(apiState.request).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-2/simulate",
      { method: "POST" },
    );
    // 第 2 回合未展开
    expect(screen.getByTestId("sim-round-2").textContent).toContain("还没走到");
    // 未选走法点下一回合 → 不推进
    fireEvent.click(screen.getByTestId("sim-next"));
    expect(screen.getByTestId("sim-round-2").textContent).toContain("还没走到");
    // 选顺 → 推进到末回合（原型口径：step==total 即 done，末回合仍待定）
    fireEvent.click(screen.getByTestId("sim-pick-1-ok"));
    expect(screen.getByTestId("sim-round-1").textContent).toContain("走法已定 · 顺");
    fireEvent.click(screen.getByTestId("sim-next"));
    expect(screen.getByTestId("sim-round-2").textContent).toContain("待你定");
    expect(screen.getByTestId("sim-adopt")).toBeTruthy();
    expect(screen.queryByTestId("sim-next")).toBeNull();
  });

  it("收进章纲把走法行交给上层（含拗 → 中途意外口径）", async () => {
    const onAdopt = await openWith();
    fireEvent.click(screen.getByTestId("sim-pick-1-warn"));
    fireEvent.click(screen.getByTestId("sim-next"));
    fireEvent.click(screen.getByTestId("sim-pick-2-ok"));
    fireEvent.click(screen.getByTestId("sim-adopt"));
    await waitFor(() =>
      expect(onAdopt).toHaveBeenCalledWith(
        "推演走法 · 中途先接一次意外，再拉回主线",
      ),
    );
  });
});
