import { beforeEach, describe, expect, it, vi } from "vitest";
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import GenreSettingForm, {
  type GenreHandle,
} from "@/components/novel/settings/GenreSettingForm";
import { GENRE_FLAVORS } from "@/lib/genreVocab";

/** mind（烧脑博弈）的起点句：充当「另一颗胶囊的起点原句」初始态（重载后高亮丢失的形态）。 */
const MIND_NOTE = GENRE_FLAVORS.find((f) => f.key === "mind")!.promiseNote;

// 题材六格面板（genre-signup-redesign tasks 4.1 / D18 新契约）
const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState, request: vi.fn() }));

const aiState = vi.hoisted(() => ({ genreAi: vi.fn() }));
const toastState = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
}));

vi.mock("@/lib/ai", () => ({
  genreAi: aiState.genreAi,
  aiBlockReason: (e: { reason?: string }) => e?.reason ?? null,
}));

vi.mock("@/lib/toast", () => ({ toast: toastState }));

function renderPanel(initial: unknown = {}) {
  apiState.get.mockImplementation((path: string) => {
    if (path === "/genres/candidates") return Promise.resolve({});
    return Promise.resolve(initial);
  });
  const ref = createRef<GenreHandle>();
  const receipts: Array<{ text: string; undo: () => void } | null> = [];
  /** 「让助手办」分派捕获（c-agent-panel-consolidate：面板只组指令发 dock） */
  const asks: string[] = [];
  const utils = render(
    <GenreSettingForm
      ref={ref}
      projectId="p1"
      settingKey="genre"
      onAskAssistant={(m) => asks.push(m)}
      onReceiptChange={(r) => receipts.push(r)}
    />,
  );
  /** 当前回执（最后一次上报；null＝已清）。 */
  const receipt = () => receipts[receipts.length - 1] ?? null;
  /** 最后一次分派给 dock 的指令。 */
  const lastAsk = () => asks[asks.length - 1] ?? null;
  return { ref, receipt, lastAsk, ...utils };
}

