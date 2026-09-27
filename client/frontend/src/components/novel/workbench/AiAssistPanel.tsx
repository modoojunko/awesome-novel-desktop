/** 右栏「AI 辅助」面板（c-ai-rail-shared：全局统一 ra-* 布局，与设定域 AiWriterAssistant 同构）。
 *  每页签＝一张 AI 助手卡：ra-head 头部（plan-badge＋标题＋状态副标题）＋ ai-target 作用域行
 *  ＋ ra-step 能力行（名称＋会读什么/落到哪＋箭头）＋ ra-foot 来源/去向声明。
 *  各页签内容不同，造型与门控全局一致；动作全部真链路（2026-09-17 起），
 *  AI 入口收口右栏（2026-09-20），布局统一设定模版（c-ai-rail-shared，2026-09-27）。
 *  注：建表动作（提取本章变化/识别角色与物品变化/登记新伏笔）走 onRunReconcile，
 *  检测动作（冲突检测/一致性/偏离/补边）走 onAiCheck，精修动作走 onPromptRefine。 */
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, request } from "@/lib/api";
import type { AiState } from "@/types/api-config";
import { toast } from "@/lib/toast";
import type { RefObject } from "react";
import type { ProseAIState, ProseHandle } from "./ProsePane";
import { chapterNoOf } from "@/lib/chapterRef";
import type { AiCheckKind, RefineMode } from "@/lib/aiCheck";
import { REQ_FIELDS } from "./chapterForm";
import AiWriterAssistant, { type AiCapabilityRow } from "@/components/novel/AiWriterAssistant";

export interface OgStats {
  /** 归档门槛已满足项（分母＝必填项数，见 REQ_FIELDS）；操作页签统计卡在用 */
  reqOk: number;
  /** 正文页签统计卡在用 */
  planWords: number | null;
  /** 展示位已上移中栏头部 meta 行（2026-09-27）；随数据通道保留 */
  plotCount: number;
  castCount: number;
  /** 还缺的必填项标签（原型 aiList('还缺'…)；「补全缺失字段」以它为输入） */
  missingLabels?: string[];
}

