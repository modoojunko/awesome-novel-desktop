import { useFeature } from "@/hooks/useTier";
import { toast } from "@/lib/toast";

/**
 * AI 写作助手卡片（genre-signup-redesign tasks 3.2 / D4）。
 *
 * 结构：PRO 徽标并头部 + 标题 + 套餐归属/只加工不代写 + 若干**并列**能力行
 * （每行＝名称上 + 描述下从属 + 右箭头，整行可点）+ 底部来源/去向声明。
 *
 * 门控：`useFeature('settings-ai-fields')`（已登记的 memberOnly key，非 ai-assistant）。
 * 免费版＝可见 + 锁定（整卡降透明 .locked，点击给统一升级提示，不各自弹窗）。
 */
export interface AiCapabilityRow {
  /** 能力标识（data-aiact，供 e2e 定位）。 */
  key: string;
  /** 能力名称（上，粗体）。 */
  name: string;
  /** 能力描述（下，从属灰字）。 */
  desc: string;
  onClick: () => void;
  /** 前置未满足（如补缺失需先体检）→ 该行置灰 + hint（D14 前置守卫）。 */
  disabled?: boolean;
  /** 置灰原因（如「先体检」）。 */
  hint?: string;
}

export interface AiWriterAssistantProps {
  rows: AiCapabilityRow[];
  /** 底部来源/去向声明。 */
  footNote: string;
  title?: string;
  "data-od-id"?: string;
}

export default function AiWriterAssistant({
  rows,
  footNote,
  title = "AI 写作助手",
  "data-od-id": odId = "ai-assist",
}: AiWriterAssistantProps) {
  const unlocked = useFeature("settings-ai-fields");
  const locked = !unlocked;

  const guard = (fn: () => void) => () => {
    if (locked) {
      toast.info("这是会员功能，升级 PRO 后解锁——免费版写作能力完整");
      return;
    }
    fn();
  };

  return (
    <div className={`rail-assist${locked ? " locked" : ""}`} data-od-id={odId}>
      <div className="ra-head">
        <span className="plan-badge">PRO</span>
        <div className="rh-t">
          <b>{title}</b>
          <span>
            {locked
              ? "未解锁 · 升级 PRO 后本书 AI 即可用"
              : "已解锁 · 包含在你的 PRO 套餐（Max 同享）· 只加工你写的，不代写"}
          </span>
        </div>
      </div>
      {rows.map((r) => (
        <button
          key={r.key}
          className={`ra-step${r.disabled ? " ra-off" : ""}`}
          type="button"
          data-aiact={r.key}
          disabled={r.disabled}
          onClick={guard(r.onClick)}
        >
          <span className="ra-body">
            <b>
              {r.name}
              {r.disabled && r.hint && <span className="ra-hint">{r.hint}</span>}
            </b>
            <i>{r.desc}</i>
          </span>
          <span className="ra-arrow" aria-hidden="true">
            ›
          </span>
        </button>
      ))}
      <p className="ra-foot">{footNote}</p>
    </div>
  );
}
