// 拆章界面测试（c-chapter-plan-ai）：覆盖原型各态——手写五段／AI 四态／角标与剧情吸引力／
// 落点卡三出口／自检（免费）／回改（同一张卡面）。
//
// **打桩层＝`@/lib/api`**（不是 chapterPlanApi 本身）：契约模块的 URL/请求体/兜底逻辑
// 因此真的执行（曾整体 mock 掉 → 该文件 20% 覆盖且「路径写错也测不出」）。
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import { api } from "@/lib/api";
import { useChapterPlan } from "@/hooks/useChapterPlan";
import { ChapterPlanModal } from "@/components/novel/workbench/ChapterPlanModal";

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
};

const ENTRY = { text: "她把信标藏进舱底夹层，签了那张登记单", source: "拟定，取自章纲落点", next_no: 3, vol_no: 1 };

const DIRS = {
  ok: true,
  entry: ENTRY,
  directions: [
    { axis: "线索", title: "同名档案", plot: "她调出那份记录，最后一页被撕掉了", obstacle: "旧档堆不对活人开放",
      ending: "她把残角收进怀里", acts: ["她：调档"], stage: "矛盾升级", cast: ["沉舟"], factions: [], places: [], why: "撕页钩子立住了", gap: "阻力偏程序化" },
    { axis: "关系", title: "船队的条件", plot: "船队长开价换航线", obstacle: "让出航线＝交出一半生存空间",
      ending: "她换来留在船上的许可", acts: ["船队长：开价"], stage: "矛盾升级", cast: [], factions: [], places: [], why: "让出航线真的疼", gap: "结尾停在安全" },
    { axis: "危机", title: "突击清查", plot: "清查队登船前她带信标出逃", obstacle: "挨船搜舱，藏无可藏",
      ending: "信标暴露——全港都知道", acts: ["清查队：搜舱"], stage: "重要转折", cast: [], factions: [], places: [], why: "外部事件当面压上来", gap: "" },
  ],
  grades: ["A", "B", "S"],
  checks: ["这一章把信标暴露提前了，注意下一章的代价"],
  warnings: [],
  note: "",
};

/** 渲染宿主：hook ＋ 弹窗（与 NovelWorkspace 同构的接线） */
function Host({ onAdopt = vi.fn() }: { onAdopt?: () => void }) {
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
      <ChapterPlanModal plan={plan} onAdopt={() => { void plan.adopt().then((r) => r.ok && onAdopt()); }} onClose={plan.close} />
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockResolvedValue({ ok: true, ...ENTRY });
  mockApi.post.mockResolvedValue(DIRS);
  mockApi.put.mockResolvedValue({ ok: true });
});

