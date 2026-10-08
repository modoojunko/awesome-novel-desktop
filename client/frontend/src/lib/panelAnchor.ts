/**
 * 弹出层锚定（c-prose-model-select 评审整改）：触发位视口矩形 → fixed 弹层的排版值。
 *
 * 两个坑一起收口，两条同族弹层共用（生成弹窗「生成模型」选择位、模型配置页模型选择器）：
 *  ① **大屏 zoom 层**：large-screen.css 把 `html { zoom: var(--ui-zoom) }`（视口 ≥2000px
 *     起放大，2560→≈1.28、4K 封顶 1.75）。`getBoundingClientRect()` 给的已是放大后的
 *     视觉值，直接塞进 fixed 的 top/left/width 会被**再放大一次**——实测（2560×1400、
 *     zoom=1.28）弹层宽 +186px、左偏 15px、下移 54px。故一律 `/zoom` 折算回布局 px。
 *  ② **下方放不下要翻转且限高**：改挂 `bottom`（自下向上生长）＋给 `maxHeight`，
 *     整层滚动。原实现按 266px 常量估算、弹层自身不限高：多配置时后几组落到视口外，
 *     fixed 元素既不可滚也拽不回来 → 那些模型点不到。
 */
export interface PanelRect {
  top: number;
  bottom: number;
  left: number;
  width: number;
}

export interface PanelPlacement {
  left: number;
  width: number;
  maxHeight: number;
  /** 下方展开：弹层上缘锚在触发位下缘下方 */
  top?: number;
  /** 向上翻转：弹层下缘锚在触发位上缘上方（自下向上生长） */
  bottom?: number;
}

/** 弹层与触发位的间距（布局 px）。 */
export const PANEL_GAP = 6;
/** 弹层高度上限（布局 px；与 design/model-config.css 的 .mp-panel max-height 同值）。 */
export const PANEL_MAX = 360;
/** 保底可视高度（布局 px）。 */
export const PANEL_MIN = 120;

/** html 上的大屏缩放（无 zoom / 旧浏览器 → 1；jsdom 读不到该属性也为 1）。 */
export function htmlZoom(): number {
  const z = Number.parseFloat(getComputedStyle(document.documentElement).zoom);
  return Number.isFinite(z) && z > 0 ? z : 1;
}

/** 计算弹层排版：返回布局 px，可直接铺到 `position: fixed` 的 inline style 上。 */
export function placePanel(
  rect: PanelRect,
  viewportH: number,
  opts: { max?: number; min?: number; gap?: number; zoom?: number } = {},
): PanelPlacement {
  const { max = PANEL_MAX, min = PANEL_MIN, gap = PANEL_GAP, zoom = htmlZoom() } = opts;
  const z = zoom > 0 ? zoom : 1;
  const gapV = gap * z; // 以下视觉 px
  const spaceBelow = viewportH - rect.bottom;
  const spaceAbove = rect.top;
  const flip = spaceBelow - gapV < max * z && spaceAbove > spaceBelow;
  const roomV = (flip ? spaceAbove : spaceBelow) - gapV;
  const availV = Math.max(min * z, Math.min(max * z, roomV));
  return {
    left: rect.left / z,
    width: rect.width / z,
    maxHeight: availV / z,
    ...(flip
      ? { bottom: (viewportH - rect.top) / z + gap }
      : { top: rect.bottom / z + gap }),
  };
}
