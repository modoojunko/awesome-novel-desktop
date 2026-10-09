// 出场角色胶囊身份标＋悬停身份卡（c-og-cast-role-hover）：两态同貌身份标（主角/配角/
// 反派/路人）／别名按卡标身份且卡显正名／没卡名无标无卡／悬停卡内容（人设＋已填档案
// ＋首次出场，空格不出行）／castInfos 缺失退化纯名字。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM, type OgForm } from "@/components/novel/workbench/chapterForm";
import { CastHover, type CastInfo } from "@/components/novel/workbench/CastHover";

const FORM: OgForm = {
  ...EMPTY_OG_FORM,
  summary: "林野夜巡",
  chars: "林野\n秦伯\n小野",
  plots: ["巷口又见袭击"],
};

const LINYE: CastInfo = {
  name: "林野",
  role: "主角",
  aliases: ["小野"],
  persona: "杂役弟子，捡到父亲留下的残页。",
  dossier: {
    gender: "男",
    age: "17",
    race: "人族",
    faction: "青云门 · 杂役",
    look: "",
    speech: "",
    background: "",
    plot: "主线推动者",
  },
  firstChapter: 1,
};

const QINBO: CastInfo = {
  name: "秦伯",
  role: "反派",
  aliases: [],
  persona: "",
  dossier: {},
  firstChapter: null,
};

const INFOS: Record<string, CastInfo> = {
  林野: LINYE,
  小野: LINYE,
  秦伯: QINBO,
};

function renderPane(editing: boolean, castInfos?: Record<string, CastInfo>) {
  return render(
    <OgPane
      form={FORM}
      characterNames={["林野", "小野"]}
      castInfos={castInfos}
      label="第02章 · 夜巡"
      editing={editing}
      loading={false}
      onPatch={vi.fn()}
      gaps={[]}
      confirmed={false}
      saving={false}
      onStartEdit={vi.fn()}
      onCancelEdit={vi.fn()}
      onGapClick={vi.fn()}
      onSaveDraft={vi.fn()}
      onConfirm={vi.fn()}
      onGoWrite={vi.fn()}
    />,
  );
}

/** 「林野」胶囊的悬停宿主（有卡名＝.cast-wrap 包裹层） */
function chipWrap(name: string): HTMLElement {
  const view = screen.getByTestId("og-cast-view");
  const chip = [...view.querySelectorAll<HTMLElement>(".chip")].find((c) =>
    c.textContent?.startsWith(name),
  );
  expect(chip, `找不到「${name}」胶囊`).toBeTruthy();
  return chip!.closest<HTMLElement>(".cast-wrap") ?? chip!;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  act(() => vi.runOnlyPendingTimers());
  vi.useRealTimers();
});

