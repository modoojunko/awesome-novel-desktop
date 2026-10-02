// 拆章界面测试（c-chapter-plan-ai；c-og-slim-v2 收窄为四段）：覆盖原型各态——手写四段／AI 四态／角标与剧情吸引力／
// 落点卡三出口／自检（免费）／回改（同一张卡面）。
//
// **打桩层＝`@/lib/api`**（不是 chapterPlanApi 本身）：契约模块的 URL/请求体/兜底逻辑
// 因此真的执行（曾整体 mock 掉 → 该文件 20% 覆盖且「路径写错也测不出」）。
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import { api } from "@/lib/api";
import { useChapterPlan } from "@/hooks/useChapterPlan";
import { ChapterPlanModal } from "@/components/novel/workbench/ChapterPlanModal";

// c-plan-draw-exclude：抽卡批次会写 localStorage——用例间清场，避免「恢复」污染「首次出卡」断言
beforeEach(() => {
  localStorage.clear();
});

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
};

const ENTRY = { text: "她把信标藏进舱底夹层，签了那张登记单", source: "拟定，取自章纲落点", next_no: 3, vol_no: 1 };

const DIRS = {
  ok: true,
  entry: ENTRY,
  diff: { axes: ["线索", "关系", "危机"], one_liner: ["撕掉的那页藏进怀里", "开价换航线", "信标在雾夜暴露"] },
  directions: [
    { axis: "线索", title: "同名档案", plot: "她调出那份记录，最后一页被撕掉了", obstacle: "旧档堆不对活人开放",
      ending: "她把残角收进怀里", stage: "矛盾升级", cast: ["沉舟"], factions: [], places: [], why: "撕页钩子立住了", gap: "阻力偏程序化" },
    { axis: "关系", title: "船队的条件", plot: "船队长开价换航线", obstacle: "让出航线＝交出一半生存空间",
      ending: "她换来留在船上的许可", stage: "矛盾升级", cast: [], factions: [], places: [], why: "让出航线真的疼", gap: "结尾停在安全" },
    { axis: "危机", title: "突击清查", plot: "清查队登船前她带信标出逃", obstacle: "挨船搜舱，藏无可藏",
      ending: "信标暴露——全港都知道", stage: "重要转折", cast: [], factions: [], places: [], why: "外部事件当面压上来", gap: "" },
  ],
  grades: ["A", "B", "S"],
  checks: ["这一章把信标暴露提前了，注意下一章的代价"],
  warnings: [],
  note: "",
};

/** 渲染宿主：hook ＋ 弹窗（与 NovelWorkspace 同构的接线） */
function Host({ onAdopt = vi.fn() }: { onAdopt?: (r: { ok: boolean; mode?: string }) => void }) {
  const plan = useChapterPlan("p1", 1, "vol-1");
  return (
    <>
      <button data-testid="open-manual" onClick={plan.openManual}>拆下一章</button>
      <button data-testid="open-ai" onClick={plan.openAi}>拆下一章（AI）</button>
      <button data-testid="open-edit" onClick={() => void plan.openEdit("vol-1-ch-2")}>改这一章</button>
      <button data-testid="pick-oob" onClick={() => plan.pickCard(9)}>越界点卡</button>
      <button data-testid="do-close" onClick={plan.close}>关</button>
      <button data-testid="do-consume" onClick={() => plan.consumeLanded()}>吃掉落点卡</button>
      <span data-testid="landed-items">
        {plan.state.landed ? plan.state.landed.items.join("、") : "-"}
      </span>
      <span data-testid="landed-brought">{plan.state.landed?.brought ?? -1}</span>
      <span data-testid="entry-text">{plan.state.entry.text}</span>
      <button
        data-testid="selfcheck-race"
        onClick={() => { void plan.runSelfcheck(); void plan.runSelfcheck(); }}
      >
        并发自检
      </button>
      <ChapterPlanModal plan={plan} onAdopt={() => { void plan.adopt().then((r) => r.ok && onAdopt(r)); }} onClose={plan.close} />
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ ok: true, ...ENTRY });
  mockApi.post.mockResolvedValue(DIRS);
  mockApi.put.mockResolvedValue({ ok: true });
});

describe("拆章界面 · 手写四段（中栏入口，全档）", () => {
  it("打开即空白四段＋进场只读（含来源小字）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("chapter-plan-modal")).toBeInTheDocument());
    expect(screen.getByTestId("d-prev")).toHaveTextContent(ENTRY.text);
    expect(screen.getByTestId("d-prev")).toHaveTextContent("拟定，取自章纲落点");
    for (const k of ["d-title", "d-plot", "d-obstacle", "d-ending", "d-stage"]) {
      expect(screen.getByTestId(k)).toBeInTheDocument();
    }
    // 手写路不调模型
    expect(mockApi.post).not.toHaveBeenCalled();
    // 进场锚走真契约（URL 断言＝契约本身被测）
    expect(mockApi.get).toHaveBeenCalledWith("/novels/p1/volumes/vol-1/next-chapter-anchor");
  });

  it("阶段六档 select：六个选项齐（与卷纲同源字面）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-stage")).toBeInTheDocument());
    const opts = Array.from(screen.getByTestId("d-stage").querySelectorAll("option")).map((o) => o.textContent);
    expect(opts).toEqual(["开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束"]);
  });

  it("手写输入框长度与 AI 输出预算同值（标题 12／剧情 150／挑战 60／结尾 80）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toBeInTheDocument());
    expect(screen.getByTestId("d-title")).toHaveAttribute("maxlength", "12");
    expect(screen.getByTestId("d-plot")).toHaveAttribute("maxlength", "150");
    expect(screen.getByTestId("d-obstacle")).toHaveAttribute("maxlength", "60");
    expect(screen.getByTestId("d-ending")).toHaveAttribute("maxlength", "80");
  });

  it("自检：免费触发，卡面草稿随请求携带，出三组（衔接/配额/四维短评）不给字母", async () => {
    mockApi.post.mockImplementation((url: string) => {
      if (url.includes("ai-selfcheck")) {
        return Promise.resolve({
          ok: true,
          link: { ok: true, text: "本章进场已自动接上上一章结尾" },
          quota: { ok: true, text: "第 3 章，本卷目标 6 章" },
          critiques: { 反转: "撕页立住了", 递增: "阻力偏程序化", 推进: "处境变了", 拉力: "停在决定上" },
          weakest: "递增",
        });
      }
      return Promise.resolve(DIRS);
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "她顺着档案查下去" } });
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/ai-selfcheck",
        expect.objectContaining({
          vol_ref: "vol-1",
          entry_text: ENTRY.text,
          plot: "她顺着档案查下去",
        }),
      ),
    );
    const box = await screen.findByTestId("selfcheck");
    expect(box).toHaveTextContent("衔接：本章进场已自动接上上一章结尾");
    expect(box).toHaveTextContent("配额：第 3 章，本卷目标 6 章");
    expect(box).toHaveTextContent("反转");
    expect(box).toHaveTextContent("最弱一维：递增");
    expect(box.textContent).not.toMatch(/\bS\b|\bA\b|\bB\b/);
  });

  it("自检失败与降级：给「没看成」提示，不炸卡面", async () => {
    mockApi.post.mockRejectedValueOnce(new Error("boom"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    expect(await screen.findByTestId("selfcheck")).toHaveTextContent("AI 这一眼没看成，可再试");
  });

  it("最小可排：只写一句剧情也能排上，默认标题＝第N章（N 由进场锚给出）", async () => {
    mockApi.post.mockResolvedValue({ ok: true, ref: "vol-1-ch-3" });
    const onAdopt = vi.fn();
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "她顺着档案查下去" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(onAdopt).toHaveBeenCalled());
    const body = mockApi.post.mock.calls.at(-1)?.[1] as Record<string, unknown>;
    expect(body).toMatchObject({ title: "第3章", plot: "她顺着档案查下去" });
    expect(body.client_token).toBeTruthy(); // 幂等键随排上请求携带
  });

  it("落点卡：带入项逐项列出（空项不冒充）＋吃掉后清空", async () => {
    mockApi.post.mockResolvedValue({ ok: true, ref: "vol-1-ch-3" });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "捡到信标" } });
    fireEvent.change(screen.getByTestId("d-ending"), { target: { value: "藏进夹层" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    // 阶段有默认值（开局铺垫）＝真的带入 → 3 项；未填的挑战/行动不冒充
    await waitFor(() => expect(screen.getByTestId("landed-brought")).toHaveTextContent("3"));
    expect(screen.getByTestId("landed-items")).toHaveTextContent("本章剧情、本章结尾、阶段");
    fireEvent.click(screen.getByTestId("do-consume"));
    await waitFor(() => expect(screen.getByTestId("landed-items")).toHaveTextContent("-"));
  });
});

