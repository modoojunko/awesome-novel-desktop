// 右栏接入（c-character-intro 3.3/4.2）：og 页签「盘点出场人物」能力行（免费可点）＋
// 行级 PRO 映射只作用章纲页签（其余四行 ra-off＋「需 PRO」）＋其余页签维持整卡锁＋
// 空章/归档禁用 hint＋data-aiact/data-od-id 锚＋档位角标＋busy 走 railData。
import { setVerifyCache } from "@/lib/licenseCache";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { AiAssistPanel } from "@/components/novel/workbench/AiAssistPanel";

const apiState = vi.hoisted(() => ({ get: vi.fn(), request: vi.fn() }));
vi.mock("@/lib/api", () => ({
  api: apiState,
  request: apiState.request,
}));

const OG_STATS = {
  reqOk: 2,
  planWords: 1800,
  plotCount: 2,
  castCount: 1,
  missingLabels: [],
};

// 档位种子（3.5 夹具翻 v2）
const V2_MAX = ["ai-plan", "chapter-review", "settings-ai-fields", "style-suggest",
  "outline-advanced-fields", "ai-model", "ai-generate", "prompt-panel", "ai-detect",
  "ai-plot", "ai-polish", "style-quant"];
function seedTier(features: string[], tier?: string) {
  setVerifyCache({
    tier: tier ?? (features.length ? "max" : "free"),
    is_member: features.length > 0,
    entitlement: { v: 2, features, limits: { max_projects: null } },
  });
}

function renderPanel(
  tab: string,
  extra: Partial<Parameters<typeof AiAssistPanel>[0]> = {},
  feats: string[] = V2_MAX,
  tier?: string,
) {
  seedTier(feats, tier);
  const cb = {
    onSimulate: vi.fn(),
    onPlotDraw: vi.fn(),
    onCastReview: vi.fn(),
    onAiCheck: vi.fn(),
    onUpgrade: vi.fn(),
  };
  render(
    <AiAssistPanel
      projectId="p1"
      chapterRef="vol-1-ch-2"
      tab={tab}
      isPro
      ogStats={OG_STATS}
      wordCount={500}
      planWords={1800}
      archived={false}
      {...cb}
      {...extra}
    />,
  );
  return cb;
}

beforeEach(() => {
  apiState.get.mockReset().mockRejectedValue(new Error("no stubs"));
  apiState.request.mockReset().mockRejectedValue(new Error("no stubs"));
});

describe("章纲页签行级门控（只作用 og 页签）", () => {
  it("免费：四行全锁——盘点收标准（需开通）、推演需 MAX、冲突需 PRO（10-05 拍板）＋副行升级出口", async () => {
    const cb = renderPanel("og", { isPro: false }, []);
    const cast = screen.getByTestId("og-cast-review") as HTMLButtonElement;
    expect(cast.disabled).toBe(true); // 盘点/抽卡归 ai-plan（标准起）
    expect(cast.getAttribute("data-aiact")).toBe("cast-review");
    expect(cast.getAttribute("data-od-id")).toBe("rail-cast");
    for (const name of [/剧情推演/, /补全缺失字段/, /剧情抽卡/]) {
      const row = screen.getByRole("button", { name }) as HTMLButtonElement;
      expect(row.disabled).toBe(true);
      expect(row.className).toContain("ra-off");
    }
    expect(screen.getAllByText("需开通").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("需 MAX").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("需 PRO").length).toBeGreaterThanOrEqual(1);
    expect(document.querySelector(".rail-assist.locked")).toBeNull();
    // 说明文案已删（行级 hint 自解释）：免费仍保留升级出口，卡头角标＝当前档位
    expect(screen.queryByText(/按套餐逐档解锁/)).toBeNull();
    expect(screen.getByTestId("plan-badge").textContent).toBe("免费版");
    fireEvent.click(screen.getByTestId("og-upgrade-btn"));
    expect(cb.onUpgrade).toHaveBeenCalled();
    // 盘点行免费不触发回调
    fireEvent.click(cast);
    expect(cb.onCastReview).not.toHaveBeenCalled();
  });

  it("MAX：四行可点，盘点行照常；点击生成类行走各自回调", async () => {
    const cb = renderPanel("og");
    const plot = screen.getByRole("button", { name: /剧情抽卡/ }) as HTMLButtonElement;
    expect(plot.disabled).toBe(false);
    await act(async () => {
      fireEvent.click(plot);
    });
    expect(cb.onPlotDraw).toHaveBeenCalled();
    expect(screen.queryByTestId("og-upgrade-exit")).toBeNull();
  });

  it("PRO（真 pro 快照：无 ai-plot/polish/quant）：推演锁「需 MAX」，其余行可用，升级出口不出现", () => {
    const PRO_FEATS = V2_MAX.filter((k) => !["ai-plot", "ai-polish", "style-quant"].includes(k));
    renderPanel("og", {}, PRO_FEATS, "pro");
    // 已到 ai-generate：不再被推升级（行提示自解释，说明文案已删）；角标＝PRO 会员
    expect(screen.queryByTestId("og-upgrade-exit")).toBeNull();
    expect(screen.queryByText(/按套餐逐档解锁/)).toBeNull();
    expect(screen.getByTestId("plan-badge").textContent).toBe("PRO 会员");
    expect((screen.getByTestId("og-plot-draw") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId("og-cast-review") as HTMLButtonElement).disabled).toBe(false);
    const sim = screen.getByTestId("og-simulate") as HTMLButtonElement;
    expect(sim.disabled).toBe(true);
    expect(screen.getByText("需 MAX")).toBeTruthy();
  });

  it("空章禁用（hint「先写剧情再盘点」）；归档禁用（hint「本章已归档」）", () => {
    renderPanel("og", { castEmpty: true });
    const cast = screen.getByTestId("og-cast-review") as HTMLButtonElement;
    expect(cast.disabled).toBe(true);
    expect(screen.getByText("先写剧情再盘点")).toBeTruthy();

    renderPanel("og", { archived: true });
    const rows = screen.getAllByTestId("og-cast-review") as HTMLButtonElement[];
    expect(rows[rows.length - 1].disabled).toBe(true);
    // 归档 hint（多行同文案，取到即可）
    expect(screen.getAllByText("本章已归档").length).toBeGreaterThan(0);
  });

  it("busy 走 railData：盘点在途行呈「生成中…」", () => {
    renderPanel("og", { castBusy: true });
    expect(screen.getByText("生成中…")).toBeTruthy();
  });

  it("其余页签维持 member_required 整卡锁定（免费不因本 change 放行）", () => {
    renderPanel("prose", { isPro: false }, []);
    expect(document.querySelector(".rail-assist.locked")).toBeTruthy();
    renderPanel("hooks", { isPro: false }, []);
    expect(document.querySelectorAll(".rail-assist.locked").length).toBeGreaterThanOrEqual(2);
    // og 页签同渲染里不锁（对照）
    renderPanel("og", { isPro: false });
    const cards = document.querySelectorAll(".rail-assist");
    expect(cards[cards.length - 1].classList.contains("locked")).toBe(false);
  });
});
