// 正文页（book.html editor 复刻）：宋体 17/2.0 · 680 版心 · 段落缩进 ·
// 自动保存三态（useChapterData store）· AI 流式写入（.generating + 停止）· 归档只读。
// 2026-09-27 查看/编辑两态（c-prose-edit-gate，对齐卷纲口径）：默认只读阅读，
// 「编辑正文」进编辑态；AI 生成/续写恢复/重写/去写正文四条链由上层自动进编辑；
// 归档/排队/旧稿锁优先于编辑态（锁定期不可写，横幅照旧）。
// 2026-09-27 编辑器内核迁移 TipTap（c-prose-editor-tiptap）：schema 仅段落，
// 文档 = chapter.prose（\n 分段纯文本）的投影——序列化单源见 proseDoc.ts。
//   IME 安全：组合期（view.composing）挂起外部替换，组合结束补一次同步；
//   AI 流式＝chunk 事务追加（addToHistory:false，SHALL NOT 整文档重建），
//   收尾两步「删流式区间（不入史）＋整段写回（入史）」使整次生成成为
//   可整体撤销的一个历史单元（一次撤销回到生成前）；
//   粘贴一律降级纯文本段落；选区捕获改走 PM 选区（SelectionCapture 形状不变）；
//   Enter 分段由 TipTap 核心键位（splitBlock）承担，execCommand 退役。
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Placeholder } from "@tiptap/extensions";
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
import { docToProse, linesToParagraphs, proseToDoc } from "./proseDoc";

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
  /** 查看/编辑两态（c-prose-edit-gate，对齐卷纲口径）：false＝只读阅读（默认），
   *  true＋非锁定＝可写。归档/排队/旧稿锁定 SHALL 优先于编辑态。 */
  editing?: boolean;
  /** 「编辑正文」入口回调（仅查看态且非锁定时出现） */
  onStartEdit?: () => void;
}

/** 纯文本偏移（docToProse 口径，段间 \n 计 1）→ PM 文档位置。越界回落末段末尾。 */
function textOffsetToPmPos(
  doc: {
    content?: {
      forEach?: (fn: (node: { textContent?: string; nodeSize?: number }) => void) => void;
    };
  },
  offset: number,
): number {
  let pos = 0;
  let remaining = offset;
  let result: number | null = null;
  doc.content?.forEach?.((para) => {
    const textLen = (para.textContent ?? "").length;
    const nodeSize = para.nodeSize ?? textLen + 2;
    if (result == null && remaining <= textLen) {
      result = pos + 1 + remaining;
    }
    remaining -= textLen + 1;
    pos += nodeSize;
  });
  return result ?? Math.max(0, pos - 1);
}