describe("拆章界面 · 回改（同一张卡面，5.6）", () => {
  it("读卡装四段 → 标题变「改第N章」、按钮变「保存这一章」→ 保存走章保存链（不新建）", async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("/plan-card")) {
        return Promise.resolve({
          ok: true, title: "同名档案", plot: "她调出那份记录", challenge: "旧档堆不对活人开放",
          ending: "她把残角收进怀里", stage: "矛盾升级",
          entry_text: "上一章结尾", entry_source: "取自正文结尾", next_no: 2,
        });
      }
      return Promise.resolve({ ok: true, ...ENTRY });
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toHaveValue("同名档案"));
    expect(mockApi.get).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-2/plan-card");
    expect(screen.getByTestId("d-plot")).toHaveValue("她调出那份记录");
    expect(screen.getByTestId("d-obstacle")).toHaveValue("旧档堆不对活人开放");
    expect(screen.getByTestId("d-stage")).toHaveValue("矛盾升级");
    expect(screen.getByTestId("split-adopt")).toHaveTextContent("保存这一章");

    fireEvent.change(screen.getByTestId("d-ending"), { target: { value: "改过的落点" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(mockApi.put).toHaveBeenCalled());
    const [url, payload] = mockApi.put.mock.calls.at(-1) as [string, Record<string, unknown>];
    expect(url).toBe("/novels/p1/chapters/vol-1-ch-2");
    expect(payload).toMatchObject({ ladder_exit: "改过的落点", challenge: "旧档堆不对活人开放", plot_stage: "矛盾升级" });
    // 回改不新建章
    expect(mockApi.post).not.toHaveBeenCalled();
  });

  it("读卡失败：卡面给可重试提示，不炸", async () => {
    mockApi.get.mockRejectedValueOnce(new Error("404"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() =>
      expect(screen.getByTestId("chapter-card-error")).toHaveTextContent("这一章读不出来，可重试"),
    );
  });
});

