// 题材知识导入二选一弹窗（c-kb-book-scope 弹窗二选一）：
// 定题材后问「从知识库导入默认设定 / 我自己一项项设定」。选导入在本弹窗内跑
// SSE 进度（逐概念组复制 → 落基线设定），选自己设定落 declined 标记不再自动弹；
// 导入中途关闭＝abort（副本/标签单事务提交在末尾，未完成即零写入）。
import { useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { kbApi, type BookScopeProgressEvent } from "@/lib/kbApi";

type Stage = "choose" | "importing" | "done" | "error";

interface ImportChoiceModalProps {
  projectId: string;
  open: boolean;
  /** 差异计数（题材命中未导入条数）——弹窗文案的数据来源 */
  newCount: number;
  /** 题材展示名（可选，缺省用「本题材」） */
  genreLabel?: string;
  onClose: () => void;
  /** 导入完成：父层刷新差异计数/来源行 */
  onImported?: () => void;
  /** 选「我自己设定」：父层记 declined，不再自动弹 */
  onDeclined?: () => void;
}

export default function ImportChoiceModal({
  projectId,
  open,
  newCount,
  genreLabel,
  onClose,
  onImported,
  onDeclined,
}: ImportChoiceModalProps) {
  const [stage, setStage] = useState<Stage>("choose");
  const [total, setTotal] = useState(0);
  const [done, setDone] = useState(0);
  const [concept, setConcept] = useState("");
  const [baseline, setBaseline] = useState(false);
  const [imported, setImported] = useState(0);
  const [err, setErr] = useState("");
  const ctrlRef = useRef<AbortController | null>(null);

  // 重开＝重新征询：上次的进度/结果不残留
  useEffect(() => {
    if (!open) return;
    setStage("choose");
    setTotal(0);
    setDone(0);
    setConcept("");
    setBaseline(false);
    setImported(0);
    setErr("");
  }, [open]);

  // 卸载兜底：流还挂着就 abort（服务端单事务未提交＝零写入）
  useEffect(() => () => ctrlRef.current?.abort(), []);

  const label = genreLabel?.trim() || "本题材";

  // 进度：复制段占 88%（未知总数时给确定性的「读取中」态），落基线 92%，完成 100%
  const pct =
    stage === "done"
      ? 100
      : baseline
        ? 92
        : total > 0
          ? Math.round((done / total) * 88)
          : 6;

  const doImport = () => {
    /* v8 ignore start —— 重入守卫：导入态按钮已卸载，UI 不可达（双击/程序调用兜底） */
    if (stage === "importing") return;
    /* v8 ignore stop */
    // 重试＝从头再来：上一轮的进度/阶段不带进来（否则先显示旧 92%/「落基线」）
    setTotal(0);
    setDone(0);
    setConcept("");
    setBaseline(false);
    setImported(0);
    setStage("importing");
    setErr("");
    ctrlRef.current = kbApi.bookScopeImportStream(
      projectId,
      (ev: BookScopeProgressEvent) => {
        if (ev.type === "phase") {
          if (ev.phase === "copy") {
            if (typeof ev.total === "number") setTotal(ev.total);
            if (ev.concept) {
              setConcept(ev.concept);
              setDone(ev.done ?? 0);
            }
          } else if (ev.phase === "baseline") {
            setBaseline(true);
          }
          return;
        }
        if (ev.type === "done") {
          setImported(ev.imported ?? 0);
          setStage("done");
          onImported?.();
          return;
        }
        setErr(ev.message || "导入失败，请重试");
        setStage("error");
      },
    );
  };

  const doDecline = async () => {
    try {
      await kbApi.bookScopeDecline(projectId, true);
    } catch {
      /* 标记失败不挡操作：来源行仍是手动补平出口 */
    }
    onDeclined?.();
    onClose();
  };

  const close = () => {
    if (stage === "importing") ctrlRef.current?.abort();
    onClose();
  };

  const phaseText =
    stage === "done"
      ? imported > 0
        ? `已导入 ${imported} 条知识，基线设定已就绪`
        // 并发的另一处导入已落库（本请求 skipped 全部）：不报「导入 0 条」吓人
        : "这本书已经有这些知识了，基线设定已就绪"
      : baseline
        ? "正在落基线设定（文风 / 世界舞台）…"
        : total > 0
          ? `正在复制「${concept || "知识"}」（${done}/${total}）`
          : "正在读取知识库…";

  return (
    <Modal
      open={open}
      onClose={close}
      title="这本书的默认设定"
      width={480}
      wbStyle
      locked={false}
      footer={
        stage === "choose" ? undefined : stage === "done" || stage === "error" ? (
          <button className="btn btn-primary btn-sm" onClick={close} data-testid="kb-import-close">
            知道了
          </button>
        ) : (
          <button className="btn btn-secondary btn-sm" onClick={close}>
            取消
          </button>
        )
      }
    >
      {stage === "choose" && (
        <div data-testid="kb-import-choice">
          <p className="mb-3 text-[13px] leading-relaxed text-[var(--muted)]">
            知识库里已经有「{label}」题材的默认设定（{newCount} 条手法 / 文风 / 文笔 /
            世界设定）。先导入这本小说，还是全部自己填？
          </p>
          <div className="space-y-2">
            <button
              type="button"
              onClick={doImport}
              data-testid="kb-import-from-kb"
              className="w-full rounded-xl border border-[var(--border)] p-3 text-left transition-colors hover:border-[var(--accent)]"
            >
              <div className="text-[13px] font-medium">从知识库导入默认设定</div>
              <div className="mt-0.5 text-[12px] leading-relaxed text-[var(--muted)]">
                复制 {newCount} 条题材知识到这本书，并落文风 / 世界基线；导入后都能逐项改
              </div>
            </button>
            <button
              type="button"
              onClick={() => void doDecline()}
              data-testid="kb-import-manual"
              className="w-full rounded-xl border border-[var(--border)] p-3 text-left transition-colors hover:border-[var(--accent)]"
            >
              <div className="text-[13px] font-medium">我自己一项项设定</div>
              <div className="mt-0.5 text-[12px] leading-relaxed text-[var(--muted)]">
                不导入，从空白开始；之后也可以在设定页从知识库补
              </div>
            </button>
          </div>
        </div>
      )}

      {(stage === "importing" || stage === "done") && (
        <div data-testid="kb-import-progress">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <span className="text-[13px]" data-testid="kb-import-phase">
              {phaseText}
            </span>
            <span className="text-[12px] tabular-nums text-[var(--muted)]">{pct}%</span>
          </div>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-[var(--fg-soft)]"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            data-testid="kb-import-progress-bar"
          >
            <i
              className="block h-full rounded-full bg-[var(--accent)] transition-[width] duration-200"
              style={{ width: `${pct}%` }}
            />
          </div>
          {stage === "done" && (
            <p className="mt-3 text-[12px] leading-relaxed text-[var(--muted)]">
              书级知识已经独立成册：之后的写作只从这里取材，作家库再新增也不会混进来。
            </p>
          )}
        </div>
      )}

      {stage === "error" && (
        <div data-testid="kb-import-error">
          <p className="mb-3 text-[13px] text-[var(--muted)]">{err}</p>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={doImport}
            data-testid="kb-import-retry"
          >
            重试
          </button>
        </div>
      )}
    </Modal>
  );
}