const ProsePane = forwardRef<ProseHandle, ProsePaneProps>(function ProsePane(
  { projectId, chapterRef, fs, lh, hidden, onAIStateChange, resumeScroll, onWriteProgress, locked, editing, onStartEdit },
  ref,
) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const store = useChapterData(projectId, chapterRef);
  const { prose, status, setProse } = store;
  const archived = status === "archived";
  const notEditable = archived || !!locked;
  // 查看/编辑两态（c-prose-edit-gate）：编辑态＋非锁定才可写；锁定语义优先
  const editable = !!editing && !notEditable;
  const [streaming, setStreaming] = useState(false);

  // 本地输入回路标记：store.prose 变化若来自本地输入则跳过重渲（保光标）
  const lastSyncedRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // 流式现场（插入点 / 起点 / 收尾定位用）
  const streamPosRef = useRef(0);
  const streamStartRef = useRef(0);
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

  // IME 组合期挂起的外部替换（组合结束补一次同步）
  const pendingProseRef = useRef<string | null>(null);

  const editor = useEditor(
    {
      // 仅段落（c-prose-editor-tiptap）：块级/标记扩展全部关闭，只留文档/段落/文本＋撤销
      extensions: [
        StarterKit.configure({
          blockquote: false,
          bold: false,
          bulletList: false,
          code: false,
          codeBlock: false,
          dropcursor: false,
          gapcursor: false,
          hardBreak: false,
          heading: false,
          horizontalRule: false,
          italic: false,
          link: false,
          listItem: false,
          orderedList: false,
          strike: false,
          trailingNode: false,
          underline: false,
        }),
        Placeholder.configure({ placeholder: "从这一章开始写……" }),
      ],
      editable: false, // 由 editable effect 统一接管（两态＋锁定＋流式）
      editorProps: {
        attributes: {
          class: `editor ${fs} ${lh}`,
          "data-testid": "prose-editor",
        },
        // 粘贴一律降级纯文本段落（spec：格式标记剥离、多段结构保留）
        handlePaste: (view, event) => {
          const text = event.clipboardData?.getData("text/plain");
          if (text == null) return false;
          const lines = text.replace(/\r\n?/g, "\n").split("\n");
          const tr = view.state.tr;
          let { from, to } = view.state.selection;
          const first = lines[0] ?? "";
          if (first) tr.insertText(first, from, to);
          else if (to > from) tr.delete(from, to);
          let cur = from + first.length;
          for (let i = 1; i < lines.length; i++) {
            tr.split(cur);
            cur += 1;
            const line = lines[i];
            if (line) {
              tr.insertText(line, cur, cur);
              cur += line.length;
            }
          }
          view.dispatch(tr);
          return true;
        },
      },
      onUpdate: ({ editor: ed }) => {
        if (streamingRef.current || !ed.isEditable || ed.isDestroyed) return;
        const next = docToProse(ed.getJSON());
        lastSyncedRef.current = next;
        setProse(next);
        saveProgressRef.current();
      },
    },
    // 单实例长驻（c-prose-editor-tiptap）：切章走 setContent 同步，SHALL NOT 随章销毁重建
    // ——重建窗口期 effect 会拿到已销毁实例（.commands 抛错 → 子树被卸载，树空白）
    [],
  );

  // ── 上次写作会话（行头归一「续写」）：输入/滚动节流 1s 记「本章+滚动比例」 ──
  const lastSaveTimeRef = useRef(0);
  const saveProgress = useCallback(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const now = Date.now();
    if (now - lastSaveTimeRef.current < 1000) return;
    lastSaveTimeRef.current = now;
    const max = wrap.scrollHeight - wrap.clientHeight;
    const scroll = max > 4 ? Math.min(1, Math.max(0, wrap.scrollTop / max)) : 0;
    setLastWriteSession(projectId, chapterRef, scroll);
    onWriteProgress?.({ ref: chapterRef, scroll, ts: now });
  }, [projectId, chapterRef, onWriteProgress]);
  // onUpdate 经 options 同步拿最新闭包；ref 兜底防首帧 TDZ
  const saveProgressRef = useRef(saveProgress);
  saveProgressRef.current = saveProgress;

  // 编辑态/流式 → contenteditable（e2e 与 a11y 判定口保持 contenteditable 属性）
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    editor.setEditable(editable && !streaming);
  }, [editor, editable, streaming]);

  // 版式偏好类与流式样式挂编辑器宿主（TipTap 自管 contenteditable，类由这里定）。
  // 只增删自己这几个类：整体赋 className 会洗掉 ProseMirror 自身的根类/动态类。
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const { classList } = editor.view.dom;
    classList.remove("editor", "fs-s", "fs-m", "fs-l", "lh-tight", "lh-comfy", "lh-loose", "generating");
    classList.add("editor", fs, lh);
    if (streaming) classList.add("generating");
  }, [editor, fs, lh, streaming]);

  // 外部 prose 变化（加载/归档恢复/润色替换/AI 完成落盘）→ 整文档替换；
  // 本地输入回路（指纹一致）与 IME 组合期跳过（组合结束补同步）。
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    if (lastSyncedRef.current === prose) return;
    if (editor.view.composing) {
      pendingProseRef.current = prose;
      return;
    }
    lastSyncedRef.current = prose;
    editor.commands.setContent(proseToDoc(prose), { emitUpdate: false });
    // 对齐旧契约：外部载入后光标回文首（本地输入走 onUpdate 回路，不经过这里，光标不动）
    editor.commands.setTextSelection(0);
  }, [editor, prose, chapterRef]);

  // IME 组合结束 → 补挂起的外部替换
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const dom = editor.view.dom;
    const onCompositionEnd = () => {
      const pending = pendingProseRef.current;
      if (pending == null || editor.isDestroyed) return;
      pendingProseRef.current = null;
      if (lastSyncedRef.current === pending) return;
      lastSyncedRef.current = pending;
      editor.commands.setContent(proseToDoc(pending), { emitUpdate: false });
      editor.commands.setTextSelection(0);
    };
    dom.addEventListener("compositionend", onCompositionEnd);
    return () => dom.removeEventListener("compositionend", onCompositionEnd);
  }, [editor]);

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
    if (!editor || editor.isDestroyed) return null;
    // 读 DOM 选区而非 editor.state.selection：PM 消化 selectionchange 有延迟，
    // 事件当刻 state 可能还是上一次的折叠选区（实测：键盘扩选后 state 停在旧点）。
    const dom = editor.view.dom;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return null;
    const range = sel.getRangeAt(0);
    if (!dom.contains(range.commonAncestorContainer)) return null;
    let from: number;
    let to: number;
    try {
      from = editor.view.posAtDOM(range.startContainer, range.startOffset);
      to = editor.view.posAtDOM(range.endContainer, range.endOffset);
    } catch {
      return null; // DOM 位置不在文档视图内（切走中的半截选区）
    }
    if (to < from) [from, to] = [to, from];
    // 文本取自 doc（\n 连接段间），与 fullText / 采纳替换的偏移坐标系一致
    const text = editor.state.doc.textBetween(from, to, "\n");
    if (!text.trim()) return null;
    const start = editor.state.doc.textBetween(0, from, "\n").length;
    const fullText = docToProse(editor.getJSON());
    return { start, end: start + text.length, text, fullText };
  }, [editor]);

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

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const onScroll = () => saveProgress();
    wrap.addEventListener("scroll", onScroll, { passive: true });
    return () => wrap.removeEventListener("scroll", onScroll);
  }, [saveProgress]);

  // ── AI 流式写入（事务追加，SHALL NOT 整文档重建；不入撤销史） ──────────
  /** 追加一段生成文本到插入点（段内换行 = 拆新段）。 */
  const appendChunk = useCallback(
    (chunk: string) => {
      if (!editor || editor.isDestroyed || !chunk) return;
      const { state, view } = editor;
      const tr = state.tr;
      tr.setMeta("addToHistory", false);
      let cur = streamPosRef.current;
      const lines = chunk.replace(/\r\n?/g, "\n").split("\n");
      lines.forEach((line, i) => {
        if (line) {
          tr.insertText(line, cur, cur);
          cur += line.length;
        }
        if (i < lines.length - 1) {
          tr.split(cur);
          cur += 1;
        }
      });
      view.dispatch(tr);
      streamPosRef.current = cur;
    },
    [editor],
  );

  const finishStream = useCallback(
    (fullText: string, ok: boolean, meta?: StreamDoneMeta) => {
      if (!streamingRef.current) return; // 已收尾（停止后又 onDone 等）
      streamingRef.current = false;
      setStreaming(false);
      onAIStateChange((prev) => ({ ...prev, streaming: false }));
      const base = streamBaseRef.current;
      const generated = fullText || streamReceivedRef.current;
      const next = [base, generated].filter((s) => s && s.trim()).join("\n");
      // 两步收尾（c-prose-editor-tiptap）：①删流式区间（不入史）②整段写回（入史）
      // ——整次生成成为可整体撤销的一个历史单元（一次撤销回到生成前起点）
      if (editor && !editor.isDestroyed) {
        const start = streamStartRef.current;
        const end = streamPosRef.current;
        if (end > start) {
          const tr = editor.state.tr.delete(start, end);
          tr.setMeta("addToHistory", false);
          editor.view.dispatch(tr);
        }
        if (generated.trim()) {
          editor
            .chain()
            .insertContentAt(start, linesToParagraphs(generated), {
              updateSelection: false,
            })
            .run();
        }
      }
      lastSyncedRef.current = next;
      setProse(next);
      if (ok) {
        toast.success("AI 生成完成 · 已保存");
        if (meta && (meta.word_check || meta.self_check)) setQcReport(meta);
      }
    },
    [editor, setProse, onAIStateChange],
  );

  const startStream = useCallback(
    (continuation: boolean, promptOverride?: string, preCapture?: SelectionCapture) => {
      if (!editor || editor.isDestroyed || streamingRef.current) return;
      if (archived) {
        toast.error("已归档章节不可生成");
        return;
      }
      const base = docToProse(editor.getJSON());
      const cap = preCapture ?? captureNow();
      const pos = continuation ? (cap ? cap.end : base.length) : base.length;
      streamBaseRef.current = base;
      streamReceivedRef.current = "";
      streamingRef.current = true;
      setStreaming(true);
      onAIStateChange((prev) => ({ ...prev, streaming: true }));
      // 插入点归一：空文档先垫一个空段落（不入史）；否则落末段末尾/续写偏移
      const { state, view } = editor;
      if (state.doc.content.size === 0) {
        const para = state.schema.nodes.paragraph?.create();
        if (para) {
          const tr = state.tr.insert(0, para);
          tr.setMeta("addToHistory", false);
          view.dispatch(tr);
        }
        streamPosRef.current = 1; // 首段内
      } else if (continuation && cap) {
        streamPosRef.current = textOffsetToPmPos(state.doc, cap.end);
      } else {
        streamPosRef.current = state.doc.content.size - 1; // 末段内
      }
      streamStartRef.current = streamPosRef.current;
      const cbs = {
        onChunk: (t: string) => {
          streamReceivedRef.current += t;
          appendChunk(t);
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
    [projectId, chapterRef, archived, editor, captureNow, appendChunk, finishStream, onAIStateChange],
  );

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
      focus: () => editor?.commands.focus(),
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
    [editor, captureNow, startStream, finishStream, runTransform],
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
      {/* 查看态顶行（c-prose-edit-gate）：只读阅读＋「编辑正文」；
          归档/排队/旧稿锁各有横幅，锁定期不出现本行。
          条件渲染而非 hidden：.ol-top 是 display:flex，会压掉 hidden 属性（历史坑） */}
      {!hidden && !editable && !notEditable && (
        <div className="ol-top" data-od-id="prose-view-bar">
          <span className="note">
            正文 · {words ? `${words.toLocaleString("zh-CN")} 字` : "空章"}
          </span>
          <span className="push">
            <button
              className="btn btn-secondary"
              data-testid="prose-edit"
              onClick={onStartEdit}
            >
              编辑正文
            </button>
          </span>
        </div>
      )}
      <div className="editor-wrap" hidden={hidden} ref={wrapRef}>
        {/* TipTap 渲染 contenteditable 宿主：.editor 类经 editorProps.attributes 挂载，
            只读/归档/流式态由 setEditable(false) 落成 contenteditable="false"
            （a11y + e2e 判定口保持） */}
        <EditorContent editor={editor} />
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
              // 采纳替换走范围事务（c-prose-editor-tiptap）：选择区按 PM 位置替换为
              // 段落集合（可撤销单元）；编辑器失联时回落「拼接 + 整档同步」老路
              let next = capture.fullText.slice(0, capture.start) +
                text +
                capture.fullText.slice(capture.end);
              if (editor && !editor.isDestroyed) {
                const from = textOffsetToPmPos(editor.state.doc, capture.start);
                const to = textOffsetToPmPos(editor.state.doc, capture.end);
                editor
                  .chain()
                  .insertContentAt({ from, to }, linesToParagraphs(text), {
                    updateSelection: false,
                  })
                  .run();
                next = docToProse(editor.getJSON());
              }
              lastSyncedRef.current = next;
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