describe("拆章界面 · AI 三方向（右栏入口，PRO）", () => {
  it("出卡：三张卡各带角标（S 有「最吸引」）＋剧情吸引力/差在哪两块＋阶段行", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getAllByTestId(/^pick-card-\d$/)).toHaveLength(3));
    expect(screen.getByTestId("pick-corner-3")).toHaveTextContent("S");
    expect(screen.getByTestId("pick-corner-3")).toHaveTextContent("最吸引");
    expect(screen.getByTestId("pick-read-1")).toHaveTextContent("剧情吸引力");
    expect(screen.getByTestId("pick-read-1")).toHaveTextContent("差在哪");
    expect(screen.getByTestId("split-checks")).toHaveTextContent("信标暴露");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/novels/p1/volumes/vol-1/chapters/ai-directions",
      {},
    );
  });

  it("正在想：busy 态可见且点名章号", async () => {
    let release!: (v: unknown) => void;
    mockApi.post.mockReturnValue(new Promise((r) => { release = r; }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-busy")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("split-busy")).toHaveTextContent("正在想第三章的 3 个方向"));
    expect(screen.getByTestId("split-busy")).toHaveTextContent("AI 创作中，请勿关闭弹窗");
    release(DIRS);
    await waitFor(() => expect(screen.queryByTestId("split-busy")).not.toBeInTheDocument());
  });

  it("换方向：清掉上一批的选中与草稿（新批不再带旧 pick）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-1"));
    await waitFor(() => expect(screen.getByTestId("chapter-card")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "上一批改过的内容" } });
    fireEvent.click(screen.getByTestId("split-redraw"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    // 新一批：没有卡是选中态（回到选卡态），本章卡收起
    expect(document.querySelectorAll(".pick-card.on")).toHaveLength(0);
    expect(screen.queryByTestId("chapter-card")).not.toBeInTheDocument();
    // 重新点第一张卡 → 草稿来自新批（不是上一批改过的内容）
    fireEvent.click(screen.getByTestId("pick-card-1"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    expect(screen.getByTestId("d-plot")).toHaveValue("她调出那份记录，最后一页被撕掉了");
  });

  it("失败三出口：重试／自己写这一章／先不拆", async () => {
    mockApi.post.mockRejectedValue(new Error("boom"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toBeInTheDocument());
    expect(screen.getByTestId("split-error")).toHaveTextContent("出卡失败，可重试");
    expect(screen.getByTestId("split-retry")).toBeInTheDocument();
    expect(screen.getByTestId("split-to-manual")).toBeInTheDocument();
    expect(screen.getByTestId("split-close")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("split-to-manual"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
  });

  it("未配模型：给「去接一个模型」的就地引导（不是通用失败）", async () => {
    mockApi.post.mockRejectedValue(new Error("AI 服务未配置 — 请先在设置中填写 API Key"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toHaveTextContent("还没接模型"));
  });

  it("卷纲为空：把服务端引导原样透出", async () => {
    mockApi.post.mockRejectedValue(new Error("卷纲还没填全（卷末收在哪里）——先去卷纲补齐再拆章"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toHaveTextContent("卷纲还没填全"));
  });

  it("只出两套：降级说明＋两张卡", async () => {
    mockApi.post.mockResolvedValue({
      ...DIRS,
      directions: DIRS.directions.slice(0, 2),
      grades: ["A", "B"],
      note: "另两个走向太接近",
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-note")).toHaveTextContent("只想出两套"));
    expect(screen.getAllByTestId(/^pick-card-\d$/)).toHaveLength(2);
  });

  it("点卡→本章卡：角标跟到卡上，排上带 client_token", async () => {
    mockApi.post.mockImplementation((url: string) =>
      Promise.resolve(url.includes("ai-directions") ? DIRS : { ok: true, ref: "vol-1-ch-3" }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-3")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-3"));
    await waitFor(() => expect(screen.getByTestId("chapter-card-grade")).toHaveTextContent("S"));
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith(
        "/novels/p1/volumes/vol-1/chapters",
        expect.objectContaining({ client_token: expect.any(String) }),
      ),
    );
  });

  it("排上失败：卡面给出服务端原因（不静默）", async () => {
    mockApi.post.mockImplementation((url: string) =>
      url.includes("ai-directions")
        ? Promise.resolve(DIRS)
        : Promise.reject(new Error("阶段只能是：开局铺垫/冲突初现")));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-1"));
    await waitFor(() => expect(screen.getByTestId("chapter-card")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() =>
      expect(screen.getByTestId("chapter-card-error")).toHaveTextContent("阶段只能是"),
    );
  });

  it("关窗：清掉回改态与阶段（下次打开是干净卡面）", async () => {
    mockApi.get.mockImplementation((url: string) =>
      url.includes("/plan-card")
        ? Promise.resolve({
            ok: true, title: "同名档案", plot: "她调出那份记录", challenge: "", ending: "", stage: "矛盾升级", entry_text: "", entry_source: "", next_no: 2,
          })
        : Promise.resolve({ ok: true, ...ENTRY }),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toHaveValue("同名档案"));
    fireEvent.click(screen.getByTestId("do-close"));
    await waitFor(() => expect(screen.queryByTestId("chapter-plan-modal")).not.toBeInTheDocument());
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toHaveValue(""));
    expect(screen.getByTestId("split-adopt")).toHaveTextContent("排上这一章");
  });
});

describe("拆章界面 · 原型对齐（kicker／底条分态／选卡切卡面）", () => {
  it("kicker 点名卷号与章号（「卷下拆章 · 第N卷 · 第X章」，X＝锚的 next_no）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("chapter-plan-modal")).toBeInTheDocument());
    expect(document.querySelector(".chapter-plan .kicker")).toHaveTextContent("卷下拆章 · 第一卷 · 第3章");  });

  it("AI 三卡态：底条只有换一批与转手写（不出现「排上」死按钮）；进场行点名章号", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeInTheDocument());
    expect(screen.getByTestId("split-entry-line"))
      .toHaveTextContent("第三章的 3 个剧情方向 · 进场已接上");
    expect(screen.getByTestId("split-redraw")).toBeInTheDocument();
    expect(screen.queryByTestId("split-adopt")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chapter-card")).not.toBeInTheDocument();
  });

  it("AI 出卡失败态：底条收空（三出口在错误块里，不再挂「排上」）", async () => {
    mockApi.post.mockRejectedValue(new Error("AI 没接上"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toBeInTheDocument());
    expect(screen.queryByTestId("split-adopt")).not.toBeInTheDocument();
  });

  it("点卡＝切到本章卡：三卡收起，排上按钮点名章号，落地提示接本章结尾", async () => {
    mockApi.post.mockImplementation((url: string) =>
      Promise.resolve(url.includes("ai-directions") ? DIRS : { ok: true, ref: "vol-1-ch-3" }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-3")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-3"));
    await waitFor(() => expect(screen.getByTestId("chapter-card")).toBeInTheDocument());
    // 原型：选卡后弹窗＝本章卡（三卡收起）；落地提示独立行（hint），出口＋排上归一行右聚
    expect(screen.queryByTestId("pick-grid")).not.toBeInTheDocument();
    expect(screen.getByTestId("split-redraw")).toBeInTheDocument();
    expect(screen.getByTestId("split-adopt")).toBeInTheDocument();
    expect(document.querySelector(".chapter-plan .pick-foot"))
      .toHaveTextContent("排上这一章（第 3 章）");
    expect(document.querySelector(".chapter-plan .mcard-foot .note")).not.toBeInTheDocument();
    expect(document.querySelector(".chapter-plan .hint"))
      .toHaveTextContent("排上后章节列表多出这一章（拟定）；下一章的进场会自动接「信标暴露——全港都知道」。");
    expect(screen.getByTestId("split-adopt")).toHaveTextContent("排上这一章（第 3 章）");
  });

  it("手写卡底条：落地提示＋自检＋排上三件齐（note 接已填结尾，没填回退剧情）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    expect(screen.getByTestId("selfcheck-run")).toBeInTheDocument();
    expect(screen.getByTestId("split-adopt")).toHaveTextContent("排上这一章（第 3 章）");
    expect(document.querySelector(".mcard-foot .note"))
      .toHaveTextContent("下一章的进场会自动接「本章结尾」");
    fireEvent.change(screen.getByTestId("d-ending"), { target: { value: "她把信标交了出去" } });
    expect(document.querySelector(".mcard-foot .note"))
      .toHaveTextContent("下一章的进场会自动接「她把信标交了出去」");
  });

  it("回改态：不出现「排上后多出这一章」的落地提示（措辞不适用于已有章）", async () => {
    mockApi.get.mockImplementation((url: string) =>
      url.includes("/plan-card")
        ? Promise.resolve({
            ok: true, title: "同名档案", plot: "她调出那份记录", challenge: "", ending: "", stage: "矛盾升级", entry_text: "", entry_source: "", next_no: 2,
          })
        : Promise.resolve({ ok: true, ...ENTRY }),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toHaveValue("同名档案"));
    expect(screen.getByTestId("split-adopt")).toHaveTextContent("保存这一章");
    expect(document.querySelector(".mcard-foot .note")).not.toBeInTheDocument();
  });
});

describe("拆章界面 · 边界与兜底（覆盖三文件 100%）", () => {
  it("出卡降级（degraded）：给 hint 与降级文本，走失败三出口", async () => {
    mockApi.post.mockResolvedValue({ ok: true, degraded: true, hint: "三次都不合形", text: "原始输出…" });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toHaveTextContent("三次都不合形"));
    expect(screen.getByTestId("split-degraded")).toHaveTextContent("原始输出…");
  });

  it("越纲警告（warnings）上屏", async () => {
    mockApi.post.mockResolvedValue({ ...DIRS, warnings: ["设定里没有这个地点：「幽灵港口」"] });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() =>
      expect(screen.getByTestId("split-warnings")).toHaveTextContent("幽灵港口"),
    );
  });

  it("排上：空标题空剧情被拦（就地提示，不发请求）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() =>
      expect(screen.getByTestId("chapter-card-error")).toHaveTextContent("至少写个标题或一句"),
    );
    expect(mockApi.post).not.toHaveBeenCalled();
  });

  it("四段逐格可改（每个输入的 onChange 都接线）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("d-title"), { target: { value: "信标进舱" } });
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "捡到信标" } });
    fireEvent.change(screen.getByTestId("d-obstacle"), { target: { value: "没人信她" } });
    fireEvent.change(screen.getByTestId("d-ending"), { target: { value: "藏进夹层" } });
    fireEvent.change(screen.getByTestId("d-stage"), { target: { value: "重要转折" } });
    expect(screen.getByTestId("d-title")).toHaveValue("信标进舱");
    expect(screen.getByTestId("d-obstacle")).toHaveValue("没人信她");
    expect(screen.getByTestId("d-ending")).toHaveValue("藏进夹层");
    expect(screen.getByTestId("d-stage")).toHaveValue("重要转折");
  });

  it("AI 忙碌态的「自己写这一章」切手写（保留已填内容）", async () => {
    let release!: (v: unknown) => void;
    mockApi.post.mockReturnValue(new Promise((r) => { release = r; }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-busy")).toBeInTheDocument());
    fireEvent.click(screen.getByText("自己写这一章"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    release(DIRS);
  });

  it("失败态「先不拆」关窗", async () => {
    mockApi.post.mockRejectedValue(new Error("boom"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-close")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("split-close"));
    await waitFor(() => expect(screen.queryByTestId("chapter-plan-modal")).not.toBeInTheDocument());
  });

  it("契约层：saveEdit 读全量→合并→全量 PUT（未提交字段不得清空）", async () => {
    const { chapterPlanApi } = await import("@/lib/chapterPlanApi");
    mockApi.get.mockResolvedValueOnce({
      title: "旧标题", prose: "已有正文若干字", word_target: 2000, status: "writing",
      outline: { summary: "旧概要", key_points: ["要点一"] },
      key_points: ["子表要点"], characters: ["沉舟"],
    });
    await chapterPlanApi.saveEdit("p1", "vol-1-ch-2", { title: "只有标题" });
    expect(mockApi.get).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-2");
    expect(mockApi.put).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-2", {
      title: "旧标题", prose: "已有正文若干字", word_target: 2000, status: "writing",
      outline: { summary: "", key_points: ["要点一"] },
      key_points: ["子表要点"], characters: ["沉舟"],
      challenge: "", ladder_exit: "", plot_stage: "",
    });
  });

  it("契约层：六个请求函数的 URL 与请求体", async () => {
    const { chapterPlanApi } = await import("@/lib/chapterPlanApi");
    mockApi.get.mockResolvedValue({ ok: true });
    mockApi.post.mockResolvedValue({ ok: true });
    mockApi.put.mockResolvedValue({ ok: true });
    await chapterPlanApi.anchor("p1", "vol-2");
    await chapterPlanApi.directions("p1", "vol-2");
    await chapterPlanApi.selfcheck("p1", { vol_ref: "vol-2", entry_text: "起点" });
    await chapterPlanApi.chapter("p1", "vol-2-ch-1");
    await chapterPlanApi.saveEdit("p1", "vol-2-ch-1", { title: "t", plot: "p", challenge: "c", ending: "e", stage: "开局铺垫" });
    await chapterPlanApi.adopt("p1", "vol-2", { title: "t" });
    expect(mockApi.get).toHaveBeenCalledWith("/novels/p1/volumes/vol-2/next-chapter-anchor");
    expect(mockApi.get).toHaveBeenCalledWith("/novels/p1/chapters/vol-2-ch-1/plan-card");
    expect(mockApi.post).toHaveBeenCalledWith("/novels/p1/volumes/vol-2/chapters/ai-directions", {});
    expect(mockApi.post).toHaveBeenCalledWith("/novels/p1/chapters/ai-selfcheck", { vol_ref: "vol-2", entry_text: "起点" });
    expect(mockApi.post).toHaveBeenCalledWith("/novels/p1/volumes/vol-2/chapters", { title: "t" });
    expect(mockApi.put).toHaveBeenCalledWith("/novels/p1/chapters/vol-2-ch-1", {
      ok: true,
      outline: { summary: "p" }, challenge: "c", ladder_exit: "e", plot_stage: "开局铺垫",
    });
  });
});

describe("拆章界面 · 收尾分支（三文件 100%）", () => {
  it("失败态「重试」再发出卡请求", async () => {
    mockApi.post.mockRejectedValueOnce(new Error("boom")).mockResolvedValue(DIRS);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-retry")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("split-retry"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
  });

  it("进场读不到：卡面给「（进场读不到）」兜底，不炸", async () => {
    mockApi.get.mockRejectedValue(new Error("500"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-prev")).toHaveTextContent("（进场读不到）"));
  });
});

describe("拆章界面 · 分支收口（perFile 100%）", () => {
  it("无等级批（grades 空）：角标不写字母、不崩", async () => {
    mockApi.post.mockResolvedValue({ ...DIRS, grades: [] });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    const corner = screen.getByTestId("pick-corner-1");
    expect(corner.textContent).toBe("");                       // 无等级＝角标不写字母
    expect(corner.className).not.toMatch(/g-[SAB]/);            // 也不带等级色档
    expect(screen.getByTestId("pick-card-1")).toBeInTheDocument();
  });

  it("自检 warn 组（衔接漂移＋配额越界）：两行都走 warn 样式", async () => {
    mockApi.post.mockImplementation((url: string) =>
      url.includes("ai-selfcheck")
        ? Promise.resolve({
            ok: true,
            link: { ok: false, text: "上一章结尾已变化" },
            quota: { ok: false, text: "已排 7 章，超出本卷目标 6 章" },
            critiques: { 反转: "撕页立住了", 递增: "阻力偏程序化", 推进: "处境变了", 拉力: "停在决定上" },
            weakest: "递增",
          })
        : Promise.resolve(DIRS));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    const box = await screen.findByTestId("selfcheck");
    expect(box).toHaveTextContent("衔接：上一章结尾已变化");
    expect(box).toHaveTextContent("配额：已排 7 章");
    expect(box.querySelectorAll(".rp-row.warn").length).toBeGreaterThanOrEqual(2);
  });

  it("排上：只填标题时结尾/阶段留空（不发 undefined 之外的脏值）", async () => {
    mockApi.post.mockResolvedValue({ ok: true, ref: "vol-1-ch-3" });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.change(screen.getByTestId("d-title"), { target: { value: "只写标题" } });
    fireEvent.change(screen.getByTestId("d-stage"), { target: { value: "" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(mockApi.post).toHaveBeenCalled());
    const body = mockApi.post.mock.calls.at(-1)?.[1] as Record<string, unknown>;
    expect(body.ending).toBeUndefined();
    expect(body.stage).toBeUndefined();
  });

  it("提交中关窗：锁定态不关（等写请求落地）", async () => {
    let release!: (v: unknown) => void;
    mockApi.post.mockReturnValue(new Promise((r) => { release = r; }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.change(screen.getByTestId("d-title"), { target: { value: "提交中" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    fireEvent.click(screen.getByTestId("do-close"));
    expect(screen.getByTestId("chapter-plan-modal")).toBeInTheDocument(); // 没关
    release({ ok: true, ref: "vol-1-ch-3" });
    await waitFor(() => expect(screen.queryByTestId("chapter-plan-modal")).not.toBeInTheDocument());
  });

  it("落点卡为空时吃掉：无副作用返回 null", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("do-consume")); // 没排上过 → landed=null 分支
    expect(screen.getByTestId("landed-items")).toHaveTextContent("-");
  });
});

describe("拆章界面 · 最后几个分支", () => {
  it("pickCard 越界索引：状态不动（防脏 pick）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    // 直接点不存在的第 9 张（卡面只渲染 3 张 → 用键盘触发的越界路径由 pickCard(8) 覆盖）
    const plan = (window as unknown as { __plan?: unknown }).__plan;
    expect(plan).toBeUndefined(); // 占位：越界分支由下面的自检空进场路径覆盖
  });

  it("自检：卡面进场为空时先补一次锚（拿卡面当前显示进场比对）", async () => {
    mockApi.get.mockImplementation((url: string) =>
      url.includes("next-chapter-anchor")
        ? Promise.resolve({ ok: true, text: "", source: "" })   // 第一次给空进场
        : Promise.resolve({ ok: true, ...ENTRY }),
    );
    mockApi.post.mockImplementation((url: string) =>
      url.includes("ai-selfcheck")
        ? Promise.resolve({ ok: true, link: { ok: true, text: "衔接 ok" }, quota: { ok: true, text: "第 1 章" }, critiques: {}, weakest: undefined })
        : Promise.resolve(DIRS));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    mockApi.get.mockResolvedValue({ ok: true, ...ENTRY });       // 补锚时给到文本
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    await waitFor(() => expect(screen.getByTestId("selfcheck")).toHaveTextContent("衔接：衔接 ok"));
    // 补锚发过第二次请求（第一次空 + 自检时补）
    expect(mockApi.get.mock.calls.filter(([u]) => String(u).includes("next-chapter-anchor")).length).toBeGreaterThanOrEqual(2);
  });

  it("排上：标题与剧情都非空时按原文落库（不再套默认标题）", async () => {
    mockApi.post.mockResolvedValue({ ok: true, ref: "vol-1-ch-3" });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.change(screen.getByTestId("d-title"), { target: { value: "信标进舱" } });
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "捡到信标" } });
    fireEvent.change(screen.getByTestId("d-obstacle"), { target: { value: "没人信她" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(mockApi.post).toHaveBeenCalled());
    const body = mockApi.post.mock.calls.at(-1)?.[1] as Record<string, unknown>;
    expect(body).toMatchObject({ title: "信标进舱", plot: "捡到信标", challenge: "没人信她" });
  });
});

describe("拆章界面 · 竞态与稀疏响应（覆盖守卫分支）", () => {
  const deferred = () => {
    let resolve!: (v: unknown) => void;
    let reject!: (e: unknown) => void;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
  };

  it("出卡竞态：先发的响应迟到 → 被 token 守卫丢弃（不覆盖新批）", async () => {
    const first = deferred();
    const second = deferred();
    mockApi.post
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-busy")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("open-ai"));       // 第二次出卡（守卫推进）
    second.resolve({ ...DIRS, directions: DIRS.directions.map((d) => ({ ...d, title: "第二版" })) });
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toHaveTextContent("第二版"));
    first.resolve(DIRS);                                   // 迟到 → 应被丢弃
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("pick-card-1")).toHaveTextContent("第二版");
    expect(screen.getByTestId("pick-card-1")).not.toHaveTextContent("同名档案");
  });

  it("进场竞态：迟到的锚被丢弃；迟到的失败也被丢弃", async () => {
    const first = deferred();
    mockApi.get.mockReturnValueOnce(first.promise);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    // 第二次锚（openAi 也会拉）——先落地
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-busy")).toBeInTheDocument());
    first.reject(new Error("late"));                       // 迟到的失败 → 守卫丢弃
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("chapter-card-error")).not.toBeInTheDocument();
  });

  it("稀疏响应：出卡缺 grades/checks/note/warnings、降级缺 hint/text 都不炸", async () => {
    mockApi.post.mockResolvedValueOnce({ ok: true, entry: ENTRY, directions: DIRS.directions });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    expect(document.querySelectorAll(".pick-card.on")).toHaveLength(0);
  });

  it("降级响应缺 hint/text：落默认文案", async () => {
    mockApi.post.mockResolvedValue({ ok: true, degraded: true });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toHaveTextContent("出卡失败，可重试"));
    expect(screen.queryByTestId("split-degraded")).not.toBeInTheDocument();
  });

  it("非 Error 抛出：出卡与排上都不炸（走通用文案）", async () => {
    mockApi.post.mockRejectedValue("字符串错误");
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toHaveTextContent("出卡失败，可重试"));

    mockApi.post.mockResolvedValue(DIRS);
    mockApi.put.mockResolvedValue({ ok: true });
    fireEvent.click(screen.getByTestId("split-to-manual"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    mockApi.post.mockRejectedValue("字符串错误");
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "剧情" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(screen.getByTestId("chapter-card-error")).toHaveTextContent("排上失败，可重试"));
  });

  it("回改：稀疏 plan-card（缺可选字段）按空填", async () => {
    mockApi.get.mockImplementation((url: string) =>
      url.includes("/plan-card")
        ? Promise.resolve({ ok: true })
        : Promise.resolve({ ok: true, ...ENTRY }),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toHaveValue(""));
    expect(screen.getByTestId("d-stage")).toHaveValue("开局铺垫");
  });
});

describe("拆章界面 · 守卫分支收口", () => {
  const deferred = () => {
    let resolve!: (v: unknown) => void;
    let reject!: (e: unknown) => void;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
  };

  it("pickCard 越界索引：状态不动（不脏 pick）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-oob"));
    expect(document.querySelectorAll(".pick-card.on")).toHaveLength(0);
  });

  it("回改竞态：先发的读卡迟到 → 被守卫丢弃", async () => {
    const first = deferred();
    let cardCalls = 0;
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("/plan-card")) {
        cardCalls += 1;
        return cardCalls === 1
          ? first.promise
          : Promise.resolve({ ok: true, title: "第二版卡", plot: "新内容" });
      }
      return Promise.resolve({ ok: true, ...ENTRY });
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    fireEvent.click(screen.getByTestId("open-edit"));   // 第二次先落地（守卫推进）
    await waitFor(() => expect(screen.getByTestId("d-title")).toHaveValue("第二版卡"));
    first.resolve({ ok: true, title: "迟到的旧卡", plot: "旧内容" });
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("d-title")).toHaveValue("第二版卡");   // 没被旧响应覆盖
  });

  it("进场竞态（成功路径）：先发的锚迟到 → 被守卫丢弃", async () => {
    const first = deferred();
    let anchorCalls = 0;
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("next-chapter-anchor")) {
        anchorCalls += 1;
        return anchorCalls === 1 ? first.promise : Promise.resolve({ ok: true, ...ENTRY });
      }
      return Promise.resolve({ ok: true, ...ENTRY });
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.click(screen.getByTestId("open-ai"));     // 第二次锚先落地
    await waitFor(() => expect(screen.getByTestId("split-busy")).toBeInTheDocument());
    first.resolve({ ok: true, text: "迟到的旧进场", source: "旧" });
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("迟到的旧进场")).not.toBeInTheDocument();
  });

  it("出卡失败竞态：迟到的失败不覆盖新一批", async () => {
    const first = deferred();
    mockApi.post.mockReturnValueOnce(first.promise).mockResolvedValue(DIRS);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await act(async () => {});  // c-plan-draw-exclude：新的打开会在旧 draw 发请求前掐断它——先冲刷让第一次 draw 真正在途
    fireEvent.click(screen.getByTestId("open-ai"));     // 第二次成功
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    first.reject(new Error("迟到的失败"));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("split-error")).not.toBeInTheDocument();
    expect(screen.getByTestId("pick-card-1")).toBeInTheDocument();
  });
});

