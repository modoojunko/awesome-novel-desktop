// 正文页（book.html editor 复刻）：宋体 17/2.0 · 680 版心 · 段落缩进 ·
// contenteditable 段落化输入 · 自动保存三态（useChapterData store）·
// AI 流式写入（.generating + contentEditable=false + 停止）· 归档只读。
// 润色/扩写沿用 ContrastPreviewModal（过渡期 daisyUI 皮，PR 5 重皮）。
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import ContrastPreviewModal from "@/components/novel/ContrastPreviewModal";
import { useChapterData } from "@/hooks/useChapterData";
import { toast } from "@/lib/toast";
import {
  compressText,
  expandText,
  polishText,
  streamChapterContinue,
  streamChapterWrite,
  type StreamDoneMeta,
} from "@/lib/ai";
import type { SelectionCapture } from "@/lib/selection";
import {
  type FontSizePref,
  type LineHeightPref,
  setLastWriteSession,
} from "@/lib/prefs";

export interface ProseAIState {
  hasSelection: boolean;
  selectedText: string;
  continueLoading: boolean;
  polishLoading: boolean;
  expandLoading: boolean;
  compressLoading: boolean;
  streaming: boolean;
}

export const INITIAL_PROSE_AI_STATE: ProseAIState = {
  hasSelection: false,
  selectedText: "",
  continueLoading: false,
  polishLoading: false,
  expandLoading: false,
  compressLoading: false,
  streaming: false,
};

export interface ProseHandle {
  focus(): void;
  captureNow(): SelectionCapture | null;
  /** promptOverride：AI 弹窗编辑后的提示词（空 = 后端自动组装） */
  startWriting(prompt?: string): void;
  stopWriting(): void;
  /** capture：解锁链等场景预先捕获的选区/光标（弹窗焦点会丢现场选区） */
  continueWriting(capture?: SelectionCapture): void;
  polish(capture: SelectionCapture): void;
  expand(capture: SelectionCapture): void;
  compress(capture: SelectionCapture): void;
}

interface ProsePaneProps {
  projectId: string;
  chapterRef: string;
  fs: FontSizePref;
  lh: LineHeightPref;
  /** 三页签切换：仅隐藏保持挂载（正文脏状态 / 流式现场不丢） */
  hidden?: boolean;
  /** 状态上抛（updater 形态：调用方直接传 React setState） */
  onAIStateChange: (update: (prev: ProseAIState) => ProseAIState) => void;
  /** 续写恢复信号（顶栏 CTA）：n 递增触发，切到本页签后把编辑器滚回 pct */
  resumeScroll?: { n: number; pct: number };
  /** 排队门禁（workbench-frontier）：非主线端点且无正文的章——只读＋提示 */
  locked?: { reason: string };
  /** 写作进度上抛（顶栏 bar-here 跟随显示上次写到的章） */
  onWriteProgress?: (session: { ref: string; scroll: number; ts: number }) => void;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[m] ?? m,
  );
}

/** prose（\n 分段）→ 段落 HTML；空串清空编辑器（:empty ::placeholder 生效）。 */
function proseToHtml(prose: string): string {
  if (!prose) return "";
  return prose
    .split("\n")
    .map((p) => `<p>${escapeHtml(p) || "<br>"}</p>`)
    .join("");
}

/** DOM → 段落数组；裸文本节点（空编辑器首击）包进 <p>，div 兜底同收。 */
function collectParagraphs(div: HTMLDivElement): string[] {
  Array.from(div.childNodes).forEach((n) => {
    if (n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").length > 0) {
      const p = document.createElement("p");
      div.replaceChild(p, n);
      p.appendChild(n);
    }
  });
  return Array.from(div.children)
    .filter((el) => el.tagName === "P" || el.tagName === "DIV")
    .map((el) => (el.textContent ?? "").replace(/\u00A0/g, " "));
}

