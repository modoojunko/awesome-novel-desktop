import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AiAssistPanel } from "@/components/novel/workbench/AiAssistPanel";

// ---------------------------------------------------------------------------
// B 组（storyline col-ai）：右栏 AI 助手随页签切换——c-ai-rail-shared 起全局统一
// ra-* 布局（与设定域 AiWriterAssistant 同模板）：ra-head 头部 + ai-target 作用域行
// + ra-step 能力行（名称＋描述）+ ra-foot 声明。检测族（onAiCheck）/精修族
//（onPromptRefine）/缺项补全（onFillGaps）全部接线；重复动作已撤。
// 注意：模板行点击经 busyRef 在途互斥（同 tick 连点会被吞），连续点击需 await act。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn(), request: vi.fn() }));
vi.mock("@/lib/api", () => ({
  api: apiState,
  request: apiState.request,
}));

const OG_STATS = {
  reqOk: 1, // 必填两项里已填一项（分母＝REQ_FIELDS.length）
  planWords: 1800,
  plotCount: 2,
  castCount: 1,
  missingLabels: ["主情绪"],
};

function renderPanel(tab: string, extra: Partial<Parameters<typeof AiAssistPanel>[0]> = {}) {
  const cb = { onAiDraft: vi.fn(), onSimulate: vi.fn() };
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
      canAiDraft
      aiDrafting={false}
      {...cb}
      {...extra}
    />,
  );
  return cb;
}

/** 模板行点击经 busyRef 互斥：点完等一个微任务，busyRef 归零后下一点才生效 */
async function clickRow(name: RegExp) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
}

beforeEach(() => {
  apiState.get.mockReset().mockRejectedValue(new Error("no stubs"));
  apiState.request.mockReset().mockRejectedValue(new Error("no stubs"));
});