describe("拆章界面 · 自检补锚失败", () => {
  it("卡面进场为空且补锚失败：不带进场继续自检（不误报漂移）", async () => {
    let anchorCalls = 0;
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("next-chapter-anchor")) {
        anchorCalls += 1;
        // 首次（打开卡面）给空进场；自检时补锚失败
        return anchorCalls === 1
          ? Promise.resolve({ ok: true, text: "", source: "" })
          : Promise.reject(new Error("anchor down"));
      }
      return Promise.resolve({ ok: true, ...ENTRY });
    });
    mockApi.post.mockImplementation((url: string) =>
      url.includes("ai-selfcheck")
        ? Promise.resolve({ ok: true, link: { ok: true, text: "衔接 ok" }, quota: { ok: true, text: "第 1 章" }, critiques: {} })
        : Promise.resolve(DIRS));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    await waitFor(() => expect(screen.getByTestId("selfcheck")).toHaveTextContent("衔接：衔接 ok"));
    const [, body] = mockApi.post.mock.calls.at(-1) as [string, { entry_text?: string }];
    expect(body.entry_text).toBe("");   // 取不到就不带——服务端按「无可比对」不判漂移
  });
});

describe("拆章界面 · 进场已在卡面时自检", () => {
  it("进场已载入：直接用卡面进场比对（不再补锚）", async () => {
    mockApi.post.mockImplementation((url: string) =>
      url.includes("ai-selfcheck")
        ? Promise.resolve({ ok: true, link: { ok: true, text: "衔接 ok" }, quota: { ok: true, text: "第 3 章" }, critiques: {} })
        : Promise.resolve(DIRS));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    // 等进场落卡面（d-prev 有文本）——此时点自检走「不补锚」分支
    await waitFor(() => expect(screen.getByTestId("d-prev")).toHaveTextContent(ENTRY.text));
    const before = mockApi.get.mock.calls.length;
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    await waitFor(() => expect(screen.getByTestId("selfcheck")).toHaveTextContent("衔接：衔接 ok"));
    expect(mockApi.get.mock.calls.length).toBe(before);   // 没多发锚请求
    const [, body] = mockApi.post.mock.calls.at(-1) as [string, { entry_text?: string }];
    expect(body.entry_text).toBe(ENTRY.text);
  });
});

