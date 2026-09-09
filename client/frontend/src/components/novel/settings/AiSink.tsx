import type { ReactNode } from "react";

/**
 * AI 结果区（genre-signup-redesign tasks 3.3 / D3）。
 *
 * TintPanel（fg-soft）只读说明，落在**左侧对应输入框正下方**；顶部操作名标签 +
 * 内容 + 采纳/重试。**必须用 --fg-soft，不得用 --surface**（surface 是可编辑/
 * 可操作容器底色，与输入框撞色会误判结果区可编辑）。
 *
 * 状态所有权在调用方面板（简介在 IntroPanel、题材在 GenrePanel）：本组件只渲染，
 * 采纳/重试通过回调上抛。
 */
export interface AiSinkProps {
  /** 操作名标签（如「AI 体检 · 六段逐项」）。 */
  label: string;
  /** 结果内容（体检行 / 候选文本 / 前后对照）。 */
  children: ReactNode;
  /** 采纳按钮文案（不传则不渲染采纳）。 */
  adoptText?: string;
  onAdopt?: () => void;
  onRetry?: () => void;
  "data-od-id"?: string;
}

export default function AiSink({
  label,
  children,
  adoptText,
  onAdopt,
  onRetry,
  "data-od-id": odId = "ai-sink",
}: AiSinkProps) {
  return (
    <div className="ai-sink" data-od-id={odId}>
      <div className="aiz-head">{label}</div>
      {children}
      {(onAdopt || onRetry) && (
        <div className="ans-act">
          {onAdopt && (
            <button className="primary" type="button" onClick={onAdopt}>
              {adoptText ?? "采纳"}
            </button>
          )}
          {onRetry && (
            <button type="button" onClick={onRetry}>
              重试
            </button>
          )}
        </div>
      )}
    </div>
  );
}
