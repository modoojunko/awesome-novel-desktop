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
//   可整体撤销的历史单元；c-prose-regen-replace 后生成＝替换本章正文：
//   开始前旧正文整档清除（**不入撤销史**——清空不可撤销，⌘Z 确定性地回到
//   清空后的空稿，与生成快慢无关；旧正文找回路径＝版本历史），
//   chunk 仍按增量事务插入空文档（「整文档重建」禁令只约束流式过程）；
//   粘贴一律降级纯文本段落；选区捕获改走 PM 选区（SelectionCapture 形状不变）；
//   Enter 分段由 TipTap 核心键位（splitBlock）承担，execCommand 退役。
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { EditorContent, useEditor, useEditorState } from "@tiptap/react";
import { TextSelection } from "@tiptap/pm/state";
import type { Editor, JSONContent } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Placeholder } from "@tiptap/extensions";
import SeamWizard from "./seamWizard/SeamWizard";
import { useChapterData } from "@/hooks/useChapterData";
import { toast } from "@/lib/toast";
import {
  fetchEffectiveModel,
  streamChapterRefill,
  streamChapterWrite,
  type StreamDoneMeta,
} from "@/lib/ai";
import type { SelectionCapture } from "@/lib/selection";
import type { ModelSelection } from "@/types/api-config";
import {
  type FontSizePref,
  type LineHeightPref,
  getLastWriteSession,
  setLastWriteSession,
} from "@/lib/prefs";
import { docToProse, linesToParagraphs, proseToDoc, normalizeStreamedProse, proseDelta} from "./proseDoc";
import { RenweiMarks, applyRenweiMarks } from "./renweiMarks";
import RenweiCheckModal from "./RenweiCheckModal";
import RenweiMarginNotes from "./RenweiMarginNotes";
import { renweiCheck, type RenweiReport } from "@/lib/renwei";
import { ZhuqueMarks, applyZhuqueSegments } from "./zhuqueMarks";
import { fingerprint } from "@/lib/zhuqueFingerprint";
import { useZhuqueCheck } from "@/hooks/useZhuqueCheck";
import { getZhuqueShow, subscribeZhuqueShow } from "@/lib/prefs";

export interface ProseAIState {
  hasSelection: boolean;
  selectedText: string;
  continueLoading: boolean;
  streaming: boolean;
}

export const INITIAL_PROSE_AI_STATE: ProseAIState = {
  hasSelection: false,
  selectedText: "",
  continueLoading: false,
  streaming: false,
};

/** 首字前阶段文案（c-prose-gen-phases）：服务端 phase 事件 key → 作者语汇；
 *  未知 key 不渲染（旧后端不下发 phase 时停在首步文案，随后由首个片段直接接棒）。 */
const GEN_STAGE_LABELS: Record<string, string> = {
  assemble: "正在准备本章素材",
  prompt: "正在组装提示词",
  model: "模型思考中，等待首字",
};