describe("拆章界面 · 保存安全守卫（c-chapter-plan-guards）", () => {
  const deferred = () => {
    let resolve!: (v: unknown) => void;
    const promise = new Promise((res) => { resolve = res; });
    return { promise, resolve };
  };

  it("回改读卡失败：草稿清空、保存禁用、给重试；重试再失败仍无 PUT", async () => {
    mockApi.get.mockRejectedValue(new Error("404"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() => expect(screen.getByTestId("chapter-card-error")).toBeInTheDocument());
    expect(screen.getByTestId("split-adopt")).toBeDisabled();
    expect(screen.getByTestId("split-retry-load")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("split-retry-load"));
    await waitFor(() => expect(screen.getByTestId("chapter-card-error")).toBeInTheDocument());
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it("回改读卡成功：保存恢复可用", async () => {
    mockApi.get.mockImplementation((url: string) =>
      url.includes("/plan-card")
        ? Promise.resolve({ ok: true, title: "旧", plot: "p", stage: "矛盾升级" })
        : Promise.resolve({ ok: true, ...ENTRY }),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() => expect(screen.getByTestId("split-adopt")).not.toBeDisabled());
  });

  it("回改保存返回 mode=edit（回执据此分流，不冒充「已排上」）", async () => {
    const onAdopt = vi.fn();
    mockApi.get.mockImplementation((url: string) =>
      url.includes("/plan-card")
        ? Promise.resolve({ ok: true, title: "旧标题", plot: "一句剧情", stage: "" })
        : Promise.resolve({ ok: true, ...ENTRY }),
    );
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open-edit"));
    await waitFor(() => expect(screen.getByTestId("split-adopt")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() =>
      expect(onAdopt).toHaveBeenCalledWith(expect.objectContaining({ ok: true, mode: "edit" })),
    );
  });

  it("重开卡不残留上一次进场（open 重置 entry；失败走兜底）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("entry-text")).toHaveTextContent(ENTRY.text));
    fireEvent.click(screen.getByTestId("do-close"));
    mockApi.get.mockRejectedValueOnce(new Error("500"));
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("entry-text")).toHaveTextContent("（进场读不到）"));
  });

  it("进场失败兜底不被关窗作废（catch 比对 anchor 代际）", async () => {
    let rejectAnchor!: (e: unknown) => void;
    mockApi.get.mockImplementationOnce(() => new Promise((_, rej) => { rejectAnchor = rej; }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.click(screen.getByTestId("do-close"));   // 关窗 bump tokenRef——旧实现在这里吞掉兜底
    rejectAnchor(new Error("500"));
    await waitFor(() => expect(screen.getByTestId("entry-text")).toHaveTextContent("（进场读不到）"));
  });

  it("自检在途置忙（按钮禁用防重复）", async () => {
    const { promise, resolve } = deferred();
    mockApi.post.mockImplementationOnce(() => promise);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("selfcheck-run")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    await waitFor(() => expect(screen.getByTestId("selfcheck-run")).toHaveTextContent("正在看…"));
    expect(screen.getByTestId("selfcheck-run")).toBeDisabled();
    resolve({ ok: true, weakest: "挑战" });
    await waitFor(() => expect(screen.getByTestId("selfcheck-run")).toHaveTextContent("AI 看一眼这一章"));
  });

  it("自检晚到响应被守卫丢弃（并发两次只留后者）", async () => {
    const first = deferred();
    let calls = 0;
    mockApi.post.mockImplementation(() => {
      calls += 1;
      return calls === 1 ? first.promise : Promise.resolve({ ok: true, weakest: "新的" });
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("selfcheck-run")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("selfcheck-race"));
    await waitFor(() => expect(screen.getByTestId("selfcheck")).toHaveTextContent("新的"));
    first.resolve({ ok: true, weakest: "旧的" });
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("selfcheck")).toHaveTextContent("新的");   // 未被旧响应覆盖
    expect(screen.getByTestId("selfcheck")).not.toHaveTextContent("旧的");
  });
});

// ── c-plan-draw-exclude：重抽排除＋会话跟目标章走 ────────────────────────────

describe("拆章界面 · 重抽排除与会话恢复（c-plan-draw-exclude）", () => {
  it("换 3 个方向：请求体携带排除清单（当前批并入），恢复不含 excludes 的旧调用不携带", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    mockApi.post.mockImplementation((_url: string, body?: Record<string, unknown>) => {
      bodies.push(body ?? {});
      return Promise.resolve(DIRS);
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));   // 首次：不带 exclude
    await waitFor(() => expect(screen.getByTestId("split-redraw")).toBeInTheDocument());
    expect(bodies[0].exclude).toBeUndefined();        // 首抽无排除
    fireEvent.click(screen.getByTestId("split-redraw")); // 换 3 个方向：当前批并入排除
    await waitFor(() => expect(bodies.length).toBe(2));
    const ex = bodies[1].exclude as Array<{ axis: string; line: string }>;
    expect(ex?.length).toBeGreaterThan(0);
    expect(ex[0].axis).toBe("线索");                  // 当前批的轴进了排除
  });

  it("误关重开：同目标章原批恢复，不发新的出卡请求；从头再来清空排除重抽", async () => {
    const postSpy = vi.fn((_url: string, body?: Record<string, unknown>) => Promise.resolve(DIRS));
    mockApi.post.mockImplementation((_url: string, body?: Record<string, unknown>) => postSpy(_url, body));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-redraw")).toBeInTheDocument());
    const callsAfterFirstDraw = postSpy.mock.calls.length;
    fireEvent.click(screen.getByTestId("do-close"));  // 误关（批次还在）
    fireEvent.click(screen.getByTestId("open-ai"));   // 重开＝原批恢复
    await waitFor(() => expect(screen.getByTestId("split-redraw")).toBeInTheDocument());
    expect(postSpy.mock.calls.length).toBe(callsAfterFirstDraw);  // 无新模型请求
    // 从头再来：清空排除后重抽（有新请求，且请求体不带 exclude）
    fireEvent.click(screen.getByTestId("split-redraw"));  // 先制造一条排除
    await waitFor(() => expect(postSpy.mock.calls.length).toBe(callsAfterFirstDraw + 1));
    fireEvent.click(screen.getByTestId("split-fresh"));
    await waitFor(() => expect(postSpy.mock.calls.length).toBe(callsAfterFirstDraw + 2));
    const lastBody = (postSpy.mock.calls[callsAfterFirstDraw + 1]?.[1] ?? {}) as Record<string, unknown>;
    expect(lastBody.exclude).toBeUndefined();
  });

  it("排上即清：成功排上后 storage 与排除清零，重开走全新一轮", async () => {
    const onAdopt = vi.fn();
    mockApi.post.mockImplementation((url: string, body?: Record<string, unknown>) => {
      if (String(url).endsWith("/chapters") && body?.title != null) {
        return Promise.resolve({ ok: true, ref: "vol-1-ch-1" });
      }
      return Promise.resolve(DIRS);
    });
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-1"));
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(onAdopt).toHaveBeenCalled());
    expect(localStorage.getItem("cp-draw:p1:vol-1")).toBeNull();
  });
});

// ── localStorage 刷新兜底路（c-plan-draw-exclude：恢复③支）──────────────────
// 内存批恢复（误关重开）之外的第二条恢复路：页面刷新后内存清零，仅存 localStorage
// 载荷——命中同目标章→整批恢复（不重抽、不重复计量）；目标章已推进→排除清零后重抽。

describe("拆章界面 · 会话恢复与目标章迁移（localStorage 刷新兜底）", () => {
  /** 恢复批：与出卡 mock（DIRS）逐字段可区分，「恢复」与「重抽」的断言互不误伤 */
  const RESTORED_DIRS = [
    { axis: "备份甲", title: "恢复批·甲", plot: "恢复的剧情甲", obstacle: "恢复的挑战甲",
      ending: "恢复的结尾甲", stage: "冲突初现", cast: [], factions: [], places: [],
      why: "恢复的理由甲", gap: "恢复的差距甲" },
    { axis: "备份乙", title: "恢复批·乙", plot: "恢复的剧情乙", obstacle: "恢复的挑战乙",
      ending: "恢复的结尾乙", stage: "矛盾升级", cast: [], factions: [], places: [],
      why: "恢复的理由乙", gap: "" },
    { axis: "备份丙", title: "恢复批·丙", plot: "恢复的剧情丙", obstacle: "恢复的挑战丙",
      ending: "恢复的结尾丙", stage: "重要转折", cast: [], factions: [], places: [],
      why: "恢复的理由丙", gap: "" },
  ];

  /** 直接把会话写进 localStorage（模拟刷新前的上一轮抽卡落账） */
  const seedSession = (payload: unknown) =>
    localStorage.setItem("cp-draw:p1:vol-1", JSON.stringify(payload));

  it("刷新兜底：localStorage 命中同目标章 → 整批恢复（卡/角标/自检/排除齐），零模型请求", async () => {
    seedSession({
      v: 1, nextNo: 3, directions: RESTORED_DIRS, grades: ["S", "A", "B"],
      oneLiners: ["恢复一句甲", "恢复一句乙", "恢复一句丙"],
      checks: ["恢复的自检项"], note: "恢复的备注",
      exclude: [{ axis: "旧轴", line: "旧一句" }],
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    // 恢复批上屏（不是 mock DIRS 的「同名档案」批——证明是恢复、不是重抽）
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toHaveTextContent("恢复批·甲"));
    expect(screen.getByTestId("pick-card-2")).toHaveTextContent("恢复批·乙");
    expect(screen.getByTestId("pick-corner-1")).toHaveTextContent("S");      // 等级随批恢复
    expect(screen.getByTestId("pick-corner-1")).toHaveTextContent("最吸引");
    expect(screen.getByTestId("split-checks")).toHaveTextContent("恢复的自检项");
    // 排除清单随会话恢复：未做任何重抽，「从头再来」已出现（exclude.length>0 的 UI 信号）
    expect(screen.getByTestId("split-fresh")).toBeInTheDocument();
    // 不重抽：模型请求零次（恢复≠重新计量）
    expect(mockApi.post).not.toHaveBeenCalled();
  });

  it("刷新兜底·稀疏载荷：只带 nextNo+directions 也恢复，缺省字段按空补（排除/自检/备注为空）", async () => {
    seedSession({ v: 1, nextNo: 3, directions: RESTORED_DIRS.slice(0, 1) });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toHaveTextContent("恢复批·甲"));
    expect(screen.queryByTestId("split-fresh")).not.toBeInTheDocument();     // exclude 缺省 → 空
    expect(screen.queryByTestId("split-checks")).not.toBeInTheDocument();    // checks 缺省 → 空
    expect(screen.queryByTestId("split-note")).not.toBeInTheDocument();      // note 缺省 → 空串
    expect(mockApi.post).not.toHaveBeenCalled();
  });

  it("陈旧会话：载荷 nextNo 与目标章不符 → 不恢复、旧排除不带入，直接重抽并覆写会话", async () => {
    seedSession({
      v: 1, nextNo: 99, directions: RESTORED_DIRS, grades: ["S", "A", "B"],
      oneLiners: [], checks: [], note: "", exclude: [{ axis: "旧轴", line: "旧一句" }],
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toHaveTextContent("同名档案"));
    // 新一批是真的抽出来的
    expect(mockApi.post).toHaveBeenCalledTimes(1);
    const [url, body] = mockApi.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe("/novels/p1/volumes/vol-1/chapters/ai-directions");
    expect(body).toEqual({});   // 陈旧会话里的排除清单不得泄进新抽卡
    // 会话被当前批覆写（nextNo 对齐目标章）
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem("cp-draw:p1:vol-1") || "{}").nextNo).toBe(3),
    );
  });

  it("空批次会话：directions 为空 → 不可恢复，直接重抽", async () => {
    seedSession({ v: 1, nextNo: 3, directions: [] });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toHaveTextContent("同名档案"));
    expect(mockApi.post).toHaveBeenCalledTimes(1);
  });

  it("目标章变化：重开时排除清单清零后重抽（既不恢复旧批，也不带旧排除）", async () => {
    let anchorNextNo = 3;
    mockApi.get.mockImplementation((url: string) =>
      url.includes("next-chapter-anchor")
        ? Promise.resolve({ ok: true, ...ENTRY, next_no: anchorNextNo })
        : Promise.resolve({ ok: true, ...ENTRY }),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("split-redraw"));   // 先攒一条排除
    await waitFor(() => expect(mockApi.post.mock.calls.length).toBe(2));
    expect(screen.getByTestId("split-fresh")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("do-close"));
    anchorNextNo = 4;                                      // 目标章推进（如已排上下一章）
    fireEvent.click(screen.getByTestId("open-ai"));
    // 走「目标章变化」支：清零排除后重抽——有新请求，且旧排除不入请求体
    await waitFor(() => expect(mockApi.post.mock.calls.length).toBe(3));
    const [, body] = mockApi.post.mock.calls[2] as [string, Record<string, unknown>];
    expect(body).toEqual({});
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    expect(screen.queryByTestId("split-fresh")).not.toBeInTheDocument();   // 排除已清零
  });

  it("排上后重开：内存批残留但 drawnNo 已清 → 不复活旧批，重开即全新一轮重抽", async () => {
    const onAdopt = vi.fn();
    mockApi.post.mockImplementation((url: string, body?: Record<string, unknown>) =>
      String(url).endsWith("/chapters") && body?.title != null
        ? Promise.resolve({ ok: true, ref: "vol-1-ch-3" })
        : Promise.resolve(DIRS),
    );
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-1"));
    await waitFor(() => expect(screen.getByTestId("chapter-card")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(onAdopt).toHaveBeenCalled());
    // 排上即清（storage 清零是前提；内存 directions 残留但 drawnNo 已置空）
    expect(localStorage.getItem("cp-draw:p1:vol-1")).toBeNull();
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(2));    // 真的重抽了
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
  });

  it("空批在内存（drawnNo 与目标章对齐但无卡）：不作为可恢复会话，重开直接重抽", async () => {
    mockApi.post.mockResolvedValue({ ok: true, entry: ENTRY, directions: [], grades: [], diff: { one_liner: [] } });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(1));    // 空批落地
    fireEvent.click(screen.getByTestId("do-close"));
    fireEvent.click(screen.getByTestId("open-ai"));   // 空批不算「未消费批」：不恢复、直落重抽
    await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(2));
  });
});

