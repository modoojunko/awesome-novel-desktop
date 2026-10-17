/**
 * 给颜色叠加透明度（c-legacy-color-fallback）。
 *
 * 内联样式不得直接写 oklch()/color-mix()——构建期有扫描闸门，且旧内核
 * （Chromium < 111）会把整条声明判为无效。动态色（例如节点徽标色）在这里
 * 算成 rgba；只认 hex 与 rgb/rgba，其他形态回落设计令牌 --fg-soft。
 */
export function withAlpha(color: string, alpha: number): string {
  const a = clamp01(alpha);
  const live = color.trim();

  const hex = live.match(/^#([0-9a-f]{3,8})$/i);
  if (hex) {
    let h = hex[1];
    if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join("");
    if (h.length === 6 || h.length === 8) {
      const r = parseInt(h.slice(0, 2), 16);
      const g = parseInt(h.slice(2, 4), 16);
      const b = parseInt(h.slice(4, 6), 16);
      const baseA = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
      return `rgba(${r}, ${g}, ${b}, ${round4(a * baseA)})`;
    }
  }

  const rgb = live.match(/^rgba?\((.*)\)$/i);
  if (rgb) {
    const parts = rgb[1].trim().split(/\s*[,/]\s*|\s+/).filter(Boolean);
    if (parts.length >= 3 && parts.slice(0, 3).every((p) => !Number.isNaN(parseFloat(p)))) {
      const channel = (raw: string) => {
        const v = raw.endsWith("%") ? (parseFloat(raw) / 100) * 255 : parseFloat(raw);
        return Math.round(Math.min(255, Math.max(0, v)));
      };
      const baseA =
        parts[3] === undefined
          ? 1
          : parts[3].endsWith("%")
            ? parseFloat(parts[3]) / 100
            : parseFloat(parts[3]);
      return `rgba(${channel(parts[0])}, ${channel(parts[1])}, ${channel(parts[2])}, ${round4(
        a * (Number.isNaN(baseA) ? 0 : baseA),
      )})`;
    }
  }

  return "var(--fg-soft)";
}

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0;
  return Math.min(1, Math.max(0, v));
}

function round4(v: number): number {
  return Math.round(clamp01(v) * 10000) / 10000;
}