describe("章纲出场角色胶囊：身份标与悬停身份卡（c-og-cast-role-hover）", () => {
  it("查看态：有卡名带身份小标（别名归卡同标），没卡名无标", () => {
    renderPane(false, INFOS);
    const view = screen.getByTestId("og-cast-view");
    const chip = (n: string) =>
      [...view.querySelectorAll(".chip")].find((c) => c.textContent?.startsWith(n))!;
    // 林野＝主角；小野（别名）归同一张卡，同标主角
    expect(chip("林野")!.querySelector(".cast-role")!.textContent).toBe("主角");
    expect(chip("小野")!.querySelector(".cast-role")!.textContent).toBe("主角");
    // 秦伯……有卡！反派标在场（此名在本用例给卡）
    expect(chip("秦伯")!.querySelector(".cast-role")!.textContent).toBe("反派");
  });

  it("悬停身份卡：正名＋人设全文＋已填档案行＋首次出场，空格不出行", () => {
    renderPane(false, INFOS);
    // React 的 onMouseEnter 由 mouseover 合成——fireEvent.mouseOver 才能触发
    fireEvent.mouseOver(chipWrap("林野"));
    expect(screen.queryByTestId("cast-hover-林野")).toBeNull(); // 150ms 开启延迟内不出卡
    act(() => vi.advanceTimersByTime(150));
    const card = screen.getByTestId("cast-hover-林野");
    expect(card.textContent).toContain("一句话人设");
    expect(card.textContent).toContain("杂役弟子，捡到父亲留下的残页。");
    expect(card.textContent).toContain("别名：小野");
    expect(card.textContent).toContain("性别 · 年龄 · 种族");
    expect(card.textContent).toContain("男 · 17 · 人族");
    expect(card.textContent).toContain("剧情定位");
    expect(card.textContent).not.toContain("外貌标签"); // 空格不出行
    expect(card.textContent).not.toContain("背景");
    expect(card.textContent).toContain("第 01 章首次出场");
    // 移出（过宽限期）即收
    fireEvent.mouseOut(chipWrap("林野"));
    act(() => vi.advanceTimersByTime(150));
    expect(screen.queryByTestId("cast-hover-林野")).toBeNull();
  });

  it("没卡名不出标不出卡；castInfos 缺失退化纯名字", () => {
    // 只有林野有卡：秦伯无卡 → 无标、悬停不出卡
    const first = renderPane(false, { 林野: LINYE });
    const view = first.getByTestId("og-cast-view");
    const qin = [...view.querySelectorAll(".chip")].find((c) =>
      c.textContent?.startsWith("秦伯"),
    )!;
    expect(qin.querySelector(".cast-role")).toBeNull();
    expect(qin.querySelector(".no-card")!.textContent).toBe("没卡");
    fireEvent.mouseOver(qin.closest(".cast-wrap") ?? qin);
    act(() => vi.advanceTimersByTime(300));
    expect(screen.queryByTestId("cast-hover-秦伯")).toBeNull();
    first.unmount();

    // 完全没给 castInfos：全部纯名字胶囊
    renderPane(false);
    expect(document.querySelectorAll('[data-testid="og-cast-view"]')).toHaveLength(1);
    expect(
      document.querySelector('[data-testid="og-cast-view"]')!.querySelectorAll(".cast-role"),
    ).toHaveLength(0);
  });

  it("编辑态同貌：候选胶囊带身份标，聚焦（键盘）出卡且正名位显卡上正名", () => {
    renderPane(true, INFOS);
    const picker = screen.getByRole("group", { name: "从角色卡选择出场角色" });
    const chip = (n: string) =>
      [...picker.querySelectorAll("button.chip")].find((c) => c.textContent?.startsWith(n))!;
    expect(chip("林野")!.querySelector(".cast-role")!.textContent).toBe("主角");
    expect(chip("小野")!.querySelector(".cast-role")!.textContent).toBe("主角");
    // 键盘聚焦即出卡（无延迟），别名胶囊的卡显正名「林野」＋别名行
    fireEvent.focus(chip("小野")!.closest(".cast-wrap")!);
    const card = screen.getByTestId("cast-hover-林野");
    expect(card.querySelector(".chc-name")!.textContent).toContain("林野");
    expect(card.querySelector(".chc-alias")!.textContent).toContain("小野");
    fireEvent.blur(chip("小野")!.closest(".cast-wrap")!);
    expect(screen.queryByTestId("cast-hover-林野")).toBeNull();
  });

  it("空人设/未出场/无别名：对应行不出", () => {
    renderPane(false, INFOS); // 秦伯卡：空人设、无别名、未出场
    fireEvent.mouseOver(chipWrap("秦伯"));
    act(() => vi.advanceTimersByTime(150));
    const card = screen.getByTestId("cast-hover-秦伯");
    expect(card.textContent).not.toContain("一句话人设");
    expect(card.textContent).not.toContain("别名：");
    expect(card.textContent).not.toContain("首次出场");
    fireEvent.mouseOut(chipWrap("秦伯"));
    act(() => vi.advanceTimersByTime(150));
  });

  it("开关时序：开延迟内移出取消／开着再入短路／卡内悬停不收／Esc 收／卸载后定时器不炸", () => {
    const { unmount } = renderPane(false, INFOS);
    const wrap = chipWrap("林野");
    // 开延迟内移出：取消开启
    fireEvent.mouseOver(wrap);
    fireEvent.mouseOut(wrap);
    act(() => vi.advanceTimersByTime(300));
    expect(screen.queryByTestId("cast-hover-林野")).toBeNull();
    // 正常开启；开着再入（open 短路）不重复排程
    fireEvent.mouseOver(wrap);
    act(() => vi.advanceTimersByTime(150));
    const card = screen.getByTestId("cast-hover-林野");
    fireEvent.mouseOver(wrap);
    // 移出胶囊但宽限期内移入卡：不收；再移出卡：过宽限期收
    fireEvent.mouseOut(wrap);
    fireEvent.mouseOver(card);
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getByTestId("cast-hover-林野")).toBeTruthy();
    fireEvent.mouseOut(card);
    act(() => vi.advanceTimersByTime(150));
    expect(screen.queryByTestId("cast-hover-林野")).toBeNull();
    // 开着按 Esc：即收
    fireEvent.mouseOver(wrap);
    act(() => vi.advanceTimersByTime(150));
    // 滚动重锚（开着时随 scroll/resize 重锚，卡不丢）
    fireEvent.scroll(window);
    expect(screen.getByTestId("cast-hover-林野")).toBeTruthy();
    // 非 Esc 按键不收卡；Esc 即收
    fireEvent.keyDown(wrap, { key: "Enter" });
    expect(screen.getByTestId("cast-hover-林野")).toBeTruthy();
    fireEvent.keyDown(wrap, { key: "Escape" });
    expect(screen.queryByTestId("cast-hover-林野")).toBeNull();
    // 卸载后残留开启定时器触发：anchor 的 !el 守卫兜底，不炸
    fireEvent.mouseOver(wrap);
    unmount();
    expect(() => act(() => vi.advanceTimersByTime(300))).not.toThrow();
  });

  it("下方放不下翻转向上：bottom 锚定（zoom 折算口径）", () => {
    const { unmount } = renderPane(true, INFOS);
    const picker = screen.getByRole("group", { name: "从角色卡选择出场角色" });
    const btn = [...picker.querySelectorAll("button.chip")].find((c) =>
      c.textContent?.startsWith("林野"),
    )!;
    const wrap = btn.closest(".cast-wrap")!;
    vi.spyOn(wrap, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 80, top: 80, left: 0, right: 100, bottom: 90, width: 100, height: 10,
      toJSON: () => ({}),
    } as DOMRect);
    const h0 = window.innerHeight;
    Object.defineProperty(window, "innerHeight", { value: 100, configurable: true });
    fireEvent.focus(wrap);
    const card = screen.getByTestId("cast-hover-林野");
    expect(card.style.top).toBe("");
    expect(parseFloat(card.style.bottom)).toBeGreaterThan(0);
    Object.defineProperty(window, "innerHeight", { value: h0, configurable: true });
    unmount();
  });

  it("闭集外 role 不出标", () => {
    renderPane(false, { 林野: { ...LINYE, role: "客串" } });
    expect(screen.getByTestId("og-cast-view").querySelectorAll(".cast-role")).toHaveLength(0);
  });

  it("castInfos 从缺到有：不炸钩序（effect 挂在提前 return 之前）", () => {
    const { rerender } = renderPane(false);
    rerender(
      <OgPane
        form={FORM}
        characterNames={["林野", "小野"]}
        castInfos={INFOS}
        label="第02章 · 夜巡"
        editing={false}
        loading={false}
        onPatch={vi.fn()}
        gaps={[]}
        confirmed={false}
        saving={false}
        onStartEdit={vi.fn()}
        onCancelEdit={vi.fn()}
        onGapClick={vi.fn()}
        onSaveDraft={vi.fn()}
        onConfirm={vi.fn()}
        onGoWrite={vi.fn()}
      />,
    );
    expect(screen.getByTestId("og-cast-view").querySelectorAll(".cast-role")).toHaveLength(3);
  });

  it("CastHover 无 info 直渲染 children（防御路径： OgPane 侧只在有卡时才包 CastHover）", () => {
    render(
      <CastHover>
        <span className="chip">裸名</span>
      </CastHover>,
    );
    expect(screen.getByText("裸名")).toBeTruthy();
    expect(document.querySelector(".cast-wrap")).toBeNull();
  });
});