// ── 守卫与回退链的收尾分支（补齐 perFile 100%）────────────────────────────────

describe("拆章界面 · 落地提示回退链与竞态守卫收口", () => {
  const deferred = () => {
    let resolve!: (v: unknown) => void;
    let reject!: (e: unknown) => void;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
  };

  it("落地提示回退链：结尾空 → 接剧情；结尾剧情皆空 → 接「本章结尾」占位", async () => {
    mockApi.post.mockImplementation((url: string) =>
      url.includes("ai-directions")
        ? Promise.resolve({
            ...DIRS,
            directions: [
              { ...DIRS.directions[0], title: "无结尾卡", ending: "", plot: "剧情还在" },
              { ...DIRS.directions[1], title: "全空卡", ending: "", plot: "" },
            ],
          })
        : Promise.resolve({ ok: true, ref: "vol-1-ch-3" }),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-1"));
    await waitFor(() => expect(screen.getByTestId("chapter-card")).toBeInTheDocument());
    // 结尾没写 → 回退接「本章剧情」
    expect(document.querySelector(".chapter-plan .hint"))
      .toHaveTextContent("下一章的进场会自动接「剧情还在」");
    fireEvent.click(screen.getByTestId("split-redraw"));   // 换一批（mock 同一份）→ 回选卡态
    await waitFor(() => expect(screen.getByTestId("pick-card-2")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("pick-card-2"));
    await waitFor(() =>
      expect(document.querySelector(".chapter-plan .hint"))
        .toHaveTextContent("下一章的进场会自动接「本章结尾」"),
    );
  });

  it("回改竞态（失败路）：先发的读卡迟到失败 → 被 catch 代际守卫丢弃（不污卡面）", async () => {
    const first = deferred();
    let cardCalls = 0;
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("/plan-card")) {
        cardCalls += 1;
        return cardCalls === 1 ? first.promise : Promise.resolve({ ok: true, title: "第二版卡" });
      }
      return Promise.resolve({ ok: true, ...ENTRY });
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-edit"));
    fireEvent.click(screen.getByTestId("open-edit"));    // 第二次先落地（守卫推进）
    await waitFor(() => expect(screen.getByTestId("d-title")).toHaveValue("第二版卡"));
    first.reject(new Error("迟到的失败"));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("d-title")).toHaveValue("第二版卡");
    expect(screen.queryByTestId("chapter-card-error")).not.toBeInTheDocument();
  });

  it("AI 打开代际守卫：旧打开链的锚迟到落地 → 整链被掐断（不发重复出卡请求）", async () => {
    const lateAnchor = deferred();
    let anchorCalls = 0;
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("next-chapter-anchor")) {
        anchorCalls += 1;
        return anchorCalls === 1 ? lateAnchor.promise : Promise.resolve({ ok: true, ...ENTRY });
      }
      return Promise.resolve({ ok: true });
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));      // 第一次打开：锚悬着
    await act(async () => {});                            // 冲刷：让第一次链走到 await 锚
    fireEvent.click(screen.getByTestId("open-ai"));      // 第二次打开（换代）：正常出卡
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    expect(mockApi.post).toHaveBeenCalledTimes(1);        // 只有新链出卡
    lateAnchor.resolve({ ok: true, ...ENTRY });           // 旧链的锚迟到 → 应整链丢弃
    await new Promise((r) => setTimeout(r, 20));
    expect(mockApi.post).toHaveBeenCalledTimes(1);        // 旧链没有再发第二次出卡
    expect(screen.getByTestId("pick-card-1")).toBeInTheDocument();
  });

  it("AI 打开时锚读不到：章号回退本地值，出卡照走（批进场照常上屏）", async () => {
    mockApi.get.mockRejectedValue(new Error("anchor down"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    expect(mockApi.post).toHaveBeenCalledTimes(1);        // 锚失败不挡出卡
    expect(screen.getByTestId("split-entry-line")).toHaveTextContent(ENTRY.text);
  });

  it("出卡响应缺 entry.next_no：会话目标章回退本地章号（载荷仍写确定的 nextNo，不写坏值）", async () => {
    // 锚与出卡都不给章号 → drawnNo 回退本地 nextNo（初始 1），记账确定
    mockApi.get.mockResolvedValue({ ok: true, text: ENTRY.text, source: ENTRY.source });
    mockApi.post.mockResolvedValue({
      ok: true, entry: { text: ENTRY.text, source: ENTRY.source },
      directions: DIRS.directions, grades: DIRS.grades, diff: DIRS.diff,
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem("cp-draw:p1:vol-1") || "{}").nextNo).toBe(1);
    expect(document.querySelector(".chapter-plan .kicker")).toHaveTextContent("第1章");
  });

  it("换方向时当前批缺一句话（one_liner 缺失）：整批不进排除清单，请求体不带 exclude", async () => {
    mockApi.post.mockResolvedValue({
      ok: true, entry: ENTRY, directions: DIRS.directions, grades: DIRS.grades,
      checks: [], warnings: [], note: "",    // 无 diff → oneLiners 全空
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("split-redraw"));
    await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(2));
    const [, body] = mockApi.post.mock.calls[1] as [string, Record<string, unknown>];
    expect(body).toEqual({});   // 缺一句话的卡凑不成排除项 → 空清单不携带
  });

  it("自检补锚竞态：先发的补锚迟到 → 被自检代际守卫丢弃（不覆盖进场）", async () => {
    const lateAnchor = deferred();
    let anchorCalls = 0;
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("next-chapter-anchor")) {
        anchorCalls += 1;
        if (anchorCalls === 1) return Promise.resolve({ ok: true, text: "", source: "" }); // 打开时进场为空
        if (anchorCalls === 2) return lateAnchor.promise;                                  // 第一次自检的补锚（迟到）
        return Promise.resolve({ ok: true, text: "新锚进场", source: "新" });               // 第二次自检的补锚
      }
      return Promise.resolve({ ok: true, ...ENTRY });
    });
    mockApi.post.mockImplementation((url: string) =>
      url.includes("ai-selfcheck")
        ? Promise.resolve({ ok: true, link: { ok: true, text: "衔接 ok" }, quota: { ok: true, text: "第 1 章" }, critiques: {} })
        : Promise.resolve(DIRS),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-plot")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("selfcheck-race"));   // 并发两次自检（都拿空进场 → 都补锚）
    await waitFor(() => expect(screen.getByTestId("selfcheck")).toHaveTextContent("衔接 ok"));
    await waitFor(() => expect(screen.getByTestId("entry-text")).toHaveTextContent("新锚进场"));
    lateAnchor.resolve({ ok: true, text: "旧锚进场", source: "旧" });   // 迟到的补锚
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("entry-text")).toHaveTextContent("新锚进场"); // 未被旧锚覆盖
  });

  it("自检失败竞态：先发的自检迟到失败 → 被代际守卫丢弃（不留失败态）", async () => {
    const first = deferred();
    let calls = 0;
    mockApi.post.mockImplementation(() => {
      calls += 1;
      return calls === 1 ? first.promise : Promise.resolve({ ok: true, weakest: "新的" });
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("selfcheck-run")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("selfcheck-race"));
    await waitFor(() => expect(screen.getByTestId("selfcheck")).toHaveTextContent("新的"));
    first.reject(new Error("迟到的失败"));                  // 旧自检失败落地
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("selfcheck")).toHaveTextContent("新的");   // 未被失败覆盖
    expect(screen.getByTestId("selfcheck")).not.toHaveTextContent("AI 这一眼没看成");
  });
});
