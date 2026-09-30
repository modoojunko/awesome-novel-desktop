/** 朱雀检测结果条（c-zhuque-ai-detect：标题行右侧裸排，无卡片壳）。
 *  三态：结果（三占比＋概率参考＋清除/重检）／检测中（转圈）／失败（按错误族出口：
 *  401/503→去配置＋401 另有重试；429/502/504→重试；400/422/404→说明＋关闭）。
 *  stale＝结果置灰＋「正文已修改，结果可能过期」＋重检（重检入口替代清除/重检对）。 */
import type { ZhuqueState } from "@/hooks/useZhuqueCheck";

export default function ZhuqueHeadStrip({
  state,
  onRerun,
  onClear,
}: {
  state: ZhuqueState;
  onRerun: () => void;
  onClear: () => void;
}) {
  if (state.status === "idle") return null;
  if (state.status === "running") {
    return (
      <div className="zq-hd run" data-od-id="zhuque-head-strip" data-testid="zhuque-head-strip">
        <div className="hd-run">
          <span className="ra-spin" />
          检测中…
        </div>
      </div>
    );
  }
  if (state.status === "error") {
    const st = state.error?.status ?? 0;
    const reason = state.error?.reason ?? "";
    const keySide = st === 401 || reason === "zhuque_not_configured";
    const retryable = st === 429 || st === 502 || st === 504 || st === 0;
    return (
      <div className="zq-hd err" data-od-id="zhuque-head-strip" data-testid="zhuque-head-strip">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <p className="hd-errline">
            <b>检测失败</b>：{state.error?.message}
          </p>
          <span className="hd-act">
            {keySide && (
              <button
                className="btn btn-secondary"
                onClick={() => {
                  window.location.hash = "#/config?tab=zhuque";
                }}
              >
                去配置
              </button>
            )}
            {retryable && (
              <button className="btn btn-secondary" onClick={onRerun}>
                重试
              </button>
            )}
            {!keySide && !retryable && (
              <button className="btn btn-secondary" onClick={onClear}>
                关闭
              </button>
            )}
          </span>
        </div>
      </div>
    );
  }
  // 结果态（stale：置灰＋提示重检）
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  const r = state.result!;
  return (
    <div
      className={`zq-hd${state.stale ? " stale" : ""}`}
      data-od-id="zhuque-head-strip"
      data-testid="zhuque-head-strip"
    >
      <div className="hd-bar">
        <i style={{ width: `${pct(r.summary.human_ratio)}`, background: "color-mix(in oklch, var(--ok) 72%, transparent)" }} />
        <i style={{ width: `${pct(r.summary.suspect_ratio)}`, background: "color-mix(in oklch, var(--warn) 72%, transparent)" }} />
        <i style={{ width: `${pct(r.summary.ai_ratio)}`, background: "color-mix(in oklch, var(--err) 72%, transparent)" }} />
      </div>
      <div className="hd-ratio">
        <span className="lg">
          <i style={{ background: "color-mix(in oklch, var(--ok) 72%, transparent)" }} />
          人工 <b>{pct(r.summary.human_ratio)}</b>
        </span>
        <span className="lg">
          <i style={{ background: "color-mix(in oklch, var(--warn) 72%, transparent)" }} />
          疑似 AI <b>{pct(r.summary.suspect_ratio)}</b>
        </span>
        <span className="lg">
          <i style={{ background: "color-mix(in oklch, var(--err) 72%, transparent)" }} />
          AI <b>{pct(r.summary.ai_ratio)}</b>
        </span>
        <span style={{ fontSize: 10.5, color: "var(--muted)" }}>
          {state.stale ? "正文已修改，结果可能过期" : "概率参考 · 非平台判定"}
        </span>
        <span className="hd-act">
          {state.stale ? (
            <button className="btn btn-ghost" onClick={onRerun} data-testid="zhuque-restale">
              重检
            </button>
          ) : (
            <>
              <button className="btn btn-ghost" data-testid="zq-clear" title="退出标注态" onClick={onClear}>
                清除标注
              </button>
              <button className="btn btn-ghost" data-testid="zq-rerun" title="整章重测" onClick={onRerun}>
                重检
              </button>
            </>
          )}
        </span>
      </div>
    </div>
  );
}