describe("GenreSettingForm · 六格", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
  });

  it("渲染五格（编号 01-05 + 名称 + 怎么填 + 成书去处；06 剧情轨道已退役）", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    for (const name of [
      "题材",
      "主要看什么",
      "绝对禁止",
      "吃苦指数",
      "本小说斗什么",
    ]) {
      expect(screen.getByText(name)).toBeTruthy();
    }
    expect(screen.getByText("01")).toBeTruthy();
    expect(screen.queryByText("06")).toBeNull(); // 06 已退役
    expect(container.querySelectorAll(".m-use").length).toBe(5);
    expect(container.querySelectorAll(".m-why").length).toBe(5);
  });

  it("常见口味＝起点：点「逆袭打脸」只给 02 一句完整的话（2026-10-08 收窄：03/04/05 不联动），再点取消", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    const comeback = container.querySelector('[data-g="comeback"]')!;
    fireEvent.click(comeback);

    // 02 的主输入是作家要写的那句话（用户 2026-09-10：选项只是几个词）
    const note = (container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value;
    expect(note).toContain("读者要看到");
    expect(note).toContain("弱者");
    expect(container.textContent).toContain("标签：以弱破强的痛快"); // 短标签仍在（胶囊写入）
    // 03/04/05 不被预填（用户 2026-10-08：选题材和下面一堆要选要填的联动，不需要）
    expect(container.querySelector('[data-forbid="forbidden:no-deus-ex-machina"]')?.className)
      .not.toContain("on");
    expect(container.querySelector('[data-bf="battlefield:resources"]')?.className)
      .not.toContain("on");
    expect(container.querySelector('[data-od-id="cost-sentence"]')).toBeNull();
    expect(container.querySelector(".cost-val")!.textContent).toBe("—");
    // 选中的框可取消：再点一次＝还原（02 回到未填、高亮消失）
    expect(comeback.className).toContain("on");
    fireEvent.click(comeback);
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("");
    expect(comeback.className).not.toContain("on");
  });

  it("03 回车自定义禁区 → 生成可移除的自定义胶囊", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    const input = container.querySelector('[data-od-id="forbid-input"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "禁穿越" } });
    fireEvent.keyDown(input, { key: "Enter" });

    const chip = screen.getByText("禁穿越 ×");
    expect(chip).toBeTruthy();
    fireEvent.click(chip);
    expect(screen.queryByText("禁穿越 ×")).toBeNull();
  });

  it("04 未设置时不出浮例句；拖动后出「N 分 → …」", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    expect(container.querySelector('[data-od-id="cost-sentence"]')).toBeNull();
    fireEvent.change(container.querySelector('[data-od-id="cost-slider"]')!, {
      target: { value: "9" },
    });
    expect(screen.getByText("9 分 → 以命作祭，才封得住那扇门")).toBeTruthy();
  });

  it("05 战场第 3 个出软提示（不禁止）", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    expect(container.querySelector('[data-od-id="bf-note"]')).toBeNull();
    for (const id of ["resources", "status", "truth"]) {
      fireEvent.click(container.querySelector(`[data-bf="battlefield:${id}"]`)!);
    }
    expect(container.querySelector('[data-od-id="bf-note"]')).toBeTruthy();
  });

  it("05 回车自定义战场 → 可移除的自定义胶囊；与预设同名落预设勾选", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    const input = container.querySelector('[data-od-id="bf-input"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "抢天道机缘" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("抢天道机缘 ×")).toBeTruthy();

    // 与预设同名 → 只勾预设胶囊，不重复出自定义项
    fireEvent.change(input, { target: { value: "查真相" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(container.querySelector('[data-bf="battlefield:truth"]')?.className).toContain("on");
    expect(screen.queryByText("查真相 ×")).toBeNull();

    // 点 × 移除自定义项
    fireEvent.click(screen.getByText("抢天道机缘 ×"));
    expect(screen.queryByText("抢天道机缘 ×")).toBeNull();

    // 词汇引用样输入拒收（后端按前缀落 vocab 引用，手造 id＝保存 FK 违例 500）
    fireEvent.change(input, { target: { value: "battlefield:hack" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(toastState.info).toHaveBeenCalledWith("这是系统内部的词汇编号——请直接写中文战场词");
    expect(screen.queryByText("battlefield:hack ×")).toBeNull();
    expect(input.value).toBe("battlefield:hack"); // 拒收不清输入，留作者改
  });

  it("save 落五字段契约（含自定义项与空值形态）", async () => {
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.change(container.querySelector('[data-od-id="m1-input"]')!, {
      target: { value: "读者要看到弱者被逼到墙角后靠脑子翻盘" },
    });
    fireEvent.click(container.querySelector('[data-forbid="forbidden:no-villain-idiot"]')!);
    const input = container.querySelector('[data-od-id="forbid-input"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "禁穿越" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(container.querySelector('[data-od-id="cost-slider"]')!, {
      target: { value: "6" },
    });
    fireEvent.click(container.querySelector('[data-bf="battlefield:truth"]')!);
    const bfInput = container.querySelector('[data-od-id="bf-input"]') as HTMLInputElement;
    fireEvent.change(bfInput, { target: { value: "抢天道机缘" } });
    fireEvent.keyDown(bfInput, { key: "Enter" });

    await ref.current!.save();

    expect(apiState.put).toHaveBeenCalledWith("/novels/p1/settings/genre", {
      theme: "",
      sub_genre: "",
      core_promise: "",
      promise_note: "读者要看到弱者被逼到墙角后靠脑子翻盘",
      forbidden_list: [{ tagId: "forbidden:no-villain-idiot" }, { text: "禁穿越" }],
      cost_ratio: 6,
      battlefield: ["battlefield:truth", "抢天道机缘"],
    });
  });

  it("01 题材选择器：点大类只浏览不改值；选中走显式动作，× 清空", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    // 收起态＝一个字段（不再是一片胶囊墙）
    const trigger = container.querySelector('[data-od-id="theme-trigger"]')!;
    expect(trigger.textContent).toContain("选择题材");
    expect(container.querySelector('[data-od-id="theme-panel"]')).toBeNull();

    fireEvent.click(trigger);
    const panel = container.querySelector('[data-od-id="theme-panel"]')!;
    const themeRow = panel.querySelector('[data-od-id="theme-row"]')!;
    expect(themeRow.querySelectorAll(".sel-item")).toHaveLength(36);

    // 点左列大类＝**只浏览**：右列换成它的子类，字段值不动
    //（回归：原来点一下即选中 → 用户报「配置过的题材老是自动变成玄幻」）
    fireEvent.click(themeRow.querySelector('[data-g="theme:仙侠/修真"]')!);
    expect(trigger.textContent).toContain("选择题材");
    const subCol = container.querySelector('[data-od-id="sub-genre-row"]')!;
    expect(subCol.querySelectorAll(".sel-item")).toHaveLength(5); // 只归到大类 + 4 子类
    expect(subCol.textContent).toContain("凡人流");

    // 显式「只归到大类」＝选中大类并收起面板
    fireEvent.click(subCol.querySelector('[data-g="theme:仙侠/修真"]')!);
    expect(trigger.textContent).toContain("仙侠/修真");
    expect(trigger.textContent).not.toContain("凡人流");
    expect(container.querySelector('[data-od-id="theme-panel"]')).toBeNull();

    // 重新展开（浏览列定位到已选大类）→ 浏览另一个大类：字段仍不动（浏览不写值）
    fireEvent.click(trigger);
    const panel2 = container.querySelector('[data-od-id="theme-panel"]')!;
    fireEvent.click(
      panel2.querySelector('[data-od-id="theme-row"] [data-g="theme:科幻"]')!,
    );
    expect(trigger.textContent).toContain("仙侠/修真");
    expect(container.querySelector('[data-od-id="sub-genre-row"]')!.textContent).toContain(
      "星际",
    );

    // 点子类（先浏览回仙侠/修真）＝选「大类 + 子类」，面板收起
    fireEvent.click(
      container.querySelector('[data-od-id="theme-row"] [data-g="theme:仙侠/修真"]')!,
    );
    fireEvent.click(
      container.querySelector('[data-od-id="sub-genre-row"] [data-g="sub:凡人流"]')!,
    );
    expect(container.querySelector('[data-od-id="theme-panel"]')).toBeNull();
    expect(trigger.textContent).toContain("仙侠/修真 / 凡人流");

    // × 清空（TDesign clearable 同语义）
    fireEvent.click(container.querySelector('[data-od-id="theme-clear"]')!);
    expect(trigger.textContent).toContain("选择题材");
  });

  it("01 搜索：命中项拍平成「大类 / 子类」路径，点选即落", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    fireEvent.click(container.querySelector('[data-od-id="theme-trigger"]')!);

    const search = container.querySelector('[data-od-id="theme-search"]') as HTMLInputElement;
    // 按解读/案例也能搜到（81 个子类，光按名字搜不够用）
    fireEvent.change(search, { target: { value: "凡人修仙传" } });
    const results = container.querySelector('[data-od-id="theme-results"]')!;
    expect(results.textContent).toContain("仙侠/修真");
    expect(results.textContent).toContain("凡人流");

    fireEvent.click(results.querySelector('[data-g="sub:凡人流"]')!);
    expect(container.querySelector('[data-od-id="theme-trigger"]')!.textContent).toContain(
      "仙侠/修真 / 凡人流",
    );

    // 无命中 → 给一句可读的空态，不留白
    fireEvent.click(container.querySelector('[data-od-id="theme-trigger"]')!);
    fireEvent.change(container.querySelector('[data-od-id="theme-search"]')!, {
      target: { value: "不存在的东西" },
    });
    expect(container.querySelector('[data-od-id="theme-results"]')!.textContent).toContain(
      "没有匹配的题材",
    );
  });

  it("01 键盘：↑↓ 移动 + Enter 选中当前项 + Esc 收起", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    fireEvent.click(container.querySelector('[data-od-id="theme-trigger"]')!);

    const search = container.querySelector('[data-od-id="theme-search"]') as HTMLInputElement;
    fireEvent.change(search, { target: { value: "权谋" } });
    // 结果首项被高亮；Enter 直接落库
    expect(
      container.querySelector('[data-od-id="theme-results"] .sel-item.cur'),
    ).toBeTruthy();
    fireEvent.keyDown(search, { key: "Enter" });
    expect(container.querySelector('[data-od-id="theme-trigger"]')!.textContent).toContain(
      "权谋",
    );

    // Esc 收起面板
    fireEvent.click(container.querySelector('[data-od-id="theme-trigger"]')!);
    expect(container.querySelector('[data-od-id="theme-panel"]')).toBeTruthy();
    fireEvent.keyDown(container.querySelector('[data-od-id="theme-search"]')!, {
      key: "Escape",
    });
    expect(container.querySelector('[data-od-id="theme-panel"]')).toBeNull();
  });

  it("01 每项都有解读与案例：选中即显示（光有标签作者不知道指什么）", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    // 未选 → 不占位
    expect(container.querySelector('[data-od-id="theme-note"]')).toBeNull();

    // 只选大类 → 显示大类解读（无案例）
    fireEvent.click(container.querySelector('[data-od-id="theme-trigger"]')!);
    const themeRow = container.querySelector('[data-od-id="theme-row"]')!;
    expect(themeRow.querySelector('[data-g="theme:仙侠/修真"]')!.getAttribute("title")).toContain(
      "修行阶次",
    );
    // 左列点大类只浏览 → 解读区不动；显式「只归到大类」才选中并出解读
    fireEvent.click(themeRow.querySelector('[data-g="theme:仙侠/修真"]')!);
    expect(container.querySelector('[data-od-id="theme-note"]')).toBeNull();
    fireEvent.click(
      container.querySelector('[data-od-id="sub-genre-row"] [data-g="theme:仙侠/修真"]')!,
    );
    const note = container.querySelector('[data-od-id="theme-note"]')!;
    expect(note.textContent).toContain("修行阶次");
    expect(note.querySelector(".eg")).toBeNull();

    // 子类项自带悬停解读 + 案例（重新展开后仍能看到已选大类的子类）
    fireEvent.click(container.querySelector('[data-od-id="theme-trigger"]')!);
    const firstSub = container.querySelector('[data-g="sub:凡人流"]')!;
    expect(firstSub.getAttribute("title")).toContain("资质平平");
    expect(firstSub.getAttribute("title")).toContain("案例：《凡人修仙传》");

    // 选子类 → 解读区换成子类解读 + 案例
    fireEvent.click(firstSub);
    const subNote = container.querySelector('[data-od-id="theme-note"]')!;
    expect(subNote.textContent).toContain("凡人流");
    expect(subNote.textContent).toContain("资质平平");
    expect(subNote.textContent).toContain("案例：《凡人修仙传》");
  });

  it("01 题材目录随契约下发回读（theme + sub_genre）", async () => {
    const { ref, container } = renderPanel({ theme: "架空古王朝", sub_genre: "权谋" });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    expect(container.querySelector('[data-od-id="theme-trigger"]')!.textContent).toContain(
      "架空古王朝 / 权谋",
    );
    expect(container.querySelector('[data-od-id="theme-note"]')!.textContent).toContain(
      "以谋局与反制推进",
    );

    await ref.current!.save();
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/settings/genre",
      expect.objectContaining({ theme: "架空古王朝", sub_genre: "权谋" }),
    );
  });

  it("回读：已有契约渲染到对应控件（含未知战场项原样展示）", async () => {
    const { container } = renderPanel({
      core_promise: "算无遗策的掌控感",
      promise_note: "读者要看布局收网",
      forbidden_list: [{ tagId: "forbidden:no-foresight" }],
      cost_ratio: 4,
      battlefield: ["battlefield:status", "街口那条巷子"],
    });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("读者要看布局收网");
    expect(screen.getByText(/标签：算无遗策的掌控感/)).toBeTruthy();
    expect(container.querySelector('[data-forbid="forbidden:no-foresight"]')?.className)
      .toContain("on");
    expect(screen.getByText("4 分 → 当众断骨毁名，才拿到入场券")).toBeTruthy();
    expect(container.querySelector('[data-bf="battlefield:status"]')?.className).toContain("on");
    expect(screen.getByText("街口那条巷子 ×")).toBeTruthy();
  });
});