interface ChapterLite {
  id: string;
  ref: string;
  chapter: number;
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

export function AiAssistPanel({
  projectId,
  chapterRef,
  tab,
  isPro,
  ogStats,
  wordCount,
  planWords,
  archived,
  canAiDraft,
  aiDrafting,
  onAiDraft,
  onSimulate,
  onPlotDraw,
  onAiWrite,
  onContinue,
  onUpgrade,
  staleDownstream,
  aiState,
  proseRef,
  onAiSelection,
  onRunReconcile,
  onFillGaps,
  gapsLoading,
  onAiCheck,
  onPromptRefine,
  onStyleSuggest,
  promptSavedSignal,
}: {
  projectId: string;
  chapterRef: string;
  tab: string;
  isPro: boolean;
  ogStats: OgStats;
  wordCount: number;
  planWords: number | null;
  archived: boolean;
  canAiDraft: boolean;
  aiDrafting: boolean;
  onAiDraft: () => void;
  onSimulate: () => void;
  /** AI 帮写剧情（三版选一弹层；生成类归 PRO，免费态 locked 置灰＋升级出口） */
  onPlotDraw?: () => void;
  /** AI 生成正文（c-prose-write-entry：正文页签动作清单首项，走页面级解锁链 → AiModal） */
  onAiWrite?: () => void;
  /** 续写建议（正文页签；从光标处或选区末尾流式续写） */
  onContinue?: () => void;
  /** 升级 PRO（免费态统一升级出口） */
  onUpgrade?: () => void;
  /** chapter-rewrite：下游「基于旧设定」章计数（无数据时显示「—」） */
  staleDownstream?: number;
  /** 正文页签的选区动作通道（压缩啰嗦段落；润色/扩写沿用页内工具卡） */
  aiState?: ProseAIState;
  proseRef?: RefObject<ProseHandle | null>;
  onAiSelection?: (
    mode: "polish" | "expand" | "compress",
    capture: ReturnType<ProseHandle["captureNow"]>,
  ) => void;
  /** 按类触发本章收尾（设定/关系/伏笔三入口）；产出在「操作」页签待确认 */
  onRunReconcile?: (kind: "set_changes" | "relations" | "hooks") => void;
  /** 章纲缺项补全（AI 产物 patch 到章纲表单，由既有保存链落库） */
  onFillGaps?: () => void;
  gapsLoading?: boolean;
  /** 六类案头检查（就地弹窗；不落库） */
  onAiCheck?: (kind: AiCheckKind) => void;
  /** 提示词精修（提案制弹窗；采纳后走提示词保存链） */
  onPromptRefine?: (mode: RefineMode) => void;
  /** 文风「AI 建议本章调整」（触发 StyleShadowPane 拉取；结果在页签内逐项采纳） */
  onStyleSuggest?: () => void;
  /** 提示词落库信号（c-prompt-tab-retire）：弹窗润色/存稿后状态行刷新 */
  promptSavedSignal?: number;
}) {
  // 页签内轻量数据（与中栏页签同端点；只在对应页签激活时取）
  const [promptSrc, setPromptSrc] = useState<{ total: number; cast: number } | null>(null);
  /** 本章提示词是否已落库（c-prompt-tab-retire：正文页签状态行用） */
  const [hasPrompts, setHasPrompts] = useState<boolean | null>(null);
  const [styleStats, setStyleStats] = useState<{ rows: number; shadow: number } | null>(null);
  const [graphStats, setGraphStats] = useState<{ nodes: number; edges: number; here: number } | null>(null);
  const [hookStats, setHookStats] = useState<{
    total: number;
    open: number;
    plantHere: number;
    resolveHere: number;
  } | null>(null);
  const [loreStats, setLoreStats] = useState<{ here: number; until: number } | null>(null);

  const chapterNo = useMemo(() => {
    return chapterNoOf(chapterRef);
  }, [chapterRef]);

  useEffect(() => {
    let cancelled = false;
    if (tab === "prose") {
      // 提示词状态（c-prompt-tab-retire：页签退役后状态收编正文页签作用域行）
      request(`/novels/${projectId}/chapters/${chapterRef}/prompts`, { quiet: true })
        .then((files: unknown) => {
          if (!cancelled) setHasPrompts(Array.isArray(files) && files.length > 0);
        })
        .catch(() => {
          if (!cancelled) setHasPrompts(false);
        });
      api
        .get(`/novels/${projectId}/chapters/${chapterRef}/prompt-sources`)
        .then((d: { total_chars?: number; cast_count?: number }) => {
          if (!cancelled) setPromptSrc({ total: d.total_chars ?? 0, cast: d.cast_count ?? 0 });
        })
        .catch(() => {
          /* 统计失败静默 */
        });
    }
    if (tab === "style") {
      api
        .get(`/novels/${projectId}/chapters/${chapterRef}/style-shadow/baseline`)
        .then(
          (d: {
            baseline?: Array<{ value?: string }>;
            shadow?: Record<string, unknown>;
          }) => {
            if (!cancelled)
              setStyleStats({
                rows: (d.baseline ?? []).filter((b) => (b.value ?? "").trim()).length,
                shadow: Object.keys(d.shadow ?? {}).length,
              });
          },
        )
        .catch(() => {
          /* 静默 */
        });
    }
    if (tab === "relations") {
      api
        .get(`/novels/${projectId}/characters/graph`)
        .then(
          (d: {
            nodes?: Array<{ id?: string }>;
            edges?: Array<{ origin_chapter?: string | null }>;
          }) => {
            const edges = d.edges ?? [];
            if (!cancelled)
              setGraphStats({
                nodes: (d.nodes ?? []).length,
                edges: edges.length,
                here: edges.filter((e) => e.origin_chapter === chapterRef).length,
              });
          },
        )
        .catch(() => {
          /* 静默 */
        });
    }
    if (tab === "hooks") {
      Promise.all([
        api.get(`/novels/${projectId}/hooks`),
        api.get(`/novels/${projectId}/volumes`),
      ])
        .then(([hd, tree]) => {
          const items = (hd?.data?.items ?? []) as Array<{
            status?: string;
            introduced_chapter_id?: string | null;
            resolved_chapter_id?: string | null;
          }>;
          const lite: ChapterLite[] = [];
          for (const v of (tree ?? []) as Array<{
            name?: string;
            ref?: string;
            chapters?: Array<{ id?: string; chapter: number; ref?: string }>;
          }>) {
            for (const c of v.chapters ?? []) {
              lite.push({
                id: c.id ?? c.ref ?? "",
                ref: c.ref ?? `${v.name ?? v.ref}-ch-${c.chapter}`,
                chapter: c.chapter,
              });
            }
          }
          const cur = lite.find((c) => c.ref === chapterRef)?.id ?? null;
          if (!cancelled)
            setHookStats({
              total: items.length,
              open: items.filter((h) => h.status === "active").length,
              plantHere: items.filter((h) => h.introduced_chapter_id === cur).length,
              resolveHere: items.filter((h) => h.resolved_chapter_id === cur).length,
            });
        })
        .catch(() => {
          /* 静默 */
        });
    }
    if (tab === "settings") {
      Promise.all([
        api.get(`/novels/${projectId}/chapters/${chapterRef}`),
        api.get(`/novels/${projectId}/settings/world`),
      ])
        .then(([ch, world]) => {
          const cast = (ch?.outline?.characters ?? []) as Array<{ state_change?: string }>;
          const here = cast.filter((c) => (c.state_change ?? "").trim()).length;
          const entries = [
            ...((world?.factions ?? []) as Array<{ origin?: string }>),
            ...((world?.history ?? []) as Array<{ origin?: string }>),
            ...((world?.extra ?? []) as Array<{ origin?: string }>),
          ];
          const until = entries.filter((e) => {
            if (!e.origin) return true;
            const n = chapterNoOf(e.origin);
            return n ? n <= chapterNo : true;
          }).length;
          if (!cancelled) setLoreStats({ here, until });
        })
        .catch(() => {
          /* 静默 */
        });
    }
    return () => {
      cancelled = true;
    };
  }, [tab, projectId, chapterRef, chapterNo, promptSavedSignal]);

  const TITLE: Record<string, string> = {
    og: "章纲", prose: "正文", prompt: "提示词", settings: "设定",
    style: "文风", relations: "角色关系", hooks: "伏笔", actions: "操作",
  };

  /** 门控与设定域同源：PRO＝ready，免费＝member_required（点击走统一升级出口） */
  const state: AiState = isPro ? "ready" : "member_required";
  const handleBlocked = (reason: AiState) => {
    if (reason === "member_required") {
      onUpgrade?.();
      return;
    }
    toast.info(reason === "no_key" ? "先去「模型配置」添加 API Key" : "AI 暂不可用");
  };

  const cap = (
    key: string,
    name: string,
    desc: string,
    opts: {
      onClick?: () => void;
      disabled?: boolean;
      hint?: string;
      testid?: string;
    } = {},
  ): AiCapabilityRow => ({
    key,
    name,
    desc,
    onClick: opts.onClick ?? (() => {}),
    disabled: opts.disabled,
    hint: opts.hint,
    testid: opts.testid,
  });
  const sel = () => proseRef?.current?.captureNow() ?? null;

  let targetLine: ReactNode;
  let footNote: string;
  let running: string | null = null;
  let rows: AiCapabilityRow[] = [];

  if (tab === "og") {
    const missing = ogStats.missingLabels ?? [];
    running = aiDrafting ? "draft" : gapsLoading ? "fill" : null;
    targetLine = missing.length ? (
      <>还缺 {missing.length} 项：<b>{missing.join("、")}</b></>
    ) : (
      <>必填已齐 · 归档门槛 {ogStats.reqOk}/{REQ_FIELDS.length}</>
    );
    rows = [
      cap("simulate", "剧情推演 · 按回合走一遍", "先定走法再逐步推演；走法可收进本章剧情条目", {
        onClick: onSimulate, disabled: archived, hint: archived ? "本章已归档" : undefined, testid: "og-simulate",
      }),
      cap("draft", "AI 起草", "按卷纲与设定出整份章纲草稿，回填表单后由你确认落库", {
        onClick: onAiDraft,
        disabled: !canAiDraft || archived,
        hint: archived ? "本章已归档" : !canAiDraft ? "需 PRO" : undefined,
        testid: "og-ai-draft",
      }),
      cap("fill", "补全缺失字段", missing.length ? `只补还缺的 ${missing.length} 项，一稿回填` : "必填已齐，暂无可补", {
        onClick: () => onFillGaps?.(),
        disabled: !onFillGaps || gapsLoading || missing.length === 0,
      }),
      cap("plot-draw", "AI 帮写剧情", "一次给 3 版剧情挑一版；要求概要、挑战、章末落点已填（手写剧情全免费）", {
        onClick: onPlotDraw, disabled: archived, hint: archived ? "本章已归档" : undefined, testid: "og-plot-draw",
      }),
      cap("conflict", "与卷纲冲突检测", "拿本章章纲去对卷纲，报出冲突点", {
        onClick: () => onAiCheck?.("volume_conflict"),
      }),
    ];
    footNote = "章纲动作的结果都回填到中栏章纲表单，检查修改后落库（3 秒静默自动保存兜底）。";
  } else if (tab === "prose") {
    running =
      aiState?.polishLoading ? "polish"
      : aiState?.expandLoading ? "expand"
      : aiState?.compressLoading ? "compress"
      : null;
    const streaming = !!aiState?.streaming;
    const pct = planWords ? Math.min(100, Math.round((wordCount / planWords) * 100)) : null;
    targetLine = (
      <>
        正文字数 {fmt(wordCount)} 字{planWords ? <> · 计划字数 {fmt(planWords)} 字 · 完成度 {pct}%</> : null}
        {" · "}
        本章提示词{" "}
        {hasPrompts == null ? "…" : hasPrompts ? "已自定义" : "自动组装"}
        {promptSrc ? <> · 组装来源 {promptSrc.total.toLocaleString("zh-CN")} 字</> : null}
      </>
    );
    rows = [
      cap("write", "生成正文", "由设定＋章纲组装提示词，可编辑后流式写入正文末尾", {
        onClick: onAiWrite, disabled: streaming, hint: streaming ? "生成中" : undefined, testid: "ai-write-btn",
      }),
      cap("continue", "续写建议", "从光标处（或选区末尾）流式续写，保持风格与上下文一致", {
        onClick: onContinue, disabled: streaming,
      }),
      cap("polish", "段落润色", "选中段落出润色稿，对照预览后替换", {
        onClick: () => onAiSelection?.("polish", sel()),
        disabled: !aiState?.hasSelection || !!aiState?.polishLoading,
        hint: !aiState?.hasSelection ? "先在正文选中一段" : undefined,
      }),
      cap("expand", "场景扩写", "把选中的一句话场景扩展为完整段落，保持设定一致", {
        onClick: () => onAiSelection?.("expand", sel()),
        disabled: !aiState?.hasSelection || !!aiState?.expandLoading,
        hint: !aiState?.hasSelection ? "先在正文选中一段" : undefined,
      }),
      cap("compress", "压缩啰嗦段落", "压缩选中的段落，保留信息去掉重复", {
        onClick: () => onAiSelection?.("compress", sel()),
        disabled: !aiState?.hasSelection || !!aiState?.compressLoading,
        hint: !aiState?.hasSelection ? "先在正文选中一段" : undefined,
      }),
      // 精修两行随提示词页签退役收编（c-prompt-tab-retire：提案制弹窗，不依赖页签）
      cap("negative", "补全负向约束", "按本章内容补「不要写什么」一类硬约束（提案制，采纳才写回）", {
        onClick: () => onPromptRefine?.("negative"),
      }),
      cap("concise", "精简提示词", "在不丢信息的前提下收拢冗长表述（提案制，采纳才写回）", {
        onClick: () => onPromptRefine?.("concise"),
      }),
    ];
    footNote =
      "续写/润色/扩写/压缩作用于正文编辑器；润色与扩写先出对照预览，采纳才替换。提示词由「生成正文」弹窗查看/编辑，弹窗内可存为本章提示词。" ;
  } else if (tab === "settings") {
    targetLine = loreStats ? (
      <>本章变化 {loreStats.here} 条 · 截至本章条目 {loreStats.until} 条</>
    ) : (
      <>本章变化统计中…</>
    );
    rows = [
      cap("extract", "提取本章变化", "从本章正文提取设定变化，归档时并进全书那一套", {
        onClick: () => onRunReconcile?.("set_changes"),
        disabled: !archived, hint: archived ? undefined : "归档后可用",
      }),
    ];
    footNote = "从本章正文里提取本章变化，归档时并进全书那一套；回退后自动重算。";
  } else if (tab === "style") {
    targetLine = styleStats ? (
      <>全书基线 {styleStats.rows} 行 · 本章调整 {styleStats.shadow ? `${styleStats.shadow} 项` : "未调整"}</>
    ) : (
      <>全书基线统计中…</>
    );
    rows = [
      cap("style-suggest", "AI 建议本章调整", "按全书文风给本章差异建议，页签内逐项采纳", {
        onClick: () => onStyleSuggest?.(),
        disabled: !onStyleSuggest || archived,
        hint: archived ? "本章已归档" : undefined,
        testid: "style-suggest-btn",
      }),
      cap("style-check", "文风一致性检查", "对照全书文风基线查本章偏离", {
        onClick: () => onAiCheck?.("style_consistency"),
      }),
      cap("style-deviate", "标记偏离段落", "标出与基线不一致的段落", {
        onClick: () => onAiCheck?.("style_deviations"),
      }),
    ];
    footNote = "全书文风基线只读；本章只改这一章的差异项，不写回全书文风。";
  } else if (tab === "relations") {
    targetLine = graphStats ? (
      <>人物与势力 {graphStats.nodes} 个 · 关系边 {graphStats.edges} 条 · 本章变化 {graphStats.here} 条</>
    ) : (
      <>人物与势力统计中…</>
    );
    rows = [
      cap("rel-extract", "识别角色与物品变化", "从本章正文识别关系与物品变化（归档后可用）", {
        onClick: () => onRunReconcile?.("relations"),
        disabled: !archived, hint: archived ? undefined : "归档后可用",
      }),
      cap("rel-check", "关系冲突检测", "查本章关系与全书关系图的冲突", {
        onClick: () => onAiCheck?.("relations_conflict"),
      }),
      cap("rel-suggest", "建议补边", "按本章内容建议补上缺失的关系", {
        onClick: () => onAiCheck?.("relation_suggest"),
      }),
    ];
    footNote = "关系图是全书统一的一套；这一章可以在图上加新的关系，归档时并进全书。";
  } else if (tab === "hooks") {
    targetLine = hookStats ? (
      <>悬置 {hookStats.open} 条 · 本章埋下 {hookStats.plantHere} 条 · 本章回收 {hookStats.resolveHere} 条 · 台账 {hookStats.total} 条</>
    ) : (
      <>伏笔台账统计中…</>
    );
    rows = [
      cap("hooks-check", "伏笔冲突检测", "查本章伏笔与台账的冲突（重复埋、提前揭、漏收）", {
        onClick: () => onAiCheck?.("hooks_conflict"),
      }),
      cap("hooks-register", "登记新伏笔", "从本章正文登记新伏笔进台账（归档后可用）", {
        onClick: () => onRunReconcile?.("hooks"),
        disabled: !archived, hint: archived ? undefined : "归档后可用",
      }),
    ];
    footNote = `伏笔台账展示到第 ${chapterNo} 章为止：本章埋下与回收的条目会被标出，跨章悬置的继续挂着。`;
  } else {
    // 操作页签：只有作用域信息，无 AI 动作（重写/回退/归档是本页签的卡片按钮）
    running = null;
    targetLine = (
      <>当前状态 {archived ? "已归档" : wordCount > 0 ? "草稿" : "待写"} · 下游挂着旧设定{" "}
        {staleDownstream === undefined ? "—" : `${staleDownstream} 章`} · 正文 {fmt(wordCount)} 字</>
    );
    rows = [];
    footNote =
      "「生成本章变更摘要/下一章建议」不设入口：变更摘要＝归档摘要＋收尾提案，下一章建议＝下一章章纲的 AI 起草。";
  }

  return (
    <AiWriterAssistant
      title={`AI 助手 · ${TITLE[tab] ?? tab}`}
      aiState={state}
      onBlocked={handleBlocked}
      runningKey={running}
      targetLine={targetLine}
      footNote={footNote}
      rows={rows}
      data-od-id={`ai-assist-${tab}`}
    />
  );
}
