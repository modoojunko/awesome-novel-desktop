import { Ico, P } from "@/components/icons";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OnboardingCardProps {
  novelId: string;
  source: "ai" | "manual" | "import";
  variant: "empty-novel" | "imported-novel";
  onDismiss: () => void;
  /** 主按钮「开始设定」的额外行为（默认与 onDismiss 相同） */
  onStart?: () => void;
}

// ---------------------------------------------------------------------------
// Step configs
// ---------------------------------------------------------------------------

const EMPTY_NOVEL_STEPS = [
  { label: "设定", active: true },
  { label: "卷纲", active: false },
  { label: "章纲", active: false },
  { label: "提示词", active: false },
  { label: "写作", active: false },
  { label: "归档", active: false },
] as const;

const IMPORTED_NOVEL_STEPS = [
  { label: "设定", active: true },
  { label: "提示词", active: false },
  { label: "写作", active: false },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function OnboardingCard({
  variant,
  onDismiss,
  onStart,
}: OnboardingCardProps) {
  const isImported = variant === "imported-novel";
  const steps = isImported ? IMPORTED_NOVEL_STEPS : EMPTY_NOVEL_STEPS;
  const handleStart = onStart ?? onDismiss;

  return (
    <div
      className="relative animate-fade-up"
      style={{
        borderBottom: "1px solid var(--accent-20)",
        background:
          "linear-gradient(to right, var(--accent-6), var(--accent-2))",
      }}
    >
      <div className="px-6 py-5">
        {/* Close button */}
        <button
          onClick={onDismiss}
          className="icon-btn absolute top-3 right-3"
          aria-label="关闭"
        >
          <Ico d={P.close} size={15} />
        </button>

        {/* Title */}
        <h3 className="serif font-semibold text-lg mb-1" style={{ color: "var(--fg)" }}>
          {isImported ? "稿子已导入！接下来补充设定" : "你的第一本书从设定开始"}
        </h3>

        {/* Description */}
        <p
          className="text-sm mb-5 max-w-lg leading-relaxed"
          style={{ color: "var(--muted)" }}
        >
          {isImported
            ? "卷纲和章纲已由导入完成，补充设定后就能进入提示词和写作阶段。"
            : "按照六阶段创作流程，从设定开始，逐步完成卷纲、章纲、提示词、写作，最后归档。"}
        </p>

        {/* Mini timeline：点 + 标签（当前步高亮，其余弱化） */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-5">
          {steps.map((step) => (
            <span
              key={step.label}
              className="flex items-center gap-1.5 text-xs"
              style={{ color: step.active ? "var(--accent-strong)" : "var(--muted)" }}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: step.active ? "var(--accent)" : "var(--fg-soft)" }}
              />
              {step.label}
            </span>
          ))}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button onClick={handleStart} className="btn btn-primary btn-sm">
            {isImported ? "补充设定" : "开始设定"}
          </button>
          <button
            onClick={onDismiss}
            className="text-sm"
            style={{ color: "var(--muted)" }}
          >
            知道了
          </button>
        </div>
      </div>
    </div>
  );
}