// ── 五行 AI（tasks 4.2 / c-settings-ai-confirm-modal）：结果统一进弹窗出卡，
//    采纳才写回；关闭即弃；缓存重开免请求（D9）；「换一个」version+1 ──────────
describe("GenreSettingForm · 全书默认节奏块（c-volume-pacing）", () => {
  const PRESETS = [
    { key: "upgrade", label: "升级套路", sub: "遇麻烦 → 解决 → 变强", steps_len: 3,
      warn_len: 6, hint: "", steps: [], ch1_extra: "" },
    { key: "case", label: "破案套路", sub: "案发 → 查案 → 反转", steps_len: 12,
      warn_len: 16, hint: "", steps: [], ch1_extra: "" },
  ];

  it("无书默认时默认段长取所建议套路的真实值（悬疑→破案 12 章，非恒 3）", async () => {
    // 内联渲染（renderPanel 会重设 get 的实现，保住 /pacing/presets 路由桩）
    apiState.get.mockImplementation((path: string) => {
      if (path === "/genres/candidates") return Promise.resolve({});
      if (path.endsWith("/pacing/presets")) {
        return Promise.resolve({
          presets: PRESETS, default_key: "upgrade", book_default: null,
          suggested_key: "case", theme: "悬疑", sub_genre: "",
        });
      }
      return Promise.resolve({
        theme: "悬疑", sub_genre: "", promise_note: "", core_promise: "",
        forbidden_list: [], battlefield: [],
      });
    });
    render(
      <GenreSettingForm ref={createRef<GenreHandle>()} projectId="p1" settingKey="genre" />,
    );
    await waitFor(() => {
      const input = screen.getByLabelText("一段剧情讲几章") as HTMLInputElement;
      expect(input.value).toBe("12");
    });
    expect((screen.getByLabelText("剧情套路") as HTMLSelectElement).value).toBe("case");
  });
});

