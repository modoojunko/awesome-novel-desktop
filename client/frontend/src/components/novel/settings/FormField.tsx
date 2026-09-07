// 设定表单字段基元（book.html v2 表单语汇统一重皮，PR4）：
//   .field（label 内联 opt 提示 / ai-fill 右贴）+ .textarea/.input
//   .li-row 列表行 + .text-btn 添加一项；details.cfg 折叠组（TabBar 页签退役）
// 数据逻辑不动：AI 生成回调 / SettingSaveHandle（gap3 确认前落库）契约保持。

import type { ReactNode } from "react";
import { Ico, P } from "@/components/icons";

// ── SettingSaveHandle ─────────────────────────────────────────────
/** 表单保存句柄（gap3）：SettingsView 持 ref 调用，确认完成前先把内容落库 */
export type SettingSaveHandle = { save: () => Promise<boolean> };

// ── AI props ──────────────────────────────────────────────────────
interface AIProps {
  aiGeneratable?: boolean;
  onAIGenerate?: () => void;
  aiLoading?: boolean;
}

/** 「AI 帮我填」按钮（原型 ai-fill：label 行内右贴；外层已按 aiGeneratable 门控） */
function AiFill({ onAIGenerate, aiLoading }: Pick<AIProps, "onAIGenerate" | "aiLoading">) {
  if (!onAIGenerate) return null;
  return (
    <button
      className="ai-fill"
      type="button"
      title="AI 帮我填"
      onClick={onAIGenerate}
      disabled={aiLoading}
    >
      <Ico d={P.spark} sw={1.8} />
      {aiLoading ? "生成中" : "AI 帮我填"}
    </button>
  );
}

// ── Field（textarea 字段）──────────────────────────────────────────
export function Field({
  label, hint, value, onChange, placeholder, maxLength, rows, aiGeneratable, onAIGenerate, aiLoading,
}: {
  label: string; hint?: string; value: string; onChange: (v: string) => void;
  placeholder?: string; maxLength?: number; rows?: number;
} & AIProps) {
  return (
    <div className="field">
      <label>
        {label}
        {hint && <span className="opt">{hint}</span>}
        {aiGeneratable && <AiFill onAIGenerate={onAIGenerate} aiLoading={aiLoading} />}
      </label>
      <textarea
        className="textarea"
        value={value}
        rows={rows}
        placeholder={placeholder}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

// ── InputField（单行字段）──────────────────────────────────────────
export function InputField({
  label, hint, value, onChange, placeholder, maxLength, aiGeneratable, onAIGenerate, aiLoading,
}: {
  label: string; hint?: string; value: string; onChange: (v: string) => void;
  placeholder?: string; maxLength?: number;
} & AIProps) {
  return (
    <div className="field">
      <label>
        {label}
        {hint && <span className="opt">{hint}</span>}
        {aiGeneratable && <AiFill onAIGenerate={onAIGenerate} aiLoading={aiLoading} />}
      </label>
      <input
        className="input"
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

// ── ListEditor（li-row 列表 + 添加一项）────────────────────────────
export function ListEditor({
  label, hint, items, onChange, placeholder, maxLength, maxItems, aiGeneratable, onAIGenerate, aiLoading,
}: {
  label?: string; hint?: string; items: string[]; onChange: (v: string[]) => void;
  placeholder?: string; maxLength?: number; maxItems?: number;
} & AIProps) {
  return (
    <div className="field">
      {(label || aiGeneratable) && (
        <label>
          {label}
          {hint && <span className="opt">{hint}</span>}
          {aiGeneratable && <AiFill onAIGenerate={onAIGenerate} aiLoading={aiLoading} />}
        </label>
      )}
      {items.map((item, i) => (
        <div className="li-row" key={i}>
          <span className="li-i">{i + 1}.</span>
          <input
            className="input"
            value={item}
            placeholder={placeholder}
            maxLength={maxLength}
            onChange={(e) => {
              const n = [...items];
              n[i] = e.target.value;
              onChange(n);
            }}
          />
          <span className="acts">
            <button
              className="icon-btn"
              type="button"
              title="删除本行"
              onClick={() => onChange(items.filter((_, j) => j !== i))}
            >
              <Ico d={P.trash} sw={1.7} />
            </button>
          </span>
        </div>
      ))}
      {(!maxItems || items.length < maxItems) && (
        <button className="text-btn" type="button" onClick={() => onChange([...items, ""])}>
          <Ico d={P.plus} sw={2} size={13} />
          添加一项
        </button>
      )}
    </div>
  );
}

// ── Cfg（details.cfg 折叠组：summary 标题 + 可选 tag + chev）────────
export function Cfg({
  title, tag, open, children,
}: {
  title: string; tag?: string; open?: boolean; children: ReactNode;
}) {
  return (
    <details className="cfg" open={open || undefined}>
      <summary>
        {title}
        {tag && <span className="tag">{tag}</span>}
        {/* P.* 是元素串：走 innerHTML 注入（与 Ico 同口径），d= 会吃进整个 <path> 报错 */}
        <svg
          className="chev"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          width="13"
          height="13"
          dangerouslySetInnerHTML={{ __html: P.chevronDown }}
        />
      </summary>
      <div className="inner">{children}</div>
    </details>
  );
}