export interface ProseHandle {
  focus(): void;
  captureNow(): SelectionCapture | null;
  /** promptOverride：AI 弹窗编辑后的提示词（空 = 后端自动组装）
   *  modelSelection：按次模型对（c-prose-model-select；未传 = 本书模型）
   *  写入语义＝替换本章正文（c-prose-regen-replace）：开始前清空现有正文，
   *  旧正文经「先 flush 后清空」进版本历史；入口层确认见 RegenConfirmModal */
  startWriting(prompt?: string, modelSelection?: ModelSelection): void;
  stopWriting(): void;
  /** 打开「人味检测」报告弹窗（c-renwei-check；入口在右栏检测区） */
  openRenweiCheck?: () => void;
  /** 打开「章际衔接修复向导」（c-seam-refill；入口同在右栏 AI 工具卡） */
  openSeamWizard?: () => void;
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
  /** 导入历史章：滚动不主动写 last_write（输入仍写），避免打开原文就把续写拽回历史章 */
  historical?: boolean;
  /** 查看/编辑两态（c-prose-edit-gate，对齐卷纲口径）：false＝只读阅读（默认），
   *  true＋非锁定＝可写。归档/排队/旧稿锁定 SHALL 优先于编辑态。 */
  editing?: boolean;
  /** 「编辑正文」入口回调（仅查看态且非锁定时出现） */
  onStartEdit?: () => void;
  /** 编辑态「完成」回调（回查看态；不回退内容，未保存修改照常自动保存） */
  onEndEdit?: () => void;
  /** 本章目标字数（章纲 wt→store.targetWords 兜底，ChapterWorkspace 传入）：
   *  文末续写块的达标判定（实写 < 90% 出块）；缺省＝无块（c-workbench-density） */
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

/** 外部载入/替换整文档——SHALL NOT 入撤销史。
 *  TipTap `setContent` 默认入史：开章后按「撤销/⌘Z」会把上一章内容（或空文档）
 *  写回本章并触发自动保存（数据破坏路径，e2e「无步时置灰」用例抓出）。
 *  preventUpdate=true 与 emitUpdate:false 同义（不触发 onUpdate）；光标回文首（旧契约）。 */
function replaceDocNoHistory(editor: Editor, doc: JSONContent) {
  const node = editor.schema.nodeFromJSON(doc);
  const tr = editor.state.tr.replaceWith(
    0,
    editor.state.doc.content.size,
    node.content ?? [],
  );
  tr.setSelection(TextSelection.atStart(tr.doc));
  tr.setMeta("addToHistory", false);
  tr.setMeta("preventUpdate", true);
  editor.view.dispatch(tr);
}

const ProsePane = forwardRef<ProseHandle, ProsePaneProps>(function ProsePane(
  { projectId, chapterRef, fs, lh, hidden, onAIStateChange, resumeScroll, onWriteProgress, historical, locked, editing, onStartEdit, onEndEdit },
  ref,
) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const paperRef = useRef<HTMLDivElement>(null);
  /* 纸边距实测（c-prose-paper）：边注/标小旗住在版心左侧的纸边距里，可用余量＝
     纸左侧内边距＝(纸宽−版心宽)/2。纸边距是 clamp 算出来的，CSS 里拿不到数值
     （同一个百分号在 padding 与 inset 上基准不同），这里实测一次写成变量，
     窄列塌到没有边距时打 data-gutter-tight，让边注整旗隐藏（段落底色仍在）。 */
  useLayoutEffect(() => {
    const paper = paperRef.current;
    if (!paper) return;
    const sync = () => {
      const ed = paper.querySelector<HTMLElement>(".editor");
      if (!ed) return;
      const gutter = Math.max(0, Math.round((paper.clientWidth - ed.clientWidth) / 2));
      paper.style.setProperty("--paper-gutter", `${gutter}px`);
      // 标小旗宽约 46px（-46px 偏移刚好停在版心左缘）：余量不够就整旗隐藏，
      // 别让小旗压到正文；段落底色（zq-warn/err、rw-mark）仍在，信息不丢
      paper.toggleAttribute("data-gutter-tight", gutter < 46);
    };
    sync();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(sync);
    ro.observe(paper);
    return () => ro.disconnect();
  }, [hidden, editing]);

  const store = useChapterData(projectId, chapterRef);
  const { prose, status, setProse } = store;
  const archived = status === "archived";
  const notEditable = archived || !!locked;
  // 查看/编辑两态（c-prose-edit-gate）：编辑态＋非锁定才可写；锁定语义优先
  const editable = !!editing && !notEditable;
  const [streaming, setStreaming] = useState(false);
  // 生成等待呈现（c-prose-gen-phases）：首字前的真实阶段（服务端 phase 事件驱动）；
  // 首字到达即退场；呼吸灯（.prose-body 的环）此时才亮起
  const [genStage, setGenStage] = useState<string | null>(null);
  // 等首字计时（c-prose-thinking-timeout 顺带）：开思考后首字可能要等上一阵，
  // 秒表随等待呈现同行——静默等 90s 判死与正常等待都有数；随 genStage 退场停表
  const [genSecs, setGenSecs] = useState(0);
  const genAwaiting = genStage !== null;
  // 等待秒数的 ref 镜像（c-thinking-display）：思考转场账目行要在回调里取
  // 「此刻已等秒数」——state 闭包值滞后一拍，ref 恒准
  const genSecsRef = useRef(0);
  useEffect(() => {
    if (!genAwaiting) return;
    const t = window.setInterval(() => {
      genSecsRef.current += 1;
      setGenSecs(genSecsRef.current);
    }, 1000);
    return () => window.clearInterval(t);
  }, [genAwaiting]);
  const sawFirstChunkRef = useRef(false);
  // 思考呈现四态（c-thinking-display）：思考面板（占位行让位）→收起条→回看→超时卡。
  // 思考内容全量留在 thinkBufRef（回看依赖全量），渲染按 ~100ms 节流合批；
  // 非文档口径与阶段呈现同款：不进正文、不计数、不保存、不送检
  const [thinkPanel, setThinkPanel] = useState(false);
  const [thinkText, setThinkText] = useState("");
  const thinkBufRef = useRef("");
  const thinkFlushRef = useRef<number | null>(null);
  const thinkBodyRef = useRef<HTMLDivElement | null>(null);
  const [thinkKept, setThinkKept] = useState<null | {
    text: string;
    thinkSecs: number;
    genSecs: number | null;
    proseChars: number | null;
  }>(null);
  const [thinkOpen, setThinkOpen] = useState(false);
  const [timeoutCard, setTimeoutCard] = useState(false);
  const [timeoutMsg, setTimeoutMsg] = useState("");
  const [thinkModel, setThinkModel] = useState("");
  const lastPromptRef = useRef<string | undefined>(undefined);
  const lastModelSelRef = useRef<ModelSelection | undefined>(undefined);
  // 模型名懒取守卫（评审 P2b）：闭包里的 thinkModel 恒为 startStream 时刻值，
  // 不加守卫＝每个思考增量都打一次 /ai-model
  const thinkModelFetchedRef = useRef(false);
  // 清空重写前旧稿（评审 P1）：判死/失败零产物时回填，正文保持原样
  const preStreamProseRef = useRef("");
  const clearThinkTimer = () => {
    if (thinkFlushRef.current != null) {
      window.clearTimeout(thinkFlushRef.current);
      thinkFlushRef.current = null;
    }
  };
  // 面板滚动锚定尾部：新增量到达即贴底（原型同款）
  useEffect(() => {
    const el = thinkBodyRef.current;
    if (el && thinkPanel) el.scrollTop = el.scrollHeight;
  }, [thinkText, thinkPanel]);

  // 本地输入回路标记：store.prose 变化若来自本地输入则跳过重渲（保光标）
  const lastSyncedRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // 补足落盘窗口防重入（c-shortfall-refill 评审二轮 P3）：flush 期间不立
  // streaming 守卫——旧区间 refs 会被换章 cleanup 的 finishStream 拿去误删
  const refillPendingRef = useRef(false);
  // 流式现场（插入点 / 起点 / 收尾定位用）
  const streamPosRef = useRef(0);
  // 流式增量镜像：已插入的「归一全量」长度（appendChunk 与后端归一同口径）
  const streamInsertedLenRef = useRef(0);
  const streamStartRef = useRef(0);
  const streamReceivedRef = useRef("");
  // 生成完工检查（三工序③：字数 + 叙事自查；提示性质，可关闭）
  const [qcReport, setQcReport] = useState<StreamDoneMeta | null>(null);
  // 续写会话轮数（c-shortfall-refill）：两轮封顶在 UI 收口，换章/整章生成即复位
  const [refillRounds, setRefillRounds] = useState(0);
  // 完工检查并入工具行（c-workbench-density）：胶囊点击展开叙事自查明细
  const [qcOpen, setQcOpen] = useState(false);

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
        // c-zhuque-ai-detect：朱雀段落标注（Decorations 覆盖层，不动文档）
        ZhuqueMarks,
        RenweiMarks,
      ],
      editable: false, // 由 editable effect 统一接管（两态＋锁定＋流式）
      editorProps: {
        attributes: {
          class: `editor ${fs} ${lh}`,
          "data-testid": "prose-editor",
          // 空章占位：Placeholder 扩展覆盖「一个空段落」，零段落空文档由 CSS :empty 兜底
          "data-placeholder": "从这一章开始写……",
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
            // 同 appendChunk：段落边界占 2 个位置
            cur += 2;
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

  // c-zhuque-ai-detect：标注注入＋失效链。
  // - 结果到达（ok）→ segments 注入 Decorations；idle/clear → 清除
  // - stale（hook 侧判定）→ 装饰置换灰变体
  // - 文档事务（tr.docChanged，含流式/整档替换/撤销——preventUpdate 不拦 transaction）
  //   → 按管道重算 live 指纹 → evaluateStale（live ≠ 送检 → 变灰＋结果条提示重检）
  const zq = useZhuqueCheck(projectId, chapterRef);
  // 显示开关响应式：关＝标注一并退场（开＝会话内缓存恢复）
  const zqShow = useSyncExternalStore(subscribeZhuqueShow, getZhuqueShow, getZhuqueShow);
  const { state: zqState, evaluateStale: zqEvaluateStale } = zq;
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    if (!zqShow) {
      applyZhuqueSegments(editor, null);
      return;
    }
    const st = zqState;
    if (st.status === "ok" && st.result) {
      applyZhuqueSegments(editor, st.result.segments, st.stale);
    } else if (st.status === "idle") {
      applyZhuqueSegments(editor, null);
    }
  }, [editor, zqShow, zqState]);
  // 载入一次性失效评估（c-zhuque-persist）：存档水合/重检完成后立刻按当前正文
  // 比对一次——实时编辑失效链只挂 docChanged 事务，进章恢复的存档无事务可蹭
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const st = zqState;
    if (st.status !== "ok" || !st.result || !st.checkedAt || st.stale) return;
    const live = docToProse(editor.getJSON());
    void fingerprint(live).then((h) => zqEvaluateStale(h));
  }, [editor, zqState, zqEvaluateStale]);
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const onTransaction = ({ transaction }: { transaction: { docChanged: boolean } }) => {
      if (!transaction.docChanged) return;
      const live = docToProse(editor.getJSON());
      void fingerprint(live).then((h) => zqEvaluateStale(h));
    };
    editor.on("transaction", onTransaction);
    return () => {
      editor.off("transaction", onTransaction);
    };
  }, [editor, zqEvaluateStale]);


  // 撤销/重做可用态（工具箱按钮置灰；useEditorState 订阅事务）
  const canUndoRedo = useEditorState({
    editor,
    selector: (snap) => ({
      canUndo: snap.editor ? snap.editor.can().undo() : false,
      canRedo: snap.editor ? snap.editor.can().redo() : false,
    }),
  });

  // ── 上次写作会话（行头归一「续写」）：输入写、滚动只在会话已是本章时更新 ──
  // 防止「只是打开/滚动导入书第 1 章」就把 last_write 记成第 1 章，续写被拽回历史章。
  const lastSaveTimeRef = useRef(0);
  const lastWriteRef = useRef(getLastWriteSession(projectId));
  useEffect(() => {
    lastWriteRef.current = getLastWriteSession(projectId);
  }, [projectId, chapterRef]);
  const saveProgress = useCallback(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const now = Date.now();
    if (now - lastSaveTimeRef.current < 1000) return;
    lastSaveTimeRef.current = now;
    const max = wrap.scrollHeight - wrap.clientHeight;
    const scroll = max > 4 ? Math.min(1, Math.max(0, wrap.scrollTop / max)) : 0;
    setLastWriteSession(projectId, chapterRef, scroll);
    lastWriteRef.current = { ref: chapterRef, scroll, ts: now };
    onWriteProgress?.({ ref: chapterRef, scroll, ts: now });
  }, [projectId, chapterRef, onWriteProgress]);
  // onUpdate 经 options 同步拿最新闭包；ref 兜底防首帧 TDZ
  const saveProgressRef = useRef(saveProgress);
  saveProgressRef.current = saveProgress;

  // ── 流式跟随滚动（fix/stream-autoscroll）──────────────────────────
  // 生成到页末自动跟着滚：只在视口距底部 ≤160px（用户本就贴着正文看）时贴底；
  // 用户上滚回看旧文时不抢滚动条，滚回底部自动恢复跟随。
  const followStream = useCallback(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const distance = wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight;
    if (distance < 160) wrap.scrollTop = wrap.scrollHeight;
  }, []);
  /** 把流式插入点滚进视口（生成开始时一次性定位） */
  const scrollInsertIntoView = useCallback(() => {
    const wrap = wrapRef.current;
    if (!wrap || !editor || editor.isDestroyed) return;
    try {
      const domAt = editor.view.domAtPos(streamPosRef.current);
      const el =
        domAt.node.nodeType === 1
          ? (domAt.node as HTMLElement)
          : domAt.node.parentElement;
      el?.scrollIntoView({ block: "center", behavior: "auto" });
    } catch {
      // 插入点越界（文档刚被清空等）忽略——首块到达后 followStream 自然贴底
    }
  }, [editor]);

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

  // 外部 prose 变化（加载/归档恢复/AI 完成落盘）→ 整文档替换；
  // 本地输入回路（指纹一致）与 IME 组合期跳过（组合结束补同步）。
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    if (lastSyncedRef.current === prose) return;
    if (editor.view.composing) {
      pendingProseRef.current = prose;
      return;
    }
    lastSyncedRef.current = prose;
    replaceDocNoHistory(editor, proseToDoc(prose));
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
      replaceDocNoHistory(editor, proseToDoc(pending));
    };
    dom.addEventListener("compositionend", onCompositionEnd);
    return () => dom.removeEventListener("compositionend", onCompositionEnd);
  }, [editor]);

  // 卸载/切章：照「停止」收尾（c-prose-stream-guard）——先断流，再把半截内容
  // 经 finishStream 并入正文并**立即落盘**（flush 自带 isDirty 门：无流时零开销），
  // SHALL NOT 静默丢弃。为何不等自动保存防抖：useChapterData 的 release 兜底
  // flush 按声明序先于本 cleanup 执行（那时还没脏），防抖定时器在 release 后
  // 成孤儿，1.5s 内关窗即丢——必须此处显式 flush。依赖仅 chapterRef：缓冲经
  // refs 取数，finishStream 捕获旧章 store——半截内容恰落旧章；编辑器 DOM
  // 同步有 isDestroyed 守卫，不依赖卸载顺序。finishStream 幂等，正常收尾的
  // 切章到此处 streamingRef 已 false，整段跳过。
  useEffect(() => {
    setQcReport(null);
    setRefillRounds(0);
    // 思考呈现是「本章的现场」：切章即清（c-thinking-display——回看保留以
    // 编辑会话为界，跨章不串场）
    thinkBufRef.current = "";
    clearThinkTimer();
    setThinkText("");
    setThinkPanel(false);
    setThinkKept(null);
    setThinkOpen(false);
    setTimeoutCard(false);
    setThinkModel("");
    return () => {
      abortRef.current?.abort();
      if (streamingRef.current) {
        finishStream(streamReceivedRef.current, false);
        void store.flush();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterRef]);

  // ── 选区跟踪（AI 动作需要选中段落） ─────────────────────────────────
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
    const onScroll = () => {
      // 历史章只在会话已经是本章时才更新；作者书保持原有「滚动也记 last_write」。
      if (!historical || lastWriteRef.current?.ref === chapterRef) saveProgress();
    };
    wrap.addEventListener("scroll", onScroll, { passive: true });
    return () => wrap.removeEventListener("scroll", onScroll);
  }, [saveProgress, chapterRef, historical]);

  // ── AI 流式写入（事务追加，SHALL NOT 整文档重建；不入撤销史） ──────────
  /** 追加一段生成文本到插入点（段内换行 = 拆新段）。 */
  const appendChunk = useCallback(
    (chunk: string) => {
      if (!editor || editor.isDestroyed || !chunk) return;
      const { state, view } = editor;
      const tr = state.tr;
      tr.setMeta("addToHistory", false);
      // 流式所见＝落库最终态：对已收全量做与后端生成出口同款归一（段间空行收敛）
      // 后取增量插入——done 重排与流式渲染逐字一致，不再出现「先空行后收敛」的跳变
      const full = normalizeStreamedProse(streamReceivedRef.current);
      const delta = proseDelta(full, streamInsertedLenRef.current);
      if (!delta) return;
      let cur = streamPosRef.current;
      const lines = delta.split("\n");
      lines.forEach((line, i) => {
        if (line) {
          tr.insertText(line, cur, cur);
          cur += line.length;
        }
        if (i < lines.length - 1) {
          tr.split(cur);
          // 段落边界占 2 个位置（本段闭合 +1、新段开启 +1）——只 +1 会让位置账本
          // 每拆一段滞后 1，split 切进上一段末字、碎片越积越多（实测复现）
          cur += 2;
        }
      });
      view.dispatch(tr);
      streamPosRef.current = cur;
      streamInsertedLenRef.current = full.length;
      followStream();
    },
    [editor],
  );

  const finishStream = useCallback(
    (
      fullText: string,
      ok: boolean,
      meta?: StreamDoneMeta,
      opts?: { refill?: boolean },
    ) => {
      if (!streamingRef.current) return; // 已收尾（停止后又 onDone 等）
      streamingRef.current = false;
      setStreaming(false);
      setGenStage(null); // 等待呈现随流式态一并复位
      setThinkPanel(false); // 思考面板退场（首字后由收起条接棒）
      clearThinkTimer();
      onAIStateChange((prev) => ({ ...prev, streaming: false }));
      // c-prose-regen-replace：生成＝替换语义，正文终态＝本次生成物
      // （开始前旧正文已清空；停止/中断保留已收到的半截）
      // c-shortfall-refill refill 模式：编辑器只插本次尾段（两步收尾不变），
      // prose/lastSynced 落服务端合并整章（done.full_text）；中断＝旧文+半截尾段
      const isRefill = opts?.refill === true;
      const tail = normalizeStreamedProse(streamReceivedRef.current);
      const generated = isRefill
        ? tail
        : normalizeStreamedProse(fullText || streamReceivedRef.current);
      // 早失败零产物（评审 P1）：守卫判死/开流即败——旧稿回填，正文保持原样
      // （有半截仍按半截，替换写语义不变）
      const restored =
        !isRefill && !ok && !streamReceivedRef.current ? preStreamProseRef.current : null;
      const next = isRefill
        ? ok
          ? normalizeStreamedProse(fullText) // 服务端合并整章（旧文仅去尾换行）
          : lastSyncedRef.current + (tail ? "\n" + tail.replace(/\n+$/, "") : "")
        : restored ?? generated;
      // 正常完成：收起条账目行补生成用时与正文字数（c-thinking-display ③）
      if (ok && !opts?.refill) {
        setThinkKept((k) =>
          k ? { ...k, genSecs: genSecsRef.current, proseChars: generated.length } : k,
        );
      }
      // 两步收尾（c-prose-editor-tiptap）：①删流式区间（不入史）②整段写回（入史）
      // ——一次撤销回到本次生成的写入起点（替换写＝清空后的空稿）
      if (editor && !editor.isDestroyed) {
        const start = streamStartRef.current;
        const end = streamPosRef.current;
        if (end > start) {
          const tr = editor.state.tr.delete(start, end);
          tr.setMeta("addToHistory", false);
          editor.view.dispatch(tr);
        }
        const writeBack = restored ?? generated;
        if (writeBack.trim()) {
          editor
            .chain()
            .insertContentAt(start, linesToParagraphs(writeBack), {
              updateSelection: false,
            })
            .run();
        }
      }
      lastSyncedRef.current = next;
      setProse(next);
      if (ok) {
        toast.success(isRefill ? "续写完成 · 已保存" : "AI 生成完成 · 已保存");
        if (meta && (meta.word_check || meta.self_check)) setQcReport(meta);
      }
    },
    [editor, setProse, onAIStateChange],
  );

  const startStream = useCallback(
    (promptOverride?: string, modelSelection?: ModelSelection) => {
      if (!editor || editor.isDestroyed || streamingRef.current) return;
      if (archived) {
        toast.error("已归档章节不可生成");
        return;
      }
      // c-prose-regen-replace：生成＝全量替换。①旧正文先 flush（版本快照前置，
      // 重写链同款——「从版本历史找回」的承诺以落库为前提）；②清空现有正文
      // （**不入撤销史**：清空不可撤销，⌘Z 恰回清空后的空稿——若入史，快生成
      // 会与收尾写回落进 history 分组窗并成一条，一次撤销直跳旧正文，慢生成
      // 却回空稿，撤销语义随生成快慢漂移，e2e 实测）；③从空文档流式写入。
      // 旧「base+generated 追加」语义随本 change 退役。
      void store.flush();
      setRefillRounds(0); // 整章生成重开补足预算（c-shortfall-refill）
      streamReceivedRef.current = "";
      streamInsertedLenRef.current = 0;
      streamingRef.current = true;
      sawFirstChunkRef.current = false;
      // 思考呈现复位（c-thinking-display）：新一轮生成从空白开始
      thinkBufRef.current = "";
      clearThinkTimer();
      setThinkText("");
      setThinkPanel(false);
      setThinkKept(null);
      setThinkOpen(false);
      setTimeoutCard(false);
      setThinkModel("");
      thinkModelFetchedRef.current = false;
      lastPromptRef.current = promptOverride;
      lastModelSelRef.current = modelSelection;
      // 判死/失败零产物时回填旧稿的底稿（评审 P1：清空重写下「正文保持原样」
      // 的兑现面——否则空稿会被自动保存覆盖）
      preStreamProseRef.current = lastSyncedRef.current ?? "";
      genSecsRef.current = 0; // 秒表 ref 与 state 同步归零（评审 P2a）
      setStreaming(true);
      // 请求在飞＝后端确在准备（服务端 phase 事件随后逐段推进等待呈现）
      setGenStage("assemble");
      setGenSecs(0);
      genSecsRef.current = 0; // 等首字计时从本次生成起点起算（阶段推进不重置）
      onAIStateChange((prev) => ({ ...prev, streaming: true }));
      const { view } = editor;
      if (editor.state.doc.content.size > 0) {
        // 流式标记已立：onUpdate 不回写 store，正文终态由 finishStream 落
        const clearTr = editor.state.tr.delete(
          0,
          editor.state.doc.content.size,
        );
        clearTr.setMeta("addToHistory", false);
        view.dispatch(clearTr);
      }
      // 插入点归一：空文档先垫一个空段落（不入史）；否则落末段末尾
      const { state } = editor;
      if (state.doc.content.size === 0) {
        const para = state.schema.nodes.paragraph?.create();
        if (para) {
          const tr = state.tr.insert(0, para);
          tr.setMeta("addToHistory", false);
          view.dispatch(tr);
        }
        streamPosRef.current = 1; // 首段内
      } else {
        streamPosRef.current = state.doc.content.size - 1; // 末段内
      }
      streamStartRef.current = streamPosRef.current;
      // 生成开始：先把插入点滚进视口（替换写＝文首起流，滚到底部见新内容）
      scrollInsertIntoView();
      const cbs = {
        onChunk: (t: string) => {
          if (!sawFirstChunkRef.current) {
            sawFirstChunkRef.current = true;
            setGenStage(null); // 首字到达：等待呈现退场、呼吸灯亮起
            // 思考面板收起为收起条（c-thinking-display ②）：转场保留可回看
            clearThinkTimer();
            setThinkPanel(false);
            if (thinkBufRef.current) {
              setThinkKept({
                text: thinkBufRef.current,
                thinkSecs: genSecsRef.current,
                genSecs: null,
                proseChars: null,
              });
            }
          }
          streamReceivedRef.current += t;
          appendChunk(t);
        },
        onDone: (full: string, meta?: StreamDoneMeta) => finishStream(full, true, meta),
        onError: (e: string, kind?: string) => {
          if (kind === "thinking_timeout") {
            // 超时终局（c-thinking-display ④）：超时卡替代 toast——正文保持
            // 原样、已到达思考保留可回看；顶条生成指示随 streaming 复位退场
            clearThinkTimer();
            setThinkPanel(false);
            setThinkKept(
              thinkBufRef.current
                ? { text: thinkBufRef.current, thinkSecs: genSecsRef.current, genSecs: null, proseChars: null }
                : null,
            );
            setTimeoutMsg(e);
            setTimeoutCard(true);
            finishStream(streamReceivedRef.current, false);
            return;
          }
          toast.error(e);
          finishStream(streamReceivedRef.current, false);
        },
        // c-prose-gen-phases：服务端真实阶段（assemble|prompt|model）；未知值不渲染
        onPhase: (phase: string) => {
          if (sawFirstChunkRef.current) return; // 首字后不再呈现阶段
          if (GEN_STAGE_LABELS[phase]) setGenStage(phase);
        },
        // 思考增量（c-thinking-display ①）：首字前到达即让位占位行；
        // ~100ms 节流合批渲染，全量留在 thinkBufRef（回看依赖全量）
        onThinking: (t: string) => {
          if (sawFirstChunkRef.current) return; // 首字后的思考增量不再呈现
          thinkBufRef.current += t;
          setThinkPanel(true);
          if (!thinkModel && !thinkModelFetchedRef.current) {
            thinkModelFetchedRef.current = true;
            // 按次模型（c-prose-model-select）：弹窗换过模型时，面板必须显示本次
            // 实际调用的模型——/ai-model 只是本书模型，此时取它必错
            const picked = lastModelSelRef.current?.model;
            if (picked) setThinkModel(picked);
            else void fetchEffectiveModel(projectId).then((m) => m && setThinkModel(m));
          }
          if (thinkFlushRef.current == null) {
            thinkFlushRef.current = window.setTimeout(() => {
              thinkFlushRef.current = null;
              setThinkText(thinkBufRef.current);
            }, 100);
          }
        },
      };
      abortRef.current = streamChapterWrite(
        projectId,
        chapterRef,
        cbs,
        promptOverride,
        modelSelection,
      );
    },
    [projectId, chapterRef, archived, editor, appendChunk, finishStream, scrollInsertIntoView, onAIStateChange, store],
  );

  /** 字数不足一键续写（c-shortfall-refill）：不删旧文、在文末开流式区间，
   *  产物 append（服务端合并落库，done.full_text＝整章）；停止/中断保留已收半截尾段。 */
  const startRefill = useCallback(async () => {
    if (
      !editor ||
      editor.isDestroyed ||
      streamingRef.current ||
      refillPendingRef.current || // flush 窗口内双击：上一击已占坑（评审三轮）
      archived
    ) {
      return;
    }
    if (editor.state.doc.content.size <= 1) {
      void startStream("", undefined); // 空章退化＝整章生成（后端 422 的 UI 侧兜前）
      return;
    }
    const refAtStart = chapterRef; // await 落盘期间可能已切章：闭包章号过期即放弃
    // 评审 P1（二轮收口）：refill 是链上唯一 read-modify-write（服务端读存稿→合并→
    // 落库），防抖窗口内的未落盘编辑必须先落盘。flush 落盘窗口不立 streaming 守卫
    // （二轮 P3：旧区间 refs 会被换章 cleanup 的 finishStream 拿去误删），防重入用
    // 独立 pending 标志；doSave 吞错（saveState:"failed"、flush 照常 resolve），
    // 失败检测靠 flush 后核 isDirty——宁可不补，绝不按旧稿合并。
    refillPendingRef.current = true;
    try {
      await store.flush();
    } catch {
      toast.error("正文还没保存成功，暂不能补足——请稍后重试");
      return;
    } finally {
      refillPendingRef.current = false;
    }
    if (
      chapterRef !== refAtStart ||
      !editor ||
      editor.isDestroyed ||
      streamingRef.current
    ) {
      // flush 窗口内切章/有动作在跑：静默放弃
      return;
    }
    if (store.isDirty) {
      toast.error("正文还没保存成功，暂不能补足——请稍后重试");
      return;
    }
    setRefillRounds((r) => r + 1);
    streamReceivedRef.current = "";
    streamInsertedLenRef.current = 0;
    sawFirstChunkRef.current = false;
    setGenStage("assemble");
    genSecsRef.current = 0;
      setGenSecs(0);
    const size = editor.state.doc.content.size;
    streamStartRef.current = size - 1; // 末段内起流；不删任何旧内容
    streamPosRef.current = size - 1;
    scrollInsertIntoView();
    const cbs = {
      onChunk: (t: string) => {
        if (!sawFirstChunkRef.current) {
          sawFirstChunkRef.current = true;
          setGenStage(null);
        }
        streamReceivedRef.current += t;
        appendChunk(t);
      },
      onDone: (full: string, meta?: StreamDoneMeta) =>
        finishStream(full, true, meta, { refill: true }),
      onError: (e: string) => {
        toast.error(e);
        finishStream(streamReceivedRef.current, false, undefined, {
          refill: true,
        });
      },
      onPhase: (phase: string) => {
        if (sawFirstChunkRef.current) return;
        if (GEN_STAGE_LABELS[phase]) setGenStage(phase);
      },
    };
    abortRef.current = streamChapterRefill(projectId, chapterRef, cbs);
  }, [
    projectId,
    chapterRef,
    archived,
    editor,
    appendChunk,
    finishStream,
    scrollInsertIntoView,
    startStream,
    onAIStateChange,
    store,
  ]);

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

  // c-renwei-check：人味检测（本地体检）。报告弹窗→「标记到正文」才上边注；
  // 段落标色走 TipTap decoration，边注走覆盖层（正文锁死，不占布局流）。
  const [renweiOpen, setRenweiOpen] = useState(false);
  const [renweiReport, setRenweiReport] = useState<RenweiReport | null>(null);
  const [renweiSettled, setRenweiSettled] = useState<Record<number, "done" | "skip">>({});
  const renweiFindings = renweiReport?.findings ?? [];
  // 需要标色的段落＝有 finding 且未处理的（0-based 非空段序）
  const renweiParas = Array.from(new Set(
    renweiFindings.filter((f) => !renweiSettled[f.para]).map((f) => f.para),
  )).sort((a, b) => a - b);
  const renweiParaTotal = new Set(renweiFindings.map((f) => f.para)).size;
  const renweiSettledCount = Object.keys(renweiSettled).length;

  // 人味标注注入：标记到正文后按「未处理 finding 段」上色；清空＝退场。
  // 与朱雀各用一套 storage/PluginKey（两路检测互不读写）。
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    applyRenweiMarks(editor, renweiParas.length ? renweiParas : null);
  }, [editor, renweiParas]);

  // 人味逐段重扫（c-renwei-check）：标记在场时，改完一段 → 700ms 后重算整章
  // （毫秒级、零额度）。通过与上一轮 findings 的 diff 精准消卡：该段变干净＝
  // 自动记「已改」，其余段沿用新结果；标注已清则不再重扫。
  const renweiRescanRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 监听器必须**稳定绑定**：store/report 每次渲染都可能换新对象，若进依赖数组，
  // 每次按键（触发重渲）都会 cleanup 并清掉 700ms 防抖定时器——实测「改完一段
  // 永远不重扫」。故只依赖 editor/章节身份，动态值走 ref。
  const renweiReportRef = useRef<RenweiReport | null>(null);
  renweiReportRef.current = renweiReport;
  const renweiStoreRef = useRef(store);
  renweiStoreRef.current = store;
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const onRenweiEdit = ({ transaction }: { transaction: { docChanged: boolean } }) => {
      if (!transaction.docChanged || !renweiReportRef.current) return;
      if (renweiRescanRef.current) clearTimeout(renweiRescanRef.current);
      renweiRescanRef.current = setTimeout(() => {
        const prevReport = renweiReportRef.current;
        if (!prevReport) return;
        // 先落盘再重扫：端点读盘正文，自动保存有 1.5s 防抖窗口——不 flush 会
        // 扫到旧稿（实测：改完一段重扫，结论仍按旧稿给出，卡片不动）。
        void renweiStoreRef.current
          .flush?.()
          .then(() => renweiCheck(projectId, chapterRef))
          .then((next) => {
            const prevParas = new Set(prevReport.findings.map((f) => f.para));
            const nextParas = new Set(next.findings.map((f) => f.para));
            const cleared = [...prevParas].filter((p) => !nextParas.has(p));
            if (cleared.length) {
              setRenweiSettled((prev) => {
                const merged = { ...prev };
                cleared.forEach((p) => { merged[p] = "done"; });
                return merged;
              });
              toast.success("这一段过关了——随手重查，不花额度");
            }
            setRenweiReport(next);
          })
          .catch(() => {
            /* 重扫失败不打扰：正文/标注保持，作家可手动重新检测 */
          });
      }, 700);
    };
    editor.on("transaction", onRenweiEdit);
    return () => {
      if (renweiRescanRef.current) clearTimeout(renweiRescanRef.current);
      editor.off("transaction", onRenweiEdit);
    };
  }, [editor, projectId, chapterRef]);

  // c-seam-refill：章际衔接修复向导（开闭态＋打开时开场快照＋锚文校验执行器）
  const [seamOpen, setSeamOpen] = useState(false);
  const [seamParaCount, setSeamParaCount] = useState(3);
  const [seamCurrentOpening, setSeamCurrentOpening] = useState("");
  const [seamSnapshotFolded, setSeamSnapshotFolded] = useState("");
  // 人味检测动作（c-renwei-check）：标记到正文 / 标为已改 / 跳过 / 清除
  const markRenweiToBody = useCallback((report: RenweiReport) => {
    setRenweiReport(report);
    setRenweiSettled({});
    setRenweiOpen(false);
    toast.info("已标记到正文——右边就是改稿提示，悬停看改法");
  }, []);
  const renweiDone = useCallback((para: number) => {
    setRenweiSettled((prev) => ({ ...prev, [para]: "done" }));
    toast.success("这段过关了——随手重查，不花额度");
  }, []);
  const renweiSkip = useCallback((para: number) => {
    setRenweiSettled((prev) => ({ ...prev, [para]: "skip" }));
    toast.info("已跳过——你的稿子你做主，这里不再提示");
  }, []);
  const clearRenwei = useCallback(() => {
    setRenweiReport(null);
    setRenweiSettled({});
  }, []);

  const openSeamWizard = useCallback(() => {
    if (!editor || editor.isDestroyed) return;
    const paras: string[] = [];
    editor.state.doc.forEach((node) => {
      const t = node.textContent;
      if (t.trim()) paras.push(t);
    });
    const count = Math.min(3, paras.length);
    if (count === 0) return;
    setSeamParaCount(count);
    setSeamCurrentOpening(paras.slice(0, count).join("\n"));
    setSeamSnapshotFolded(paras.slice(0, count).map((s) => s.replace(/\s/g, "")).join(""));
    setSeamOpen(true);
  }, [editor]);
  // 应用（c-seam-refill 终版）：锚文全等校验（漂移拒做）＋单事务替换＋flush
  const applySeamOpening = useCallback(
    (newText: string): boolean => {
      if (!editor || editor.isDestroyed) return false;
      const paras: Array<{ start: number; end: number; text: string }> = [];
      editor.state.doc.forEach((node, pos) => {
        const t = node.textContent;
        if (!t.trim()) return;
        paras.push({ start: pos + 1, end: pos + 1 + node.content.size, text: t });
      });
      if (paras.length < seamParaCount) return false;
      const folded = paras
        .slice(0, seamParaCount)
        .map((p) => p.text.replace(/\s/g, ""))
        .join("");
      if (folded !== seamSnapshotFolded) return false; // 正文已变动，锚文校验失败
      // 整节点删除（含段落边界）再同位插入——不留空段节点（旧法只删段内文本，
      // 会遗留 N 个空段＝正文里多出空行，违反单换行分段契约）
      const chain = editor.chain();
      chain.deleteRange({ from: paras[0].start - 1, to: paras[seamParaCount - 1].end + 1 });
      chain.insertContentAt(paras[0].start - 1, linesToParagraphs(newText));
      chain.run();
      const next = docToProse(editor.getJSON());
      lastSyncedRef.current = next;
      setProse(next);
      void store.flush?.(); // 应用即刻落盘（flush 自带 isDirty 门）：防 1.5s 防抖窗口内关页丢稿
      return true;
    },
    [editor, store, seamParaCount, seamSnapshotFolded, setProse],
  );
  useImperativeHandle(
    ref,
    () => ({
      focus: () => editor?.commands.focus("end"), // 落文末：进入写作的继续位置
      captureNow,
      startWriting: (prompt?: string, modelSelection?: ModelSelection) =>
        startStream(prompt, modelSelection),
      stopWriting: () => {
        // 中断 + 立即收尾（fetch abort 不回调 onDone/onError）
        abortRef.current?.abort();
        finishStream(streamReceivedRef.current, false);
      },
      openRenweiCheck: () => setRenweiOpen(true),
      openSeamWizard: () => openSeamWizard(),
    }),
    [editor, captureNow, startStream, finishStream, openSeamWizard],
  );

  const words = prose.replace(/\s/g, "").length;
  // 等待呈现 vs 呼吸灯（c-prose-gen-phases）：等待期＝无框行内、**不出现呼吸框**；
  // 首个正文片段到达＝等待期结束，呼吸灯在编辑体（工具行＋正文区整列）上亮起
  const awaiting = streaming && !!genStage;
  const ringOn = streaming && !genStage;
  const proseBodyClass = `prose-body${awaiting ? " awaiting" : ""}${ringOn ? " generating" : ""}`;

  return (
    <>
      {/* 密度重排（c-workbench-density）：完工检查自整条横幅收缩为编辑态工具行警示胶囊
          （点开展开叙事自查明细条）——qc 数据服务写作中的人，查看态不再渲染。
          testid qc-word/qc-self 迁入展开明细条保留（e2e 定位口径不变）；
          条件渲染而非 hidden：.ol-top 是 display:flex，会压掉 hidden 属性（历史坑） */}
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
      {/* 编辑体（c-prose-gen-phases）：呼吸灯环绕范围＝编辑工具行＋正文区整列，
          至底部状态条上沿；纯 box-shadow，不动版式（流式写作位置不变）。
          hidden 属性必须跟着页签走：.prose-body 是 display:flex，会压掉 hidden
          属性的历史坑同 .ol-top——非正文页签不得占位（回退：三页签切换仅隐藏） */}
      <div className={proseBodyClass} hidden={hidden}>
      {/* 查看态顶行（c-prose-edit-gate）：只读阅读＋「编辑正文」；
          归档/排队/旧稿锁各有横幅，锁定期不出现本行。
          条件渲染而非 hidden：.ol-top 是 display:flex，会压掉 hidden 属性（历史坑） */}
      {/* 编辑态工具箱顶条（c-prose-edit-affordance / c-prose-edit-toolbar）：
          编辑框上沿（与正文区连体）＝ 撤销/重做 ｜ 状态 · 写完自动保存 · 完成。
          格式按钮（加粗/斜体…）不做——纯文本存储下无法持久化。 */}
      {!hidden && editable && (
        <div className="ol-top edit-bar" data-od-id="prose-edit-bar">
          {/* 完工检查胶囊（c-workbench-density）：有 qc 结果才出现；点开叙事自查明细 */}
          {qcReport && (qcReport.word_check || qcReport.self_check) && (
            <button
              className="qc-pill"
              data-testid="qc-banner"
              onClick={() => setQcOpen((v) => !v)}
              title="完工检查 · 点击展开明细"
            >
              {qcReport.word_check?.below_limit ? (
                <>
                  ⚠ 字数未达标 · {qcReport.word_check.actual}/{qcReport.word_check.target} ·{" "}
                  <b>差 {Math.max(0, qcReport.word_check.target - qcReport.word_check.actual)} 字</b>
                </>
              ) : (
                <>✓ 字数达标{qcReport.word_check && <> · {qcReport.word_check.actual}/{qcReport.word_check.target}</>}</>
              )}
              {qcReport.self_check && (
                <> · 叙事自查 {qcReport.self_check.length > 0 ? `${qcReport.self_check.length} 处` : "0/7"}</>
              )}
            </button>
          )}
          {/* 字数不足出路（c-shortfall-refill）：below_limit 才现动作；两轮封顶
              后收口为「重新生成整章」（复用既有 startStream 替换语义与版本快照前置） */}
          {qcReport?.word_check?.below_limit && editable && !archived && (
            <span className="tool-seg">
              {refillRounds < 2 ? (
                <button
                  className="btn btn-secondary btn-sm"
                  data-testid="prose-refill"
                  disabled={streaming}
                  onClick={startRefill}
                  title="从末尾续写，补到本章下限（目标字的九成）"
                >
                  补足字数{refillRounds > 0 ? `（第 ${refillRounds + 1} 次）` : ""}
                </button>
              ) : (
                <button
                  className="btn btn-secondary btn-sm"
                  data-testid="prose-regen"
                  disabled={streaming}
                  onClick={() => startStream("", undefined)}
                  title="两轮补足仍未达标——整章重新生成"
                >
                  重新生成整章
                </button>
              )}
            </span>
          )}
          <span className="tool-seg">
            <button
              className="icon-btn"
              title="撤销"
              aria-label="撤销"
              data-testid="prose-undo"
              disabled={!canUndoRedo.canUndo}
              onClick={() => editor?.chain().focus().undo().run()}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M9 14L4 9l5-5" />
                <path d="M4 9h10a6 6 0 010 12h-3" />
              </svg>
            </button>
            <button
              className="icon-btn"
              title="重做"
              aria-label="重做"
              data-testid="prose-redo"
              disabled={!canUndoRedo.canRedo}
              onClick={() => editor?.chain().focus().redo().run()}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M15 14l5-5-5-5" />
                <path d="M20 9H10a6 6 0 000 12h3" />
              </svg>
            </button>
          </span>
          <span className="push">
            {renweiParaTotal > 0 && (
              <span
                className={`rw-fixchip${renweiSettledCount >= renweiParaTotal ? " done" : ""}`}
                data-testid="rw-chip"
              >
                人味改稿 {renweiSettledCount}/{renweiParaTotal}
              </span>
            )}
            <span className="note">正在编辑正文 · {words.toLocaleString("zh-CN")} 字</span>
            <span className="note">写完自动保存</span>
            <button
              className="btn btn-secondary btn-sm"
              data-testid="prose-done"
              onClick={onEndEdit}
            >
              完成
            </button>
          </span>
        </div>
      )}
      {/* 完工检查明细条（c-workbench-density）：胶囊展开时渲染在工具行下方 */}
      {!hidden && editable && qcOpen && qcReport && (qcReport.word_check || qcReport.self_check) && (
        <div className="qc-detail" data-testid="qc-detail">
          {qcReport.word_check && (
            <span data-testid="qc-word">
              {qcReport.word_check.below_limit ? (
                <>
                  <b>字数未达标</b>：目标约 {qcReport.word_check.target} 字 · 实写{" "}
                  {qcReport.word_check.actual} 字（低于目标 90%），可在章纲调低目标字数或手动补写。
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
            <span data-testid="qc-self">
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
            <span data-testid="qc-self">
              <b>叙事自查</b>：七条规则均未命中。
            </span>
          )}
        </div>
      )}
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
      <div
        className={`editor-wrap${editable ? " editing" : ""}${renweiParaTotal > 0 ? " rw-margin" : ""}`}
        hidden={hidden}
        ref={wrapRef}
      >
        {/* 纸（c-prose-paper）：正文列分三层——桌面（.editor-wrap 底色）／纸（本层）／
            写字范围（版心＋编辑态虚线框）。滚动容器仍是 .editor-wrap（wrapRef 不动），
            纸随内容长；生成等待行、思考面板族与正文一起进纸，人味边注留在纸外层
            （它按 .editor-wrap 做测量与定位，落在纸右侧边距上，不改既有锚定口径）。 */}
        <div className="prose-paper" ref={paperRef}>
          {/* 写字范围框（c-prose-paper）：仅编辑态可见的装饰层，四边由 inset 给出；
              pointer-events:none 不参与交互，阅读态整框 display:none */}
          <span className="prose-frame" aria-hidden="true" />
        {/* 生成等待呈现（c-prose-gen-phases）：首字前无框行内——与正文同字体同首行缩进，
            不进文档、不参与撤销/保存/字数；首字到达即退场（呼吸灯此刻在编辑体上亮起） */}
        {genStage && !thinkPanel && !hidden && (
          <div className="gen-line" data-testid="gen-line">
            <p className="gl-main">
              <span className="gl-text" key={genStage}>
                {GEN_STAGE_LABELS[genStage]}
              </span>
              {/* 等首字秒表（c-prose-thinking-timeout 顺带）：在 key 外＝不随阶段切换重放入场动画 */}
              <span className="gl-sec" data-testid="gen-line-sec">
                · {genSecs}s
              </span>
              <i className="gl-caret" aria-hidden="true" />
            </p>
            <p className="gl-note">通常要半分钟到一分钟；期间可点「停止」。</p>
          </div>
        )}
        {/* 思考面板（c-thinking-display ①）：占位行让位后的唯一等待面——
            模型名＋已思考秒数＋弱化全文（限高滚动锚尾、全量保留）＋非文档说明；
            宽度相对正文列、与思考文字量无关 */}
        {thinkPanel && !hidden && (
          <div className="tk-live" data-testid="think-panel" role="log" aria-live="polite">
            <div className="tk-live-head">
              <span className="tk-dot" aria-hidden="true" />
              <span className="tk-live-title">{thinkModel ? `${thinkModel} · 思考过程` : "思考过程"}</span>
              <span className="tk-live-meta">已思考 <b data-testid="think-secs">{genSecs}</b> 秒</span>
            </div>
            <div className="tk-live-body" ref={thinkBodyRef}>
              <p>{thinkText}</p>
            </div>
            <div className="tk-live-foot">思考内容由模型生成，帮助它打磨本章；只在这里可见，不会写进正文。</div>
          </div>
        )}
        {/* 思考收起条＋回看抽屉（c-thinking-display ②③）：首字后转场保留，
            账目行随完成补齐；编辑会话内常驻，阅读视图同样保留 */}
        {thinkKept && !thinkPanel && !timeoutCard && !hidden && (
          <div className="tk-anchor">
            <button
              type="button"
              className="tk-bar"
              data-testid="think-bar"
              aria-expanded={thinkOpen}
              onClick={() => setThinkOpen((v) => !v)}
            >
              <span className="tk-bar-check" aria-hidden="true">✓</span>
              <span>
                {thinkKept.proseChars != null
                  ? `已思考 ${thinkKept.thinkSecs} 秒 · 本章生成完毕`
                  : `思考完成 · ${thinkKept.thinkSecs} 秒，正文正在写入`}
              </span>
              <span className="tk-bar-more">{thinkOpen ? "收起" : "展开回看"}</span>
            </button>
            {thinkOpen && (
              <div className="tk-drawer" data-testid="think-drawer">
                <div className="tk-drawer-head">
                  思考回看
                  <span className="tk-drawer-meta">
                    思考 {thinkKept.thinkSecs} 秒
                    {thinkKept.genSecs != null ? ` · 生成 ${thinkKept.genSecs} 秒` : ""}
                    {thinkKept.proseChars != null ? ` · 正文 ${thinkKept.proseChars} 字` : ""}
                  </span>
                  <button type="button" className="tk-x" onClick={() => setThinkOpen(false)}>收起</button>
                </div>
                <div className="tk-drawer-body"><p>{thinkKept.text}</p></div>
                <div className="tk-drawer-foot">思考内容由模型生成，仅供写作参考，不会写进正文。</div>
              </div>
            )}
          </div>
        )}
        {/* 超时卡（c-thinking-display ④）：守卫判死的终局——正文保持原样、
            已到达思考保留可回看；服务端文案带实测秒数 */}
        {timeoutCard && !hidden && (
          <div className="tk-timeout" data-testid="think-timeout">
            <div className="tk-timeout-head">本次生成已停止</div>
            <p>{timeoutMsg}</p>
            {thinkKept?.text ? (
              <div className="tk-timeout-see">
                <span>已保留它的思考内容</span>
                <button type="button" data-testid="think-see" onClick={() => setThinkOpen((v) => !v)}>
                  {thinkOpen ? "收起" : "展开回看"}
                </button>
              </div>
            ) : null}
            {thinkOpen && thinkKept?.text ? (
              <div className="tk-drawer" data-testid="think-drawer">
                <div className="tk-drawer-body"><p>{thinkKept.text}</p></div>
              </div>
            ) : null}
            <div className="tk-timeout-actions">
              <button
                type="button"
                className="tk-btn-main"
                data-testid="think-regen"
                onClick={() => {
                  setTimeoutCard(false);
                  setThinkOpen(false);
                  startStream(lastPromptRef.current, lastModelSelRef.current);
                }}
              >
                重新生成
              </button>
              <button
                type="button"
                className="tk-btn-ghost"
                data-testid="think-dismiss"
                onClick={() => setTimeoutCard(false)}
              >
                知道了
              </button>
            </div>
          </div>
        )}
        {/* TipTap 渲染 contenteditable 宿主：.editor 类经 editorProps.attributes 挂载，
            只读/归档/流式态由 setEditable(false) 落成 contenteditable="false"
            （a11y + e2e 判定口保持） */}
        <EditorContent editor={editor} className="editor-host" />
        </div>
        {renweiParaTotal > 0 && (
          <RenweiMarginNotes
            editorEl={editor?.view.dom as HTMLElement | undefined ?? null}
            findings={renweiFindings}
            settled={renweiSettled}
            onDone={renweiDone}
            onSkip={renweiSkip}
          />
        )}
      </div>
      </div>

      {/* 人味检测（c-renwei-check）：四拍弹窗——说明/运行/结果/标记到正文 */}
      <RenweiCheckModal
        open={renweiOpen}
        projectId={projectId}
        chapterRef={chapterRef}
        onClose={() => setRenweiOpen(false)}
        onMarkToBody={markRenweiToBody}
        onClear={clearRenwei}
      />
      {/* 章际衔接修复向导（c-seam-refill）：入口同在右栏 AI 工具卡（openSeamWizard） */}
      <SeamWizard
        open={seamOpen}
        onClose={() => setSeamOpen(false)}
        projectId={projectId}
        chapterRef={chapterRef}
        paraCount={seamParaCount}
        currentOpening={seamCurrentOpening}
        snapshotFolded={seamSnapshotFolded}
        onApply={applySeamOpening}
      />
    </>
  );
});

export default ProsePane;