describe("GenreSettingForm · 五行 AI（收编：让助手办）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    aiState.genreAi.mockReset();
  });

  it("四格 runAi 分派 dock 指令（单一文案源=chips 表），不再出弹窗", async () => {
    const { ref, lastAsk, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    await act(async () => ref.current!.runAi("core_promise"));
    expect(lastAsk()).toBe("给我几个「主要看什么」的核心看点候选。");
    await act(async () => ref.current!.runAi("forbidden_list"));
    expect(lastAsk()).toBe("这本书绝不出现什么？给我红线清单候选。");
    await act(async () => ref.current!.runAi("cost_ratio"));
    expect(lastAsk()).toBe("主角得到好处要付多大代价？给吃苦指数建议。");
    await act(async () => ref.current!.runAi("battlefield"));
    expect(lastAsk()).toBe("全书主要斗的是什么？给对抗物候选。");
    // 旧弹窗路径退役：不出确认卡、不直调生成核
    expect(screen.queryByTestId("genre-ai-card")).toBeNull();
    expect(aiState.genreAi).not.toHaveBeenCalled();
  });

  it("未知 key 不分派（守卫）", async () => {
    const { ref, lastAsk, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    await act(async () => (ref.current as unknown as { runAi: (f: string) => Promise<void> }).runAi("nope"));
    expect(lastAsk()).toBeNull();
    expect(container.querySelectorAll(".mod")).toHaveLength(5);
  });
});