describe("AiAssistPanel（随页签，ra-* 统一布局）", () => {
  it("章纲页签：统计卡不进右栏（上移头部 meta 行）＋还缺进作用域行＋动作行全真", async () => {
    const onFillGaps = vi.fn();
    const onAiCheck = vi.fn();
    const cb = renderPanel("og", { onFillGaps, onAiCheck });
    expect(screen.getByText("AI 助手 · 章纲")).toBeTruthy();
    // 统计卡退役；口径进 ai-target 作用域行
    expect(document.querySelector(".rail-stats")).toBeNull();
    const target = document.querySelector(".ai-target")?.textContent ?? "";
    expect(target).toContain("还缺 1 项");
    expect(target).toContain("主情绪");
    // 「补全缺失字段」行描述带还缺数量
    expect(screen.getByText("只补还缺的 1 项，一稿回填")).toBeTruthy();

    await clickRow(/AI 起草/);
    expect(cb.onAiDraft).toHaveBeenCalled();
    await clickRow(/剧情推演/);
    expect(cb.onSimulate).toHaveBeenCalled();

    await clickRow(/补全缺失字段/);
    expect(onFillGaps).toHaveBeenCalled();
    await clickRow(/与卷纲冲突检测/);
    expect(onAiCheck).toHaveBeenCalledWith("volume_conflict");
  });

  it("章纲页签：无缺项/补全中时「补全缺失字段」禁用", async () => {
    renderPanel("og", {
      onFillGaps: vi.fn(),
      ogStats: { ...OG_STATS, missingLabels: [] },
    });
    expect(screen.getByRole("button", { name: /补全缺失字段/ })).toBeDisabled();

    renderPanel("og", { onFillGaps: vi.fn(), gapsLoading: true });
    const all = screen.getAllByRole("button", { name: /补全缺失字段/ });
    const last = all[all.length - 1] as HTMLButtonElement;
    expect(last.disabled).toBe(true);
  });

  it("正文页签：统计＋提示词状态进作用域行；动作行含精修；选中才可点（走 onAiSelection）", async () => {
    const onAiSelection = vi.fn();
    const onPromptRefine = vi.fn();
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/prompt-sources")) return { total_chars: 1234, cast_count: 3 };
      throw new Error("unexpected " + p);
    });
    apiState.request.mockImplementation(async (p: string) => {
      if (p.endsWith("/prompts")) return [];
      throw new Error("unexpected " + p);
    });
    renderPanel("prose", { onAiSelection, onPromptRefine });
    const target = document.querySelector(".ai-target")?.textContent ?? "";
    expect(target).toContain("500 字");
    expect(target).toContain("28%"); // 500/1800
    expect(screen.getByText("AI 助手 · 正文")).toBeTruthy();
    // c-prompt-tab-retire：提示词状态与组装来源收编正文页签作用域行（懒取回填后）
    await waitFor(() =>
      expect(document.querySelector(".ai-target")?.textContent).toContain("组装来源 1,234 字"),
    );
    expect(document.querySelector(".ai-target")?.textContent).toContain("自动组装");
    // 精修两行随提示词页签退役收编（提案制）
    await clickRow(/补全负向约束/);
    expect(onPromptRefine).toHaveBeenCalledWith("negative");
    await clickRow(/精简提示词/);
    expect(onPromptRefine).toHaveBeenCalledWith("concise");
    // 未选中 → 润色/扩写/压缩禁用并带 hint
    const polish = screen.getByRole("button", { name: /段落润色/ }) as HTMLButtonElement;
    expect(polish.disabled).toBe(true);
    expect(screen.getAllByText(/先在正文选中一段/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: /生成正文/ })).toBeTruthy();

    // 选中 → 压缩可点，走 onAiSelection（capture 取自 proseRef）
    const capture = { text: "选中的一段" };
    renderPanel("prose", {
      onAiSelection,
      aiState: { hasSelection: true, compressLoading: false } as never,
      proseRef: { current: { captureNow: () => capture } } as never,
    });
    // 第二次 render 追加进容器：取最后一份（选中态）的行
    const btns = screen.getAllByRole("button", { name: /压缩啰嗦段落/ }) as HTMLButtonElement[];
    const btn = btns[btns.length - 1];
    expect(btn.disabled).toBe(false);
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(onAiSelection).toHaveBeenCalledWith("compress", capture);
  });

  it("设定/关系/伏笔三入口按类触发收尾（未归档禁用）", async () => {
    const onRunReconcile = vi.fn();
    const { unmount } = render(
      (() => {
        const cb = { onAiDraft: vi.fn(), onSimulate: vi.fn() };
        return (
          <AiAssistPanel
            projectId="p1"
            chapterRef="vol-1-ch-2"
            tab="settings"
            isPro
            ogStats={OG_STATS}
            wordCount={0}
            planWords={null}
            archived
            canAiDraft={false}
            aiDrafting={false}
            onRunReconcile={onRunReconcile}
            {...cb}
          />
        );
      })(),
    );
    await clickRow(/提取本章变化/);
    expect(onRunReconcile).toHaveBeenCalledWith("set_changes");
    unmount();

    renderPanel("relations", { archived: true, onRunReconcile });
    await clickRow(/识别角色与物品变化/);
    expect(onRunReconcile).toHaveBeenCalledWith("relations");
    unmount();

    renderPanel("hooks", { archived: true, onRunReconcile });
    await clickRow(/登记新伏笔/);
    expect(onRunReconcile).toHaveBeenCalledWith("hooks");
    unmount();

    // 未归档：三入口禁用
    renderPanel("settings", { archived: false, onRunReconcile });
    const all = screen.getAllByRole("button", { name: /提取本章变化/ });
    expect((all[all.length - 1] as HTMLButtonElement).disabled).toBe(true);
  });

  it("文风/关系/伏笔页签：检测动作接线（走 onAiCheck，撤重复项）", async () => {
    const onAiCheck = vi.fn();

    renderPanel("style", { onAiCheck });
    await clickRow(/文风一致性检查/);
    expect(onAiCheck).toHaveBeenCalledWith("style_consistency");
    await clickRow(/标记偏离段落/);
    expect(onAiCheck).toHaveBeenCalledWith("style_deviations");

    renderPanel("relations", { onAiCheck });
    // 与 reconcile 关系收尾同产出 → 不设入口（ADJUSTMENTS #27 ⑫）
    expect(screen.queryByRole("button", { name: /本章关系变化检测/ })).toBeNull();
    await clickRow(/关系冲突检测/);
    expect(onAiCheck).toHaveBeenCalledWith("relations_conflict");
    await clickRow(/建议补边/);
    expect(onAiCheck).toHaveBeenCalledWith("relation_suggest");

    renderPanel("hooks", { onAiCheck });
    // 与 reconcile 伏笔收尾的「收束」提案同产出 → 不设入口
    expect(screen.queryByRole("button", { name: /建议本章回收/ })).toBeNull();
    await clickRow(/伏笔冲突检测/);
    expect(onAiCheck).toHaveBeenCalledWith("hooks_conflict");
  });

  it("免费态：整卡 locked，动作行可点但被门控拦下走统一升级出口", async () => {
    const onUpgrade = vi.fn();
    const onAiCheck = vi.fn();
    renderPanel("style", { isPro: false, onAiCheck, onUpgrade });
    expect(document.querySelector(".rail-assist.locked")).toBeTruthy();
    expect(screen.getByText(/未解锁 · 升级 PRO 后本书 AI 即可用/)).toBeTruthy();
    const row = screen.getByRole("button", { name: /文风一致性检查/ }) as HTMLButtonElement;
    expect(row.disabled).toBe(false); // 模板免费态＝可见可点，点击被门控拦下
    await clickRow(/文风一致性检查/);
    expect(onAiCheck).not.toHaveBeenCalled();
    expect(onUpgrade).toHaveBeenCalled();
  });

  it("伏笔页签：悬置/本章埋下统计（作用域行）与检测动作", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/hooks")) {
        return {
          data: {
            items: [
              { status: "active", introduced_chapter_id: "c2", resolved_chapter_id: null },
              { status: "resolved", introduced_chapter_id: "c1", resolved_chapter_id: "c2" },
            ],
          },
        };
      }
      if (p.endsWith("/volumes")) {
        return [
          {
            name: "vol-1",
            chapters: [
              { id: "c1", chapter: 1, ref: "vol-1-ch-1" },
              { id: "c2", chapter: 2, ref: "vol-1-ch-2" },
            ],
          },
        ];
      }
      throw new Error("unexpected " + p);
    });
    const onAiCheck = vi.fn();
    renderPanel("hooks", { chapterRef: "vol-1-ch-2", onAiCheck });
    expect(screen.getByText("AI 助手 · 伏笔")).toBeTruthy();
    await screen.findByText(/台账 2 条/);
    await clickRow(/伏笔冲突检测/);
    expect(onAiCheck).toHaveBeenCalledWith("hooks_conflict");
  });
});
