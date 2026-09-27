/** 右栏「AI 辅助」面板（storyline.html col-ai 复刻，workbench-storyline-ai-panel）：
 *  随中栏页签切换——每页签一条引导语＋统计卡＋动作清单。
 *  2026-09-27 用户拍板：章纲页签统计卡（归档门槛/计划字数/剧情/出场角色）上移
 *  中栏头部 meta 行（ChapterWorkspace e-meta），右栏章纲页签只剩引导语＋还缺＋动作。
 *  动作清单已全部落地（2026-09-17）：占位机制退役——onClick 改为必填，各动作按门控禁用。
 *  2026-09-20 AI 入口收口右栏（用户拍板）：章页签 body 的 AI 按钮全部退役，
 *  起草/推演/建议调整等触发动作唯一化在此；结果呈现仍在对应页签（文风建议逐项采纳、
 *  推演弹窗、章纲回填表单）。
 *  2026-09-17 撤三个重复动作（ADJUSTMENTS #27 ⑫）：「重新组装提示词」＝提示词页签内
 *  AI 润色（组装＋落库同一动作，且粗组稿本就每次重算）；「本章关系变化检测」＝操作页签
 *  reconcile 关系收尾；「建议本章回收」＝reconcile 伏笔收尾的「收束」提案。
 *  注：建表动作（提取本章变化/识别角色与物品变化/登记新伏笔）走 onRunReconcile，
 *  检测动作（冲突检测/一致性/偏离/补边）走 onAiCheck，精修动作走 onPromptRefine。 */
import { useEffect, useMemo, useState } from "react";
import type { RefObject } from "react";
import { api } from "@/lib/api";
import { Ico, P } from "@/components/icons";
import type { ProseAIState, ProseHandle } from "./ProsePane";
import { chapterNoOf } from "@/lib/chapterRef";
import type { AiCheckKind, RefineMode } from "@/lib/aiCheck";
import { REQ_FIELDS } from "./chapterForm";

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

interface Act {
  label: string;
  /** 必填：占位机制已退役（每个动作都有真实链路；不可用经 disabled 表达） */
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
  /** e2e 稳定锚（入口收口右栏后沿用原 testid，如 og-ai-draft/og-simulate） */
  testid?: string;
}

function raStats(pairs: Array<[string, string]>) {
  return (
    <ul className="rail-stats">
      {pairs.map(([k, v]) => (
        <li key={k}>
          <span className="k">{k}</span>
          <span className="v num">{v}</span>
        </li>
      ))}
    </ul>
  );
}

