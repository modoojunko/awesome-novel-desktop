import { beforeEach, describe, expect, it, vi } from "vitest";
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import GenreSettingForm, {
  type GenreHandle,
} from "@/components/novel/settings/GenreSettingForm";

// 题材六格面板（genre-signup-redesign tasks 4.1 / D18 新契约）
const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState, request: vi.fn() }));

const aiState = vi.hoisted(() => ({ genreAi: vi.fn() }));

vi.mock("@/lib/ai", () => ({
  genreAi: aiState.genreAi,
  aiBlockReason: (e: { reason?: string }) => e?.reason ?? null,
}));

function renderPanel(initial: unknown = {}) {
  apiState.get.mockImplementation((path: string) => {
    if (path === "/genres/candidates") return Promise.resolve({});
    return Promise.resolve(initial);
  });
  const ref = createRef<GenreHandle>();
  const receipts: Array<{ text: string; undo: () => void } | null> = [];
  const utils = render(
    <GenreSettingForm
      ref={ref}
      projectId="p1"
      settingKey="genre"
      onReceiptChange={(r) => receipts.push(r)}
    />,
  );
  /** 当前回执（最后一次上报；null＝已清）。 */
  const receipt = () => receipts[receipts.length - 1] ?? null;
  return { ref, receipt, ...utils };
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

  it("常见口味＝起点：点「逆袭打脸」预填一句完整的话（+03/04/05），不落 track", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.click(container.querySelector('[data-g="comeback"]')!);

    // 02 的主输入是作家要写的那句话（用户 2026-09-10：选项只是几个词）
    const note = (container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value;
    expect(note).toContain("读者要看到");
    expect(note).toContain("弱者");
    expect(container.textContent).toContain("标签：以弱破强的痛快"); // 短标签仍在（胶囊写入）
    expect(container.querySelector('[data-forbid="forbidden:no-deus-ex-machina"]')?.className)
      .toContain("on");
    expect(container.querySelector('[data-bf="battlefield:resources"]')?.className).toContain("on");
    expect(container.querySelector('[data-od-id="cost-slider"]')).toBeTruthy();
    expect(screen.getByText("8")).toBeTruthy();
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

    await ref.current!.save();

    expect(apiState.put).toHaveBeenCalledWith("/novels/p1/settings/genre", {
      theme: "",
      sub_genre: "",
      core_promise: "",
      promise_note: "读者要看到弱者被逼到墙角后靠脑子翻盘",
      forbidden_list: [{ tagId: "forbidden:no-villain-idiot" }, { text: "禁穿越" }],
      cost_ratio: 6,
      battlefield: ["battlefield:truth"],
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
    expect(themeRow.querySelectorAll(".sel-item")).toHaveLength(21);

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

// ── 五行 AI（tasks 4.2）：反馈落各格下方，采纳才写回 ──────────────────────
describe("GenreSettingForm · 五行 AI", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
    aiState.genreAi.mockReset();
  });

  it("core_promise：sink 落在 02 格下方，采纳写回 value + note", async () => {
    aiState.genreAi.mockResolvedValue({
      value: { value: "以弱破强的痛快", note: "读者要看到弱者翻盘" },
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    await act(async () => ref.current!.runAi("core_promise"));

    const sink = container.querySelector('[data-od-id="genre-ai-sink-core_promise"]');
    expect(sink).toBeTruthy();
    expect(screen.getByText("AI 填 · 主要看什么")).toBeTruthy();
    expect(aiState.genreAi).toHaveBeenCalledWith(
      "core_promise",
      expect.objectContaining({ title: "" }),
      "p1",
    );

    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("读者要看到弱者翻盘");
    expect(container.textContent).toContain("标签：以弱破强的痛快");
  });

  it("02 多看点：勾选式采纳（单选＝标签+句子；多选＝只拼句子）", async () => {
    aiState.genreAi.mockResolvedValue({
      value: [
        { value: "以弱破强的痛快", note: "读者要看到弱者用脑子翻盘" },
        { value: "绝处逢生的紧张", note: "读者想看一次次死里逃生" },
      ],
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    // 右栏「多给几个看点」→ runAi(field, {multi:true}) → 结果区多条
    await act(async () => {
      await ref.current!.runAi("core_promise", { multi: true });
    });
    const multi = container.querySelector('[data-od-id="multi-points"]')!;
    expect(multi.querySelectorAll('[data-od-id^="multi-pick-"]')).toHaveLength(2);

    // 单选第二条 → 标签＝该条 value、主框＝该条 note
    fireEvent.click(multi.querySelector('[data-od-id="multi-pick-1"]')!);
    fireEvent.click(screen.getByRole("button", { name: "采纳勾选的这条" }));
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("读者想看一次次死里逃生");
    expect(container.textContent).toContain("标签：绝处逢生的紧张");
  });

  it("02 多看点：多选＝拼句子且不设单一标签（作家也可一条不勾自己写）", async () => {
    aiState.genreAi.mockResolvedValue({
      value: [
        { value: "以弱破强的痛快", note: "读者要看到弱者用脑子翻盘" },
        { value: "绝处逢生的紧张", note: "读者想看一次次死里逃生" },
      ],
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    await act(async () => {
      await ref.current!.runAi("core_promise", { multi: true });
    });

    const multi = container.querySelector('[data-od-id="multi-points"]')!;
    fireEvent.click(multi.querySelector('[data-od-id="multi-pick-0"]')!);
    fireEvent.click(multi.querySelector('[data-od-id="multi-pick-1"]')!);
    // 按钮文案随勾选数变化 → 明确"这一次会落几条"
    fireEvent.click(screen.getByRole("button", { name: "采纳勾选的 2 条" }));

    const box = container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement;
    expect(box.value).toBe("读者要看到弱者用脑子翻盘；读者想看一次次死里逃生");
    // 单一标签表达不了多个看点 → 多选时不写标签（作者想留标签就只勾一条）
    expect(container.textContent).not.toContain("标签：以弱破强的痛快");
  });

  it("cost_ratio：采纳后滑块与浮例句同步", async () => {
    aiState.genreAi.mockResolvedValue({ value: 9 });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    await act(async () => ref.current!.runAi("cost_ratio"));
    expect(screen.getByText(/建议 9 分/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));
    expect(screen.getByText("9 分 → 以命作祭，才封得住那扇门")).toBeTruthy();
  });

  it("03 绝对禁止：tagId 显示中文标签，绝不把英文 slug 甩给作者", async () => {
    // 用户 2026-09-10 反馈「AI 建议给出来的是英文」——AI 返回的是 tagId（正确），
    // 03 结果区漏了 tagId→label 映射（05 有），原样打出 forbidden:no-free-powerup。
    aiState.genreAi.mockResolvedValue({
      value: [
        { tagId: "forbidden:no-free-powerup" },
        { tagId: "forbidden:no-villain-idiot" },
        { text: "禁主角靠灵根觉醒翻盘" },
      ],
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    await act(async () => {
      await ref.current!.runAi("forbidden_list");
    });
    const sink = container.querySelector('[data-od-id="genre-ai-sink-forbidden_list"]')!;
    expect(sink.textContent).toContain("禁白捡神器");
    expect(sink.textContent).toContain("禁反派降智");
    expect(sink.textContent).toContain("禁主角靠灵根觉醒翻盘"); // 自定义中文原样
    expect(sink.textContent).not.toContain("forbidden:"); // 英文 slug 一个都不许露

    // 采纳仍落 tagId（存储契约不变），界面胶囊显示中文
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));
    expect(container.querySelector('[data-forbid="forbidden:no-free-powerup"]')).toBeTruthy();
    expect(container.textContent).toContain("禁白捡神器");
  });

  it("03 近似容错：模型写岔的 id（少写/多写一个词）也显示中文", async () => {
    // 实测坑：模型把 forbidden:no-deus-ex-machina 写成 forbidden:no-deus-machina，
    // 后端曾把它当「自定义文本」存下来 → 界面显示英文 slug（用户 2026-09-10 反馈）。
    aiState.genreAi.mockResolvedValue({
      value: [
        { tagId: "forbidden:no-deus-machina" }, // 少写 ex
        { tagId: "forbidden:no-villain-idiot" },
      ],
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));
    await act(async () => {
      await ref.current!.runAi("forbidden_list");
    });
    const sink = container.querySelector('[data-od-id="genre-ai-sink-forbidden_list"]')!;
    expect(sink.textContent).toContain("禁天降外援");
    expect(sink.textContent).not.toContain("forbidden:");
  });

  it("battlefield：候选 tagId 采纳后落成已选胶囊", async () => {
    aiState.genreAi.mockResolvedValue({
      value: [{ tagId: "battlefield:resources" }, { text: "街口那条巷子" }],
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    await act(async () => ref.current!.runAi("battlefield"));
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));

    expect(container.querySelector('[data-bf="battlefield:resources"]')?.className).toContain("on");
    expect(screen.getByText("街口那条巷子 ×")).toBeTruthy();
  });


  it("失败不落 sink（按 reason 分派提示）", async () => {
    aiState.genreAi.mockRejectedValue({ reason: "missing_model" });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    await act(async () => ref.current!.runAi("battlefield"));
    expect(container.querySelector('[data-od-id="genre-ai-sink-battlefield"]')).toBeNull();
  });
});

// 题材四行：最近 5 次历史 + 切回旧版采纳覆盖本格
describe("GenreSettingForm · 生成历史（最近 5 次）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
    aiState.genreAi.mockReset();
  });

  it("连生成 6 次只保留最近 5 次；切回旧版采纳覆盖本格", async () => {
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    for (let i = 1; i <= 6; i++) {
      aiState.genreAi.mockResolvedValueOnce({ value: [{ text: `第${i}版战场` }] });
      await act(async () => ref.current!.runAi("battlefield"));
      await waitFor(() => expect(container.textContent).toContain(`第${i}版战场`));
    }
    const chips = [...container.querySelectorAll('[data-od-id="ai-sink-history"] [data-hist]')];
    expect(chips).toHaveLength(5); // 丢最旧
    expect(container.textContent).toContain("只保留最近 5 次");

    // 切回第 1 条（＝第 2 次生成）并采纳 → 覆盖 05 战场胶囊
    fireEvent.click(chips[0]);
    expect(container.textContent).toContain("第2版战场");
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));
    expect(container.textContent).toContain("第2版战场");
  });
});

// ── 改动回执 + 单步撤销（用户 2026-09-10 拍板：一键改变内容类动作必须可回退）──
describe("GenreSettingForm · 改动回执 + 撤销", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
  });

  it("口味胶囊＝一次覆盖多格 → 回执写明覆盖范围，撤销回到改前", async () => {
    const { ref, receipt, container } = renderPanel({
      core_promise: "算无遗策的掌控感",
      promise_note: "读者要看布局收网",
      cost_ratio: 5,
    });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    fireEvent.click(container.querySelector('[data-g="comeback"]')!);
    expect(receipt()?.text).toContain("已按「逆袭打脸」覆盖");
    expect(receipt()?.text).toContain("吃苦指数 5→8");

    receipt()!.undo();
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toBe("读者要看布局收网"),
    );
    expect(container.querySelector(".cost-val")!.textContent).toBe("5");
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

  it("AI 采纳覆盖这段 → 回执报字数，撤销写回改前两个字", async () => {
    aiState.genreAi.mockResolvedValue({
      value: { value: "以弱破强的痛快", note: "读者要看到弱者用脑子翻盘" },
    });
    const { ref, receipt, container } = renderPanel({ promise_note: "旧的一句" });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(5));

    await act(async () => ref.current!.runAi("core_promise"));
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));

    expect(receipt()?.text).toContain("已采纳 AI 建议，覆盖「主要看什么」");
    expect(receipt()?.text).toContain("4 字 → 12 字");
    receipt()!.undo();
    await waitFor(() =>
      expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
        .toBe("旧的一句"),
    );
    expect(container.textContent).not.toContain("标签：以弱破强的痛快");
  });
});
