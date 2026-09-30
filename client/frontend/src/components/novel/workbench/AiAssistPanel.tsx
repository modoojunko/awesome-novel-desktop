/** 右栏「AI 辅助」面板（c-ai-rail-shared：全局统一 ra-* 布局，与设定域 AiWriterAssistant 同构）。
 *  每页签＝一张 AI 助手卡：ra-head 头部（plan-badge＋标题＋状态副标题）＋ ai-target 作用域行
 *  ＋ ra-step 能力行（名称＋会读什么/落到哪＋箭头）＋ ra-foot 来源/去向声明。
 *  各页签内容不同，造型与门控全局一致；动作全部真链路（2026-09-17 起），
 *  AI 入口收口右栏（2026-09-20），布局统一设定模版（c-ai-rail-shared，2026-09-27）。
 *  注：收尾触发只剩「登记新伏笔」走 onRunReconcile（c-chapter-dossier：设定/关系
 *  两入口退役——四域随归档提取进设定/角色关系页签），
 *  检测动作（冲突检测/一致性/偏离/补边）走 onAiCheck。 */
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, request } from "@/lib/api";
import { useFeature } from "@/hooks/useTier";
import { getZhuqueShow } from "@/lib/prefs";
import { runZhuqueCheck, useZhuqueCheck } from "@/hooks/useZhuqueCheck";
import type { AiState } from "@/types/api-config";
import { toast } from "@/lib/toast";
import type { RefObject } from "react";
import type { ProseAIState, ProseHandle } from "./ProsePane";
import { chapterNoOf } from "@/lib/chapterRef";
import type { AiCheckKind } from "@/lib/aiCheck";
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
  onCastReview,
  castEmpty,
  castBusy,
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
  /** 盘点出场人物（c-character-intro：免费只读盘点＋PRO 抽卡；行级门控只作用章纲页签） */
  onCastReview?: () => void;
  /** 空章（留存格与剧情条目全空）：盘点行禁用 hint「先写剧情再盘点」 */
  castEmpty?: boolean;
  /** 盘点/抽卡在途（railData 驱动「生成中…」） */
  castBusy?: boolean;
  /** AI 生成正文（c-prose-write-entry：正文页签动作清单首项，走页面级解锁链 → AiModal） */
  onAiWrite?: () => void;
  /** 续写建议（正文页签；从光标处或选区末尾流式续写） */
  onContinue?: () => void;
  /** 升级 PRO（免费态统一升级出口） */
  onUpgrade?: () => void;
  /** chapter-rewrite：下游「基于旧设定」章计数（无数据时显示「—」） */
  staleDownstream?: number;
  /** 正文页签的选区动作通道（压缩啰嗦段落；去AI味/扩写沿用页内工具卡） */
  aiState?: ProseAIState;
  proseRef?: RefObject<ProseHandle | null>;
  onAiSelection?: (
    mode: "polish" | "expand" | "compress",
    capture: ReturnType<ProseHandle["captureNow"]>,
  ) => void;
  /** 按类触发本章收尾（伏笔「登记新伏笔」入口）；产出在「伏笔」页签待确认 */
  onRunReconcile?: (kind: "hooks") => void;
  /** 章纲缺项补全（AI 产物 patch 到章纲表单，由既有保存链落库） */
  onFillGaps?: () => void;
  gapsLoading?: boolean;
  /** 六类案头检查（就地弹窗；不落库） */
  onAiCheck?: (kind: AiCheckKind) => void;
  /** 文风「AI 建议本章调整」（触发 StyleShadowPane 拉取；结果在页签内逐项采纳） */
  onStyleSuggest?: () => void;
  /** 提示词落库信号（c-prompt-tab-retire）：弹窗润色/存稿后状态行刷新 */
  promptSavedSignal?: number;
}) {
  // 页签内轻量数据（与中栏页签同端点；只在对应页签激活时取）
  const [promptSrc, setPromptSrc] = useState<{ total: number; cast: number; note?: string } | null>(null);
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
  // c-zhuque-ai-detect：检测行三事实（权益/Key 配置/显示开关）＋编排状态
  const aiDetect = useFeature("ai-detect");
  const [zqConfigured, setZqConfigured] = useState<boolean | null>(null);
  const [zqShow, setZqShowState] = useState(() => getZhuqueShow());
  const zq = useZhuqueCheck(projectId, chapterRef);

  const chapterNo = useMemo(() => {
    return chapterNoOf(chapterRef);
  }, [chapterRef]);

  useEffect(() => {
    let cancelled = false;
    if (tab === "prose") {
      // c-zhuque-ai-detect：朱雀 Key 配置状态（就绪/引导分流的事实源）
      request("/api/v1/zhuque/config", { quiet: true, apiBase: "" })
        .then((d: { configured?: boolean }) => setZqConfigured(!!d?.configured))
        .catch(() => setZqConfigured(false));
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
        .then(
          (
            d: {
              total_chars?: number;
              cast_count?: number;
              sources?: Array<{ key?: string; note?: string }>;
            },
          ) => {
            if (cancelled) return;
            // 故事状态缺口标注（c-chapter-dossier）：把「不采纳→下章静默缺状态」
            // 变成聚合行上的可见提示（「提示词」页签退役后的唯一 UI 承接面）
            const ss = (d.sources ?? []).find((x) => x.key === "story_state");
            setPromptSrc({
              total: d.total_chars ?? 0,
              cast: d.cast_count ?? 0,
              note: ss?.note || "",
            });
          },
        )
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
            data?: {
              nodes?: Array<{ id?: string }>;
              edges?: Array<{ origin_chapter?: string | null }>;
            };
          }) => {
            // 端点返回 {ok, data} 信封（与中栏关系图同源）；此前直读顶层恒 0
            const edges = d.data?.edges ?? [];
            if (!cancelled)
              setGraphStats({
                nodes: (d.data?.nodes ?? []).length,
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
          // 契约：状态变化在 outline.character_states（仅非空条目），不在 characters（string[]）
          const states = (ch?.outline?.character_states ?? []) as Array<{ state_change?: string }>;
          const here = states.filter((c) => (c.state_change ?? "").trim()).length;
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

  // c-zhuque-ai-detect：显示开关（prefs 单源）跨组件同步——配置页拨动经 CustomEvent 到达
  useEffect(() => {
    const onZqShow = () => setZqShowState(getZhuqueShow());
    window.addEventListener("zhuque-show-changed", onZqShow);
    window.addEventListener("storage", onZqShow);
    return () => {
      window.removeEventListener("zhuque-show-changed", onZqShow);
      window.removeEventListener("storage", onZqShow);
    };
  }, []);

  const TITLE: Record<string, string> = {
    og: "章纲", prose: "正文", prompt: "提示词", settings: "设定",
    style: "文风", relations: "角色关系", hooks: "伏笔", actions: "操作",
  };

  /** 门控与设定域同源：PRO＝ready，免费＝member_required（点击走统一升级出口）。
   *  c-character-intro 3.3：行级 PRO 映射只作用章纲页签——og 页签恒 ready（盘点行
   *  免费可点，其余行 ra-off＋「需 PRO」）；其余页签维持 member_required 整卡锁定。 */
  const state: AiState = isPro || tab === "og" ? "ready" : "member_required";
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
      odId?: string;
    } = {},
  ): AiCapabilityRow => ({
    key,
    name,
    desc,
    onClick: opts.onClick ?? (() => {}),
    disabled: opts.disabled,
    hint: opts.hint,
    testid: opts.testid,
    odId: opts.odId,
  });
  const sel = () => proseRef?.current?.captureNow() ?? null;

  let targetLine: ReactNode;
  let footNote: string;
  let running: string | null = null;
  let rows: AiCapabilityRow[] = [];

  if (tab === "og") {
    const missing = ogStats.missingLabels ?? [];
    running = aiDrafting ? "draft" : gapsLoading ? "fill" : castBusy ? "cast-review" : null;
    targetLine = missing.length ? (
      <>还缺 {missing.length} 项：<b>{missing.join("、")}</b></>
    ) : (
      <>必填已齐 · 归档门槛 {ogStats.reqOk}/{REQ_FIELDS.length}</>
    );
    // 行级 PRO 映射（c-character-intro 3.3）：只作用章纲页签——盘点行全档免费可点，
    // 其余五行免费态 ra-off＋「需 PRO」（照 VolumeAssistPanel 先例）；
    // 其余页签维持 member_required 整卡锁定，不因本 change 放行。
    const proRow = (disabledExtra: boolean, hintExtra?: string) => ({
      disabled: !isPro || disabledExtra,
      hint: !isPro ? "需 PRO" : hintExtra,
    });
    rows = [
      cap("simulate", "剧情推演 · 按回合走一遍", "先定走法再逐步推演；走法可收进本章剧情条目", {
        onClick: onSimulate, disabled: archived || !isPro, hint: archived ? "本章已归档" : !isPro ? "需 PRO" : undefined, testid: "og-simulate",
      }),
      cap("draft", "AI 起草", "按卷纲与设定出整份章纲草稿，回填表单后由你确认落库", {
        onClick: onAiDraft,
        disabled: !canAiDraft || archived || !isPro,
        hint: archived ? "本章已归档" : !isPro ? "需 PRO" : undefined,
        testid: "og-ai-draft",
      }),
      cap("fill", "补全缺失字段", missing.length ? `只补还缺的 ${missing.length} 项，一稿回填` : "必填已齐，暂无可补", {
        onClick: () => onFillGaps?.(),
        disabled: !onFillGaps || gapsLoading || missing.length === 0 || !isPro,
        hint: !isPro ? "需 PRO" : undefined,
      }),
      cap("plot-draw", "AI 帮写剧情", "一次给 3 版剧情挑一版；要求概要、挑战、章末落点已填（手写剧情全免费）", {
        onClick: onPlotDraw,
        disabled: archived || !isPro,
        hint: archived ? "本章已归档" : !isPro ? "需 PRO" : undefined,
        testid: "og-plot-draw",
      }),
      cap(
        "cast-review",
        "盘点出场人物",
        "逐段盘这一章缺不缺人；缺的人给三个方向抽卡（PRO）或你自己填，确认后写进角色表、本章出场角色与本卷出场清单",
        {
          onClick: () => onCastReview?.(),
          disabled: archived || castEmpty || !onCastReview,
          hint: archived ? "本章已归档" : castEmpty ? "先写剧情再盘点" : undefined,
          testid: "og-cast-review",
          odId: "rail-cast",
        },
      ),
      cap("conflict", "与卷纲冲突检测", "拿本章章纲去对卷纲，报出冲突点", {
        onClick: () => onAiCheck?.("volume_conflict"),
        ...proRow(false),
      }),
    ];
    footNote = isPro
      ? "章纲动作的结果都回填到中栏章纲表单，检查修改后落库（3 秒静默自动保存兜底）。"
      : "免费版：盘点只读、不代笔；标「需 PRO」的行升级后可用。盘点结果要写进章纲的，走你平时那套保存。";
  } else if (tab === "prose") {
    running =
      aiState?.polishLoading ? "polish"
      : aiState?.expandLoading ? "expand"
      : aiState?.compressLoading ? "compress"
      : zq.state.status === "running" ? "zhuque"
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
        {promptSrc?.note ? (
          <span className="ra-hint" data-testid="story-state-note">
            {" "}
            · 上一章变化{promptSrc.note === "上一章未归档" ? "未归档" : promptSrc.note}（见「设定」页签）
          </span>
        ) : null}
      </>
    );
    rows = [
      cap("write", "生成正文", "由设定＋章纲组装提示词，可编辑后流式写入正文末尾", {
        onClick: onAiWrite, disabled: streaming, hint: streaming ? "生成中" : undefined, testid: "ai-write-btn",
      }),
      cap("continue", "续写建议", "从光标处（或选区末尾）流式续写，保持风格与上下文一致", {
        onClick: onContinue, disabled: streaming,
      }),
      cap("polish", "去AI味", "选中段落去掉机器腔，对照预览后替换", {
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
    ];
    // c-zhuque-ai-detect：朱雀检测行（四态）
    // 非 MAX（快照无 ai-detect）→ maxlk 锁定（免费档整卡锁定承载；PRO 行级锁定），点击统一升级出口
    // MAX 未配 Key → guide 虚线引导跳「模型配置 → 朱雀」；MAX 已配 → 就绪/运行
    if (zqShow) {
      const configured = zqConfigured === true;
      const running = zq.state.status === "running";
      const maxlk = !aiDetect;
      const guide = aiDetect && !configured;
      const wordCountEmpty = wordCount === 0;
      rows.push({
        key: "zhuque",
        name: "朱雀 AI 检测 · 查AI味",
        desc: maxlk
          ? "MAX 会员权益 · 升级后整章送腾讯朱雀检测（需自备腾讯云 Key）"
          : guide
            ? wordCountEmpty
              ? "先写正文，再整章送腾讯朱雀测 AI 味；Key 在「模型配置 → 朱雀」配置"
              : "未配置 Key · 点击去「模型配置 → 朱雀」粘贴腾讯云 EdgeOne Key"
            : "整章送腾讯朱雀测 AI 味，结果与段落标注就地显示",
        badge: maxlk ? (
          <span className="pill pill-warn">MAX 专属</span>
        ) : (
          <span className="pill pill-accent">MAX 权益</span>
        ),
        variant: maxlk ? "maxlk" : guide ? "guide" : undefined,
        onClick: () => {
          if (maxlk) {
            onUpgrade?.();
            return;
          }
          if (guide) {
            window.location.hash = "#/config?tab=zhuque";
            return;
          }
          void runZhuqueCheck(projectId, chapterRef);
        },
        hint: guide ? undefined : undefined,
        testid: "rail-zhuque-check",
        odId: "rail-zhuque-check",
        runningHint: "检测中…",
        // 空正文：可点但后端 400「先写正文」——行内即给出预判提示
        disabled: !maxlk && !guide && wordCountEmpty,
      });
    }
    footNote =
      "续写/去AI味/扩写/压缩作用于正文编辑器；朱雀检测整章送检，结果在标题右侧的结果条里，段落标注打在正文行上。检测需在「模型配置 → 朱雀」配好 Key（MAX 会员权益）。";
  } else if (tab === "settings") {
    targetLine = loreStats ? (
      <>本章变化 {loreStats.here} 条 · 截至本章条目 {loreStats.until} 条</>
    ) : (
      <>本章变化统计中…</>
    );
    rows = [];
    footNote =
      "设定/关系/物品/认知变化随归档自动提取（全档可用），在「设定」「角色关系」页签逐条确认。";
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
      cap("rel-check", "关系冲突检测", "查本章关系与全书关系图的冲突", {
        onClick: () => onAiCheck?.("relations_conflict"),
      }),
      cap("rel-suggest", "建议补边", "按本章内容建议补上缺失的关系", {
        onClick: () => onAiCheck?.("relation_suggest"),
      }),
    ];
    footNote =
      "页签以关系图为主表达：剧情关系截至本章上图（本章边高亮、待确认虚线）；变化行在本页签确认，不写回全书设定。";
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
      // 免费态章纲页签：副行插槽＋统一升级出口（行级门控的升级口）
      subTitle={
        tab === "og" && !isPro ? "免费行可用 · 标「需 PRO」的行升级后解锁" : undefined
      }
    >
      {tab === "og" && !isPro && (
        <p className="none" data-testid="og-upgrade-exit">
          标「需 PRO」的行升级后可用{" "}
          <button className="btn btn-primary btn-sm" data-testid="og-upgrade-btn" onClick={onUpgrade}>
            升级 PRO
          </button>
        </p>
      )}
    </AiWriterAssistant>
  );
}