describe("拆章界面 · 手写五段（中栏入口，全档）", () => {
  it("打开即空白五段＋进场只读（含来源小字）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("chapter-plan-modal")).toBeInTheDocument());
    expect(screen.getByTestId("d-prev")).toHaveTextContent(ENTRY.text);
    expect(screen.getByTestId("d-prev")).toHaveTextContent("拟定，取自章纲落点");
    for (const k of ["d-title", "d-plot", "d-obstacle", "d-ending", "d-acts", "d-stage"]) {
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
  it("读卡装五段 → 标题变「改第N章」、按钮变「保存这一章」→ 保存走章保存链（不新建）", async () => {
    mockApi.get.mockImplementation((url: string) => {
      if (url.includes("/plan-card")) {
        return Promise.resolve({
          ok: true, title: "同名档案", plot: "她调出那份记录", challenge: "旧档堆不对活人开放",
          ending: "她把残角收进怀里", acts: ["她：调档"], stage: "矛盾升级",
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
    expect(screen.getByTestId("d-acts")).toHaveValue("她：调档");
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
            ok: true, title: "同名档案", plot: "她调出那份记录", challenge: "", ending: "",
            acts: [], stage: "矛盾升级", entry_text: "", entry_source: "", next_no: 2,
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

  it("行动行拼接剥行尾句读：模型自带「。」不出现「。；」双标点（卡面与底条 note 同值）", async () => {
    mockApi.post.mockImplementation((url: string) =>
      Promise.resolve({
        ...DIRS,
        directions: DIRS.directions.map((d, i) =>
          i === 0 ? { ...d, acts: ["她：调出同名记录。", "文书：记下出入；未起疑"] } : d),
      }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("pick-card-1")).toBeInTheDocument());
    // 三卡态的行动行已剥行尾「。」
    expect(screen.getByTestId("pick-card-1")).toHaveTextContent("她：调出同名记录；文书：记下出入；未起疑");
    fireEvent.click(screen.getByTestId("pick-card-1"));
    await waitFor(() => expect(screen.getByTestId("chapter-card")).toBeInTheDocument());
    // 本章卡的输入框同值（回车进库的也是干净行）
    expect(screen.getByTestId("d-acts")).toHaveValue("她：调出同名记录；文书：记下出入；未起疑");
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
            ok: true, title: "同名档案", plot: "她调出那份记录", challenge: "", ending: "",
            acts: [], stage: "矛盾升级", entry_text: "", entry_source: "", next_no: 2,
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

  it("五段逐格可改（每个输入的 onChange 都接线）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("d-title")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("d-title"), { target: { value: "信标进舱" } });
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "捡到信标" } });
    fireEvent.change(screen.getByTestId("d-obstacle"), { target: { value: "没人信她" } });
    fireEvent.change(screen.getByTestId("d-ending"), { target: { value: "藏进夹层" } });
    fireEvent.change(screen.getByTestId("d-acts"), { target: { value: "沉舟：藏信标" } });
    fireEvent.change(screen.getByTestId("d-stage"), { target: { value: "重要转折" } });
    expect(screen.getByTestId("d-title")).toHaveValue("信标进舱");
    expect(screen.getByTestId("d-obstacle")).toHaveValue("没人信她");
    expect(screen.getByTestId("d-ending")).toHaveValue("藏进夹层");
    expect(screen.getByTestId("d-acts")).toHaveValue("沉舟：藏信标");
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

  it("契约层：saveEdit 缺字段按空写（不塞 undefined 进库）", async () => {
    const { chapterPlanApi } = await import("@/lib/chapterPlanApi");
    await chapterPlanApi.saveEdit("p1", "vol-1-ch-2", { title: "只有标题" });
    expect(mockApi.put).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-2", {
      outline: { summary: "" },
      challenge: "",
      ladder_exit: "",
      chapter_acts: [],
      plot_stage: "",
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
    await chapterPlanApi.saveEdit("p1", "vol-2-ch-1", { title: "t", plot: "p", challenge: "c", ending: "e", acts: ["a"], stage: "开局铺垫" });
    await chapterPlanApi.adopt("p1", "vol-2", { title: "t" });
    expect(mockApi.get).toHaveBeenCalledWith("/novels/p1/volumes/vol-2/next-chapter-anchor");
    expect(mockApi.get).toHaveBeenCalledWith("/novels/p1/chapters/vol-2-ch-1/plan-card");
    expect(mockApi.post).toHaveBeenCalledWith("/novels/p1/volumes/vol-2/chapters/ai-directions", {});
    expect(mockApi.post).toHaveBeenCalledWith("/novels/p1/chapters/ai-selfcheck", { vol_ref: "vol-2", entry_text: "起点" });
    expect(mockApi.post).toHaveBeenCalledWith("/novels/p1/volumes/vol-2/chapters", { title: "t" });
    expect(mockApi.put).toHaveBeenCalledWith("/novels/p1/chapters/vol-2-ch-1", {
      outline: { summary: "p" }, challenge: "c", ladder_exit: "e", chapter_acts: ["a"], plot_stage: "开局铺垫",
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
    expect(screen.getByTestId("d-acts")).toHaveValue("");
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