// ── 改动回执 + 单步撤销（用户 2026-09-10 拍板：一键改变内容类动作必须可回退）──
describe("GenreSettingForm · 改动回执 + 撤销", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
  });

  it("口味胶囊＝覆盖起点句（非作者内容）→ 回执含起点全句，撤销回到改前（04 不被动）", async () => {
    const { ref, receipt, container } = renderPanel({
      core_promise: "层层反转的智力快感",
      promise_note: MIND_NOTE, // 已是另一颗的起点原句（重载态，高亮已丢）→ 可被替换
      cost_ratio: 5,
    });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.click(container.querySelector('[data-g="comeback"]')!);
    expect(receipt()?.text).toContain("已按「逆袭打脸」给出「主要看什么」一句起点");
    expect(receipt()?.text).toContain("弱者用脑子换来的痛快"); // 起点全句入回执（最长回执载体）
    expect(receipt()?.text).not.toContain("吃苦指数");

    receipt()!.undo();
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toBe(MIND_NOTE),
    );
    expect(container.querySelector(".cost-val")!.textContent).toBe("5");
    // 撤销后高亮跟着回：点选前的态＝未选中
    expect(container.querySelector('[data-g="comeback"]')?.className).not.toContain("on");
  });

  it("作者已写的内容：点胶囊不覆盖、不高亮、出提示", async () => {
    const { receipt, container } = renderPanel({ promise_note: "作者手写的那句话" });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.click(container.querySelector('[data-g="comeback"]')!);
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("作者手写的那句话");
    expect(container.querySelector('[data-g="comeback"]')?.className).not.toContain("on");
    expect(toastState.info).toHaveBeenCalledWith(expect.stringContaining("起点没有动它"));
    expect(receipt()).toBeNull(); // 拒绝动作不记回执
  });

  it("起点再点一次取消：未改过 → 还原点前值＋回执可撤销（撤销＝重新写回起点）", async () => {
    const { receipt, container } = renderPanel({ promise_note: MIND_NOTE });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    const comeback = container.querySelector('[data-g="comeback"]')!;
    fireEvent.click(comeback);
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toContain("弱者用脑子换来的痛快");

    fireEvent.click(comeback); // 再点＝取消
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toBe(MIND_NOTE),
    );
    expect(comeback.className).not.toContain("on");
    expect(receipt()?.text).toContain("已取消「逆袭打脸」起点");

    receipt()!.undo(); // 撤销取消＝重新写回该起点
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toContain("弱者用脑子换来的痛快"),
    );
    expect(comeback.className).toContain("on");
  });

  it("起点被作者改过后取消：只清高亮、字不动、不新增回执", async () => {
    const { receipt, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    const comeback = container.querySelector('[data-g="comeback"]')!;
    fireEvent.click(comeback);
    fireEvent.change(container.querySelector('[data-od-id="m1-input"]')!, {
      target: { value: "作者改过的话" },
    });

    fireEvent.click(comeback);
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("作者改过的话");
    expect(comeback.className).not.toContain("on");
    // 无数据变更 → 不新增回执（最后一条仍是点选时的那条）
    expect(receipt()?.text).toContain("一句起点");
    expect(receipt()?.text).not.toContain("已取消");
  });

  it("取消→撤销→再取消：每次取消都还原点前值（ref 随 undo 闭包恢复）", async () => {
    const { receipt, container } = renderPanel({ promise_note: MIND_NOTE });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    const comeback = container.querySelector('[data-g="comeback"]')!;
    fireEvent.click(comeback); // 应用 A
    fireEvent.click(comeback); // 取消 → 还原为 mind 起点句
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toBe(MIND_NOTE),
    );

    receipt()!.undo(); // 撤销取消 → A 起点句＋高亮回来
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toContain("弱者用脑子换来的痛快"),
    );

    fireEvent.click(comeback); // 再取消 → 仍须还原为 mind 起点句（回归：ref 未随 undo 恢复时只清高亮、A 句残留）
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toBe(MIND_NOTE),
    );
    expect(comeback.className).not.toContain("on");
    expect(receipt()?.text).toContain("已取消「逆袭打脸」起点");
  });

  it("切换口味：新起点覆盖 02；撤销回到上一颗的句子且高亮回上一颗", async () => {
    const { receipt, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.click(container.querySelector('[data-g="comeback"]')!);
    fireEvent.click(container.querySelector('[data-g="mind"]')!);
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toContain("信息差布局收网");
    expect(container.querySelector('[data-g="mind"]')?.className).toContain("on");
    expect(receipt()?.text).toContain("已按「烧脑博弈」给出「主要看什么」一句起点");

    receipt()!.undo();
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toContain("弱者用脑子换来的痛快"),
    );
    expect(container.querySelector('[data-g="comeback"]')?.className).toContain("on");
    expect(container.querySelector('[data-g="mind"]')?.className).not.toContain("on");
  });

  it("禁项胶囊：勾选与取消都留回执，撤销可来回", async () => {
    const { receipt, container } = renderPanel({ forbidden_list: [{ tagId: "forbidden:no-free-powerup" }] });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.click(container.querySelector('[data-forbid="forbidden:no-villain-idiot"]')!);
    expect(receipt()?.text).toBe("已勾选「禁反派降智」");
    receipt()!.undo();
    await waitFor(() =>
      expect(container.querySelector('[data-forbid="forbidden:no-villain-idiot"]')!.className)
        .not.toContain("on"),
    );

    fireEvent.click(container.querySelector('[data-forbid="forbidden:no-free-powerup"]')!);
    expect(receipt()?.text).toBe("已取消「禁白捡神器」");
    receipt()!.undo();
    await waitFor(() =>
      expect(container.querySelector('[data-forbid="forbidden:no-free-powerup"]')!.className)
        .toContain("on"),
    );
  });

  it("滑块：拖动中不出回执，松手出一次；撤销回到拖动前", async () => {
    const { receipt, container } = renderPanel({ cost_ratio: 6 });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    const slider = container.querySelector('[data-od-id="cost-slider"]') as HTMLInputElement;

    fireEvent.pointerDown(slider);
    fireEvent.change(slider, { target: { value: "9" } });
    expect(receipt()).toBeNull(); // 拖动中不刷回执

    fireEvent.pointerUp(slider);
    expect(receipt()?.text).toBe("已把吃苦指数从 6 调到 9");

    receipt()!.undo();
    await waitFor(() => expect((container.querySelector('[data-od-id="cost-slider"]') as HTMLInputElement).value).toBe("6"));
  });

  it("02 文本：敲字只在失焦后给「恢复到打开时的原文」，过程中不提示", async () => {
    const { receipt, container } = renderPanel({ promise_note: "读者要看弱者翻盘" });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    const box = container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement;

    fireEvent.change(box, { target: { value: "读者要看弱者靠算计翻盘" } });
    expect(container.querySelector('[data-od-id="field-restore"]')).toBeNull(); // 打字中不提示
    expect(receipt()).toBeNull(); // 也不进脚部回执

    fireEvent.blur(box);
    expect(container.querySelector('[data-od-id="field-restore"]')).toBeTruthy();
    fireEvent.click(container.querySelector('[data-od-id="field-restore-btn"]')!);
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("读者要看弱者翻盘");
    expect(container.querySelector('[data-od-id="field-restore"]')).toBeNull();
  });

  it("撤销按差量：勾选后自己加的自定义禁区不被撤销带走", async () => {
    const { receipt, container } = renderPanel({});
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.click(container.querySelector('[data-forbid="forbidden:no-villain-idiot"]')!);
    const input = container.querySelector('[data-od-id="forbid-input"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "禁穿越" } });
    fireEvent.keyDown(input, { key: "Enter" });

    receipt()!.undo();
    await waitFor(() =>
      expect(container.querySelector('[data-forbid="forbidden:no-villain-idiot"]')!.className)
        .not.toContain("on"),
    );
    // 「禁穿越」是勾选之后作家自己敲的，不属于这次改动 → 保留
    expect(container.textContent).toContain("禁穿越");
  });

  it("滑块：未设 → N 也出回执（首次使用同样可撤销）", async () => {
    const { receipt, container } = renderPanel({ cost_ratio: null });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    const slider = container.querySelector('[data-od-id="cost-slider"]') as HTMLInputElement;

    fireEvent.pointerDown(slider);
    fireEvent.change(slider, { target: { value: "7" } });
    fireEvent.pointerUp(slider);
    expect(receipt()?.text).toBe("已把吃苦指数从未设调到 7");

    receipt()!.undo();
    await waitFor(() =>
      expect(container.querySelector(".cost-val")!.textContent).toBe("—"),
    );
  });

  it("滑块：一次拖动里来回一圈回到原值 → 不算改动，连上一条回执一起清掉", async () => {
    const { receipt, container } = renderPanel({ cost_ratio: 6 });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    const slider = container.querySelector('[data-od-id="cost-slider"]') as HTMLInputElement;

    // 垫一条回执（用 03 勾选，免得动了 04 的值把「原值」挪走）
    fireEvent.click(container.querySelector('[data-forbid="forbidden:no-villain-idiot"]')!);
    expect(receipt()).not.toBeNull();

    fireEvent.pointerDown(slider);
    fireEvent.change(slider, { target: { value: "9" } });
    fireEvent.change(slider, { target: { value: "6" } });
    fireEvent.pointerUp(slider);
    expect(receipt()).toBeNull();
  });

});