const ProsePane = forwardRef<ProseHandle, ProsePaneProps>(function ProsePane(
  { projectId, chapterRef, fs, lh, hidden, onAIStateChange, resumeScroll, onWriteProgress, locked },
  ref,
) {
  const editorRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const store = useChapterData(projectId, chapterRef);
  const { prose, status, setProse } = store;
  const archived = status === "archived";
  const notEditable = archived || !!locked;
  const [streaming, setStreaming] = useState(false);

  // 本地输入回路标记：store.prose 变化若来自本地输入则跳过重渲（保光标）
  const lastRenderedRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // 流式现场（停止时收尾用）
  const streamBaseRef = useRef("");
  const streamReceivedRef = useRef("");
  // 生成完工检查（三工序③：字数 + 叙事自查；提示性质，可关闭）
  const [qcReport, setQcReport] = useState<StreamDoneMeta | null>(null);
  const [preview, setPreview] = useState<{
    mode: "polish" | "expand" | "compress";
    capture: SelectionCapture;
    text: string | null;
    loading: boolean;
    error: string | null;
  } | null>(null);

  // 外部 prose 变化（加载/归档恢复/AI 完成/润色替换）→ 重渲 DOM
  useEffect(() => {
    const div = editorRef.current;
    if (!div) return;
    if (lastRenderedRef.current === prose) return;
    lastRenderedRef.current = prose;
    div.innerHTML = proseToHtml(prose);
  }, [prose, chapterRef]);

  // Enter 产生 <p> 而非 <div>（与 collectParagraphs 双保险）
  useEffect(() => {
    try {
      document.execCommand("defaultParagraphSeparator", false, "p");
    } catch {
      // 旧浏览器忽略；collectParagraphs 已兜底 div
    }
  }, []);

  // 卸载/切章：中断流式 + 清完工检查
  useEffect(() => {
    setQcReport(null);
    return () => {
      abortRef.current?.abort();
      streamingRef.current = false;
    };
  }, [chapterRef]);

  // ── 选区跟踪（AI 润色/扩写需要选中段落） ──────────────────────────────
  const captureNow = useCallback((): SelectionCapture | null => {
    const div = editorRef.current;
    const sel = window.getSelection();
    if (!div || !sel || sel.rangeCount === 0) return null;
    const range = sel.getRangeAt(0);
    if (!div.contains(range.commonAncestorContainer)) return null;
    const text = range.toString();
    if (!text.trim()) return null;
    const pre = document.createRange();
    pre.selectNodeContents(div);
    pre.setEnd(range.startContainer, range.startOffset);
    const start = pre.toString().length;
    const fullText = div.textContent ?? "";
    return { start, end: start + text.length, text, fullText };
  }, []);

  useEffect(() => {
    const onSel = () => {
      const cap = captureNow();
      onAIStateChange((prev) => ({
        ...prev,
        hasSelection: !!cap,
        selectedText: cap?.text ?? "",
      }));
    };
    document.addEventListener("selectionchange", onSel);
    return () => document.removeEventListener("selectionchange", onSel);
  }, [captureNow, onAIStateChange]);

  // ── 上次写作会话（行头归一「续写」）：输入/滚动节流 1s 记「本章+滚动比例」 ──
  const lastSaveRef = useRef(0);
  const saveProgress = useCallback(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const now = Date.now();
    if (now - lastSaveRef.current < 1000) return;
    lastSaveRef.current = now;
    const max = wrap.scrollHeight - wrap.clientHeight;
    const scroll = max > 4 ? Math.min(1, Math.max(0, wrap.scrollTop / max)) : 0;
    setLastWriteSession(projectId, chapterRef, scroll);
    onWriteProgress?.({ ref: chapterRef, scroll, ts: now });
  }, [projectId, chapterRef, onWriteProgress]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const onScroll = () => saveProgress();
    wrap.addEventListener("scroll", onScroll, { passive: true });
    return () => wrap.removeEventListener("scroll", onScroll);
  }, [saveProgress]);

  // ── 输入 → store（自动保存由 store 防抖；1.5s） ───────────────────────
  const handleInput = useCallback(() => {
    if (archived || locked || streamingRef.current) return;
    const div = editorRef.current;
    if (!div) return;
    const next = collectParagraphs(div).join("\n");
    lastRenderedRef.current = next;
    setProse(next);
    saveProgress();
  }, [archived, locked, setProse, saveProgress]);

  // ── 续写恢复：每个信号号只恢复一次（appliedResumeRef 守卫）。
  //    换章加载时内容未就绪 → rAF 轮询等 scrollHeight 长出来（上限 2s），
  //    空章/不可滚动则放弃。守卫是必须的：resumeScroll 每次渲染都是新对象，
  //    不守卫的话用户续写后每次输入/滚动都会被拽回旧位置 ────────────────────
  const appliedResumeRef = useRef(0);
  useEffect(() => {
    if (!resumeScroll || !resumeScroll.n) return;
    if (appliedResumeRef.current === resumeScroll.n) return;
    const wrap = wrapRef.current;
    if (!wrap) return;
    const start = performance.now();
    let raf = 0;
    const tick = () => {
      const max = wrap.scrollHeight - wrap.clientHeight;
      if (max > 4) {
        appliedResumeRef.current = resumeScroll.n;
        wrap.scrollTop = Math.min(1, Math.max(0, resumeScroll.pct)) * max;
        return;
      }
      if (performance.now() - start < 2000) {
        raf = requestAnimationFrame(tick);
      } else {
        // 放弃（空章本无可恢复），同样标记防重入
        appliedResumeRef.current = resumeScroll.n;
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [resumeScroll, chapterRef]);

  // ── AI 流式写入 ────────────────────────────────────────────────────────
  const renderStreamed = useCallback((base: string, generated: string) => {
    const div = editorRef.current;
    if (!div) return;
    const paras = [...(base ? base.split("\n") : []), ...generated.split("\n")];
    div.innerHTML = paras.map((p) => `<p>${escapeHtml(p) || "<br>"}</p>`).join("");
  }, []);

  const finishStream = useCallback(
    (fullText: string, ok: boolean, meta?: StreamDoneMeta) => {
      if (!streamingRef.current) return; // 已收尾（停止后又 onDone 等）
      streamingRef.current = false;
      setStreaming(false);
      onAIStateChange((prev) => ({ ...prev, streaming: false }));
      const base = streamBaseRef.current;
      const generated = fullText || streamReceivedRef.current;
      const next = [base, generated].filter((s) => s && s.trim()).join("\n");
      lastRenderedRef.current = next;
      setProse(next);
      if (ok) {
        toast.success("AI 生成完成 · 已保存");
        if (meta && (meta.word_check || meta.self_check)) setQcReport(meta);
      }
    },
    [setProse, onAIStateChange],
  );

  const startStream = useCallback(
    (continuation: boolean, promptOverride?: string, preCapture?: SelectionCapture) => {
      const div = editorRef.current;
      if (!div || streamingRef.current) return;
      if (archived) {
        toast.error("已归档章节不可生成");
        return;
      }
      const base = lastRenderedRef.current ?? prose;
      const cap = preCapture ?? captureNow();
      const pos = continuation ? (cap ? cap.end : base.length) : base.length;
      streamBaseRef.current = base;
      streamReceivedRef.current = "";
      streamingRef.current = true;
      setStreaming(true);
      onAIStateChange((prev) => ({ ...prev, streaming: true }));
      const cbs = {
        onChunk: (t: string) => {
          streamReceivedRef.current += t;
          renderStreamed(streamBaseRef.current, streamReceivedRef.current);
        },
        onDone: (full: string, meta?: StreamDoneMeta) => finishStream(full, true, meta),
        onError: (e: string) => {
          toast.error(e);
          finishStream(streamReceivedRef.current, false);
        },
      };
      abortRef.current = continuation
        ? streamChapterContinue(projectId, chapterRef, pos, cbs)
        : streamChapterWrite(projectId, chapterRef, cbs, promptOverride);
    },
    [projectId, chapterRef, prose, archived, captureNow, renderStreamed, finishStream, onAIStateChange],
  );

  // ── 润色 / 扩写（选中段落 → 对照预览 → 接受替换） ─────────────────────
  const runTransform = useCallback(
    async (mode: "polish" | "expand" | "compress", capture: SelectionCapture) => {
      const ctxBefore = capture.fullText.slice(Math.max(0, capture.start - 200), capture.start);
      const ctxAfter = capture.fullText.slice(capture.end, capture.end + 200);
      setPreview({ mode, capture, text: null, loading: true, error: null });
      onAIStateChange((prev) => ({
        ...prev,
        polishLoading: mode === "polish",
        expandLoading: mode === "expand",
        compressLoading: mode === "compress",
      }));
      try {
        const text =
          mode === "polish"
            ? await polishText(projectId, chapterRef, capture.text, ctxBefore, ctxAfter)
            : mode === "expand"
              ? await expandText(projectId, chapterRef, capture.text, ctxBefore, ctxAfter)
              : await compressText(projectId, chapterRef, capture.text, ctxBefore, ctxAfter);
        setPreview({ mode, capture, text, loading: false, error: null });
      } catch (e) {
        setPreview({
          mode,
          capture,
          text: null,
          loading: false,
          error: (e as Error)?.message || "请求出错",
        });
      } finally {
        onAIStateChange((prev) => ({
          ...prev,
          polishLoading: false,
          expandLoading: false,
          compressLoading: false,
        }));
      }
    },
    [projectId, chapterRef, onAIStateChange],
  );

  useImperativeHandle(
    ref,
    () => ({
      focus: () => editorRef.current?.focus(),
      captureNow,
      startWriting: (prompt?: string) => startStream(false, prompt),
      stopWriting: () => {
        // 中断 + 立即收尾（fetch abort 不回调 onDone/onError）
        abortRef.current?.abort();
        finishStream(streamReceivedRef.current, false);
      },
      continueWriting: (capture?: SelectionCapture) => startStream(true, undefined, capture),
      polish: (capture: SelectionCapture) => void runTransform("polish", capture),
      expand: (capture: SelectionCapture) => void runTransform("expand", capture),
      compress: (capture: SelectionCapture) => void runTransform("compress", capture),
    }),
    [captureNow, startStream, finishStream, runTransform],
  );

  const words = prose.replace(/\s/g, "").length;

  return (
    <>
      {/* 生成完工检查（三工序③：字数 ±10% + 叙事自查；提示性质，可关闭） */}
      {qcReport && (qcReport.word_check || qcReport.self_check) && (
        <div
          className="readonly-banner"
          data-testid="qc-banner"
          hidden={hidden}
          style={{ alignItems: "flex-start" }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M9 11l3 3 8-8" />
            <path d="M20 12v6a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h9" />
          </svg>
          <span style={{ flex: 1, minWidth: 0 }}>
            {qcReport.word_check && (
              <span data-testid="qc-word" style={{ display: "block" }}>
                {qcReport.word_check.below_limit ? (
                  <>
                    <b>字数未达标</b>：目标约 {qcReport.word_check.target} 字 · 实写{" "}
                    {qcReport.word_check.actual} 字（低于目标 90%），可用「续写」补足。
                  </>
                ) : (
                  <>
                    <b>字数达标</b>：实写 {qcReport.word_check.actual} / 目标约{" "}
                    {qcReport.word_check.target} 字。
                  </>
                )}
              </span>
            )}
            {qcReport.self_check && qcReport.self_check.length > 0 && (
              <span data-testid="qc-self" style={{ display: "block" }}>
                <b>叙事自查提示</b>（非阻断）：
                {qcReport.self_check.map((issue) => (
                  <span key={issue.rule} style={{ display: "block" }}>
                    · {issue.rule}（{issue.excerpts.length} 处）
                    {issue.excerpts[0] && (
                      <i style={{ color: "var(--muted)" }}>
                        {" "}
                        如「{issue.excerpts[0].slice(0, 30)}
                        {issue.excerpts[0].length > 30 ? "…" : ""}」
                      </i>
                    )}
                  </span>
                ))}
              </span>
            )}
            {qcReport.self_check && qcReport.self_check.length === 0 && (
              <span data-testid="qc-self" style={{ display: "block" }}>
                <b>叙事自查</b>：七条规则均未命中。
              </span>
            )}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setQcReport(null)}
            data-testid="qc-close"
          >
            知道了
          </button>
        </div>
      )}
      {locked && !hidden && (
        <div className="readonly-banner" data-od-id="frontier-lock-banner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v5M12 16h.01" />
          </svg>
          <span>
            <b>{locked.reason}</b>。完成前面的章节并归档后，这里会自动开放。
          </span>
        </div>
      )}
      <div className="editor-wrap" hidden={hidden} ref={wrapRef}>
        {/* contentEditable 用字符串 "false"：布尔 false 会被 React 整个丢掉属性，
            归档/流式态需要 contenteditable="false" 保住只读语义（a11y + e2e 可判定） */}
        <div
          ref={editorRef}
          className={`editor ${fs} ${lh}${streaming ? " generating" : ""}`}
          contentEditable={!notEditable && !streaming ? true : "false"}
          data-placeholder={words ? "" : "从这一章开始写……"}
          suppressContentEditableWarning
          onInput={handleInput}
        />
      </div>

      {preview && (
        <ContrastPreviewModal
          open
          mode={preview.mode}
          originalText={preview.capture.text}
          modifiedText={preview.text}
          loading={preview.loading}
          error={preview.error}
          onClose={() => setPreview(null)}
          onAccept={() => {
            const { capture, text } = preview;
            if (text) {
              const next =
                capture.fullText.slice(0, capture.start) +
                text +
                capture.fullText.slice(capture.end);
              lastRenderedRef.current = next;
              setProse(next);
              toast.success(
                preview.mode === "polish"
                  ? "已应用润色"
                  : preview.mode === "expand"
                    ? "已应用扩写"
                    : "已应用压缩",
              );
            }
            setPreview(null);
          }}
          onReject={() => {
            setPreview(null);
            toast.info("已放弃修改");
          }}
          onRetry={() => void runTransform(preview.mode, preview.capture)}
        />
      )}
    </>
  );
});

export default ProsePane;
