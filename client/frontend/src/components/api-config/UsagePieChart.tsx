/**
 * SVG-based donut chart.
 *
 * Approach: Uses stroke-dasharray / stroke-dashoffset on <circle> elements
 * to render proportional arc segments. Each segment is offset by the cumulative
 * percentage of previous segments (via strokeDashoffset), and its visible length
 * is set via strokeDasharray. The whole chart is rotated -90deg so the first
 * segment starts at 12 o'clock (convention for donut charts).
 *
 * - Single segment: rendered as a full circle with a single stroke color.
 * - Multiple segments: one <circle> per segment with calculated dash params.
 * - Empty / zero-total / loading states: handled explicitly.
 *
 * 调色板与主题同源（走 --chart-N 令牌；内联样式不得直写颜色函数）：
 * 墨绿=accent 族、暖金=warn 族、赭红=err 族，再补黛蓝/紫棠/青三个邻近色相。
 */

interface UsagePieChartProps {
  data: Array<{ model: string; tokens: number }>;
  loading?: boolean;
}

const COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
];

export function UsagePieChart({ data, loading }: UsagePieChartProps) {
  if (loading) {
    return (
      <div className="flex justify-center py-4">
        <svg width="80" height="80" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r="32" fill="none" stroke="var(--border)" strokeWidth="14" />
        </svg>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return <p className="text-sm text-center py-4" style={{ color: "var(--muted)" }}>暂无用量数据</p>;
  }

  const total = data.reduce((s, d) => s + d.tokens, 0);
  if (total === 0) {
    return <p className="text-sm text-center py-4" style={{ color: "var(--muted)" }}>暂无用量数据</p>;
  }

  // Single segment: full circle
  if (data.length === 1) {
    return (
      <div className="flex flex-col items-center gap-2 py-2">
        <svg width="80" height="80" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r="32" fill="none" stroke={COLORS[0]} strokeWidth="14" />
        </svg>
        <div className="flex items-center gap-1 text-xs">
          <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: COLORS[0] }} />
          <span>{data[0].model}</span>
          <span style={{ color: "var(--muted)" }}>{total.toLocaleString()}</span>
        </div>
      </div>
    );
  }

  // Multi-segment donut
  let cumulative = 0;
  const segments = data.map((d, i) => {
    const percentage = d.tokens / total;
    const offset = cumulative * 360;
    const length = percentage * 360;
    cumulative += percentage;
    return { ...d, color: COLORS[i % COLORS.length], offset, length, percentage };
  });

  return (
    <div className="flex flex-col items-center gap-3 py-2">
      <svg width="80" height="80" viewBox="0 0 80 80">
        {segments.map((seg, i) => {
          const r = 32;
          const circumference = 2 * Math.PI * r;
          const dashLength = seg.length / 360 * circumference;
          const dashOffset = -seg.offset / 360 * circumference;
          return (
            <circle
              key={i}
              cx="40" cy="40" r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={`${dashLength} ${circumference - dashLength}`}
              strokeDashoffset={dashOffset}
              transform="rotate(-90, 40, 40)"
            />
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1 text-xs">
            <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: seg.color }} />
            <span>{seg.model}</span>
            <span style={{ color: "var(--muted)" }}>{Math.round(seg.percentage * 100)}%</span>
            <span style={{ color: "var(--muted)" }}>{seg.tokens.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
