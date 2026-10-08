// 弹层锚定助手（c-prose-model-select 评审整改）：两条弹层共用的换算——大屏 zoom 折算、
// 放不下翻转、限高。回归钉子来自评审实测：zoom=1.28 时按 rect 原值布置会宽 +186px、
// 左偏 15px、下移 54px。
import { describe, expect, it, vi } from "vitest";
import {
  PANEL_GAP,
  PANEL_MAX,
  PANEL_MIN,
  htmlZoom,
  placePanel,
} from "@/lib/panelAnchor";

/** 触发位矩形（视觉 px），与 Playwright 实测同一形状。 */
const rect = (top: number, opts: { h?: number; left?: number; w?: number } = {}) => {
  const h = opts.h ?? 40;
  return { top, bottom: top + h, left: opts.left ?? 520, width: opts.w ?? 520 };
};

describe("placePanel", () => {
  it("空间充足：下方展开，锚在触发位下缘 + 间距，宽度随 rect", () => {
    const p = placePanel(rect(100), 900, { zoom: 1 });
    expect(p).toEqual({ top: 146, bottom: undefined, left: 520, width: 520, maxHeight: PANEL_MAX });
  });

  it("下方放不下且上方更宽敞时：向上翻转（挂 bottom，自下向上长）", () => {
    // 视口 900、触发位 700..740 → 下方仅 160，上方 700 → 翻转
    const p = placePanel(rect(700), 900, { zoom: 1 });
    expect(p.bottom).toBe(900 - 700 + PANEL_GAP); // 下缘贴触发位上缘上方 6px
    expect(p.top).toBeUndefined();
    expect(p.maxHeight).toBe(Math.min(PANEL_MAX, 700 - PANEL_GAP));
  });

  it("大屏 zoom：rect 的视觉值折算回布局 px（宽度/左边/间距都不再被放大）", () => {
    const z = 1.28;
    const r = rect(0, { left: 666, w: 666, h: 51 });
    const p = placePanel(r, 1400, { zoom: z });
    expect(p.width).toBeCloseTo(666 / z, 5); // 布局 px → 视觉 666（不再 ×1.28）
    expect(p.left).toBeCloseTo(666 / z, 5);
    expect(p.top).toBeCloseTo(51 / z + PANEL_GAP, 5);
    expect(p.maxHeight).toBeLessThanOrEqual(PANEL_MAX);
  });

  it("zoom 下的翻转判据按视觉像素：视口 1000、触发位 900..950、zoom 1.1", () => {
    const p = placePanel(rect(900, { h: 50 }), 1000, { zoom: 1.1 });
    expect(p.bottom).toBeCloseTo(1000 / 1.1 - 900 / 1.1 + PANEL_GAP, 5);
  });

  it("空间极窄：maxHeight 不低于保底（不塌成 0）", () => {
    const p = placePanel(rect(70, { h: 10 }), 100, { zoom: 1 });
    expect(p.maxHeight).toBe(PANEL_MIN);
  });

  it("zoom 非法值兜底为 1（jsdom/旧浏览器 getComputedStyle.zoom 为空）", () => {
    const p = placePanel(rect(100), 900, { zoom: Number.NaN });
    expect(p.top).toBe(146);
    expect(p.left).toBe(520);
  });
});

describe("htmlZoom", () => {
  it("读 html 上的 zoom（大屏层生效时按实取）", () => {
    const spy = vi
      .spyOn(window, "getComputedStyle")
      .mockReturnValue({ zoom: "1.28" } as unknown as CSSStyleDeclaration);
    try {
      expect(htmlZoom()).toBe(1.28);
    } finally {
      spy.mockRestore();
    }
  });

  it("读不到（jsdom）/非数值/非正 → 兜底 1", () => {
    for (const raw of ["", "auto", "0", "-1"]) {
      const spy = vi
        .spyOn(window, "getComputedStyle")
        .mockReturnValue({ zoom: raw } as unknown as CSSStyleDeclaration);
      try {
        expect(htmlZoom()).toBe(1);
      } finally {
        spy.mockRestore();
      }
    }
  });
});