function raList(title: string, items: string[], tone = "") {
  if (items.length === 0) return null;
  return (
    <div className={`rail-list${tone ? ` ${tone}` : ""}`}>
      <em>{title}</em>
      <ul>
        {items.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

function raActs(acts: Act[], locked: boolean) {
  return (
    <div className={`rail-acts${locked ? " rail-locked" : ""}`}>
      {acts.map((a) => (
        <button
          key={a.label}
          className="btn btn-secondary btn-sm"
          data-testid={a.testid}
          disabled={locked || a.disabled}
          onClick={a.onClick}
        >
          {a.busy ? `${a.label}…` : a.label}
        </button>
      ))}
    </div>
  );
}

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
  /** AI 生成正文（c-prose-write-entry：自右栏常驻工具卡收编进正文页签动作清单；
   *  点击走页面级解锁链 → AiModal，与原 ai-write-btn 同一链路） */
  onAiWrite?: () => void;
  /** 升级 PRO（免费态剧情卡升级出口） */
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
}) {
  // 页签内轻量数据（与中栏页签同端点；只在对应页签激活时取）
  const [promptSrc, setPromptSrc] = useState<{ total: number; cast: number } | null>(null);
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
    if (tab === "prompt") {
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
  }, [tab, projectId, chapterRef, chapterNo]);

  const locked = !isPro;

  if (tab === "og") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 章纲</p>
        <p className="rail-lead">按本卷卷纲检查、补全第 {chapterNo} 章的章纲；必填项决定这一章能否归档。</p>
        {/* 归档门槛/计划字数/剧情/出场角色统计卡已上移中栏头部 meta 行（2026-09-27） */}
        {raList("还缺", ogStats.missingLabels ?? [], "warn")}
        {raActs(
          [
            {
              label: "剧情推演 · 按回合走一遍",
              testid: "og-simulate",
              onClick: onSimulate,
              disabled: archived,
            },
            {
              label: aiDrafting ? "AI 起草中" : "AI 起草",
              testid: "og-ai-draft",
              onClick: onAiDraft,
              disabled: !canAiDraft || aiDrafting || archived,
              busy: aiDrafting,
            },
            {
              label: gapsLoading ? "补全中" : "补全缺失字段",
              onClick: () => onFillGaps?.(),
              disabled:
                !onFillGaps ||
                gapsLoading ||
                (ogStats.missingLabels ?? []).length === 0,
              busy: gapsLoading,
            },
            {
              label: "与卷纲冲突检测",
              onClick: () => onAiCheck?.("volume_conflict"),
            },
          ],
          locked,
        )}
        {/* 章内剧情（c-plot-split，原型 rail-plot 逐字）：生成类归 PRO；
            免费态 rail-locked 置灰禁点不隐藏，升级出口在包裹外（手写全档可用） */}
        {onPlotDraw && (
          <>
            <p className="ai-sec">剧情</p>
            <div className={locked ? "rail-locked" : undefined}>
              <div className="ai-tool" data-od-id="rail-plot">
                <div className="ai-feat-head">
                  <b>AI 帮写剧情</b>
                  <span className="ai-tag">
                    <Ico d={P.star} fill size={10} />
                    PRO
                  </span>
                </div>
                <p>
                  一次给 3
                  版剧情，挑一版填进去，之后随便改，填错了能撤销。这一章干什么、卡在哪、到哪收——这三样填齐了
                  AI 才有依据。
                </p>
                <button
                  className="btn btn-primary btn-sm"
                  data-od-id="btn-plot-draw"
                  data-testid="og-plot-draw"
                  disabled={archived || locked}
                  onClick={onPlotDraw}
                >
                  给我 3 版剧情
                </button>
              </div>
            </div>
            {locked && (
              <div data-testid="plot-upgrade-exit">
                <p className="f-hint" style={{ marginBottom: 8 }}>
                  AI 写剧情是 PRO 功能。剧情自己写全免费，随便加、随便改。
                </p>
                <button className="btn btn-secondary btn-sm" onClick={onUpgrade}>
                  升级 PRO
                </button>
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  if (tab === "prose") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 正文</p>
        <p className="rail-lead">贴着本章章纲与全书文风，续写、扩写或改写已有的正文。</p>
        {raStats([
          ["正文字数", `${wordCount.toLocaleString("zh-CN")} 字`],
          ["计划字数", planWords ? `${planWords.toLocaleString("zh-CN")} 字` : "未定"],
          [
            "完成度",
            planWords ? `${Math.min(100, Math.round((wordCount / planWords) * 100))}%` : "—",
          ],
          ["状态", archived ? "已归档" : wordCount > 0 ? "草稿" : "待写"],
        ])}
        {raActs(
          [
            {
              // 生成正文（c-prose-write-entry：自右栏常驻工具卡收编；解锁链/AiModal 不变）
              label: "生成正文",
              testid: "ai-write-btn",
              onClick: () => onAiWrite?.(),
              disabled: !onAiWrite || !!aiState?.streaming,
            },
            {
              label: aiState?.compressLoading ? "压缩中" : "压缩啰嗦段落",
              onClick: () =>
                onAiSelection?.("compress", proseRef?.current?.captureNow() ?? null),
              disabled: !aiState?.hasSelection || !!aiState?.compressLoading,
            },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "prompt") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 提示词</p>
        <p className="rail-lead">
          提示词由六处来源自动组装：全书设定、卷纲、本章章纲、全书文风（含本章调整）、截至上一章的伏笔进展、本章涉及的角色设定。
        </p>
        {raStats([
          ["组装来源", "6 处"],
          ["来源字数", promptSrc ? `${promptSrc.total.toLocaleString("zh-CN")} 字` : "—"],
          ["涉及角色", promptSrc ? `${promptSrc.cast} 人` : "—"],
        ])}
        {raActs(
          [
            {
              label: "补全负向约束",
              onClick: () => onPromptRefine?.("negative"),
            },
            {
              label: "精简提示词",
              onClick: () => onPromptRefine?.("concise"),
            },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "settings") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 设定</p>
        <p className="rail-lead">
          从本章正文里提取本章变化，归档时并进全书那一套；回退后自动重算。
        </p>
        {raStats([
          ["本章变化", loreStats ? `${loreStats.here} 条` : "—"],
          ["截至本章条目", loreStats ? `${loreStats.until} 条` : "—"],
          ["基于旧设定", "—"],
        ])}
        {raActs(
          [
            {
              label: "提取本章变化",
              onClick: () => onRunReconcile?.("set_changes"),
              disabled: !archived,
            },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "style") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 文风</p>
        <p className="rail-lead">
          全书文风基线只读；本章只改这一章的差异项，不写回全书文风。AI 建议在此生成、页签内逐项采纳。
        </p>
        {raStats([
          ["全书基线", styleStats ? `${styleStats.rows} 行` : "—"],
          ["本章调整", styleStats ? (styleStats.shadow ? `${styleStats.shadow} 项` : "未调整") : "—"],
          ["硬约束", "见基线"],
        ])}
        {raActs(
          [
            {
              label: "AI 建议本章调整",
              testid: "style-suggest-btn",
              onClick: () => onStyleSuggest?.(),
              disabled: !onStyleSuggest || archived,
            },
            {
              label: "文风一致性检查",
              onClick: () => onAiCheck?.("style_consistency"),
            },
            {
              label: "标记偏离段落",
              onClick: () => onAiCheck?.("style_deviations"),
            },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "relations") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 角色关系</p>
        <p className="rail-lead">关系图是全书统一的一套；这一章可以在图上加新的关系。</p>
        {raStats([
          ["人物与势力", graphStats ? `${graphStats.nodes} 个` : "—"],
          ["关系边", graphStats ? `${graphStats.edges} 条` : "—"],
          ["本章变化的关系", graphStats ? `${graphStats.here} 条` : "—"],
        ])}
        {raActs(
          [
            {
              label: "识别角色与物品变化",
              onClick: () => onRunReconcile?.("relations"),
              disabled: !archived,
            },
            {
              label: "关系冲突检测",
              onClick: () => onAiCheck?.("relations_conflict"),
            },
            {
              label: "建议补边",
              onClick: () => onAiCheck?.("relation_suggest"),
            },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "hooks") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 伏笔</p>
        <p className="rail-lead">
          伏笔台账展示到第 {chapterNo} 章为止：本章埋下与回收的条目会被标出，跨章悬置的继续挂着。
        </p>
        {raStats([
          ["悬置", hookStats ? `${hookStats.open} 条` : "—"],
          ["本章埋下", hookStats ? `${hookStats.plantHere} 条` : "—"],
          ["本章回收", hookStats ? `${hookStats.resolveHere} 条` : "—"],
          ["台账总数", hookStats ? `${hookStats.total} 条` : "—"],
        ])}
        {raActs(
          [
            {
              label: "伏笔冲突检测",
              onClick: () => onAiCheck?.("hooks_conflict"),
            },
            {
              label: "登记新伏笔",
              onClick: () => onRunReconcile?.("hooks"),
              disabled: !archived,
            },
          ],
          locked,
        )}
      </div>
    );
  }

  return (
    <div className="rail-assist" data-testid="rail-assist">
      <p className="ai-sec">AI 辅助 · 操作</p>
      <p className="rail-lead">
        重写、回退、归档都会改动主线与全书设定；归档后的写回提案在「操作」里逐条确认。
      </p>
      {raStats([
        ["归档门槛", `${ogStats.reqOk}/${REQ_FIELDS.length}`],
        ["当前状态", archived ? "已归档" : wordCount > 0 ? "草稿" : "待写"],
        [
          "下游挂着旧设定",
          staleDownstream === undefined ? "—" : `${staleDownstream} 章`,
        ],
        ["正文", `${wordCount.toLocaleString("zh-CN")} 字`],
      ])}
      {/* 「生成本章变更摘要/生成下一章建议」不设入口（2026-09-17 设计修正）：
          面板无结果显示区，且产出与既有消费面重复——变更摘要＝归档摘要＋收尾提案
          ＋设定页签「本章变化」；下一章建议＝下一章章纲的 AI 起草。 */}
    </div>
  );
}
