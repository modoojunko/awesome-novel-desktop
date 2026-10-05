// 右栏（book.html .col-ai）：c-ai-rail-shared 起三域（设定/卷/章）同一布局——
//   卷选中 → VolumeAssistPanel（验证报告/规划入口，内容随卷域定）
//   章选中 → AiAssistPanel（随章页签切换的 AI 助手卡，ra-* 全局统一布局）
// 右栏 SHALL 只承载 AI 相关功能（c-rail-ai-only）；AI 写入工具全部经 onAi* 走
// 页面级写入链（归档章动作置灰＋hint「恢复编辑后可用」，c-archived-readonly：
// 原「解除只读」解锁链已退役，小改走横幅「恢复编辑」、整体重写走「重写本章」）。
import type { RefObject } from "react";
import type { ProseAIState, ProseHandle } from "./ProsePane";
import { toast } from "@/lib/toast";
import { AiAssistPanel, type OgStats } from "./AiAssistPanel";
import {
  VolumeAssistPanel,
  type RailIdleData,
  type VolumeRailData,
} from "./VolumeAssistPanel";
import type { AiCheckKind } from "@/lib/aiCheck";
import { runReconcile } from "@/lib/reconcileApi";

export interface RailChapterData {
  wordCount: number;
  targetWords: number;
  setTargetWords: (n: number) => void;
  archived: boolean;
  bookWords: number;
  /** 中栏当前页签（storyline col-ai 口径：右栏 AI 辅助随页签切换） */
  tab?: string;
  /** 章纲页签统计（归档门槛/计划字数/关键事件/出场角色） */
  ogStats?: OgStats;
  /** 剧情推演（章纲页签动作） */
  onSimulate?: () => void;
  /** 剧情抽卡（章纲页签动作；三版选一弹层，生成类归 PRO） */
  onPlotDraw?: () => void;
  /** 盘点出场人物（章纲页签动作；免费只读盘点＋PRO 抽卡，c-character-intro） */
  onCastReview?: () => void;
  /** 空章（留存格与剧情条目全空）：盘点行禁用 hint「先写剧情再盘点」 */
  castEmpty?: boolean;
  /** 盘点/抽卡在途（行「生成中…」） */
  castBusy?: boolean;
  /** 当前章 ref（右栏辅助面板按章取数） */
  chapterRef?: string;
  /** chapter-rewrite：下游「基于旧设定」章计数（NovelWorkspace 由树计算注入） */
  staleDownstream?: number;
  /** 章纲缺项补全（AI 产物回填章纲表单） */
  onFillGaps?: () => void;
  gapsLoading?: boolean;
  /** 六类案头检查（就地弹窗） */
  onAiCheck?: (kind: AiCheckKind) => void;
  /** 文风「AI 建议本章调整」触发（StyleShadowPane 信号拉取；2026-09-20 入口收口右栏） */
  onStyleSuggest?: () => void;
  /** 提示词落库信号（c-prompt-tab-retire）：弹窗润色/存稿后右栏提示词状态行刷新 */
  promptSavedSignal?: number;
}

interface RailProps {
  mode: "volume" | "chapter";
  /** 书本 id（右栏 AI 辅助面板按书按章取数） */
  projectId: string;
  isPro: boolean;
  onUpgrade: () => void;
  proseRef: RefObject<ProseHandle | null>;
  aiState: ProseAIState;
  data?: RailChapterData;
  /** 卷选中态右栏语境（VolumeWorkspace 上抛；null=未选中卷，呈通用空态） */
  volumeData?: VolumeRailData | null;
  /** 未选中态统计（壳层给数：空书/刚落删除都走这态） */
  railIdle: RailIdleData;
  /** 卷域 AI（volume-plan-ai）：规划台入口与「卷的验证」点行回调 */
  genreLabel: string;
  onPlanVolume: (volNo: number) => void;
  /** 拆下一章（AI）——本卷章节页签 PRO 入口（c-chapter-plan-ai；c-split-to-chapters-tab 迁入） */
  onSplitAi: () => void;
  /** 右栏「去补卷纲」出口：中栏切回卷纲页签（c-split-to-chapters-tab） */
  onGoOutline: () => void;
  onSelectVolume: (ref: string) => void;
  /** 选中卷自动体检信号（点行选中时递增） */
  autoCheckSeq: number;
  /** AI 写入工具链入口（归档章先解锁；生成正文再经 AiModal 提示词预览） */
  onAiWrite: () => void;
  onAiSelection: (mode: "polish", capture: ReturnType<ProseHandle["captureNow"]>) => void;
}

export default function Rail({
  mode,
  projectId,
  isPro,
  onUpgrade,
  proseRef,
  aiState,
  data,
  volumeData,
  railIdle,
  genreLabel,
  onPlanVolume,
  onSplitAi,
  onGoOutline,
  onSelectVolume,
  autoCheckSeq,
  onAiWrite,
  onAiSelection,
}: RailProps) {
  if (mode === "volume") {
    // 卷语境右栏（volume-plan-ai 三态：验证面板 / 规划入口 / 接着往下规划＋卷的验证）
    return (
      <VolumeAssistPanel
        projectId={projectId}
        data={volumeData ?? null}
        idle={railIdle}
        genreLabel={genreLabel}
        onPlanVolume={onPlanVolume}
        onSelectVolume={onSelectVolume}
        autoCheckSeq={autoCheckSeq}
        onSplitAi={onSplitAi}
        onGoOutline={onGoOutline}
        isPro={isPro}
        onUpgrade={onUpgrade}
      />
    );
  }

  const d = data;
  const words = d?.wordCount ?? 0;

  return (
    <div>
      {d?.tab && d.ogStats && d.chapterRef && d.onSimulate && (
        <AiAssistPanel
          projectId={projectId}
          chapterRef={d.chapterRef}
          tab={d.tab}
          isPro={isPro}
          onAiWrite={onAiWrite}
          ogStats={d.ogStats}
          wordCount={words}
          planWords={d.ogStats.planWords ?? d.targetWords ?? null}
          archived={!!d.archived}
          onSimulate={d.onSimulate}
          onPlotDraw={d.onPlotDraw}
          onCastReview={d.onCastReview}
          castEmpty={d.castEmpty}
          castBusy={d.castBusy}
          onUpgrade={onUpgrade}
          staleDownstream={d.staleDownstream}
          aiState={aiState}
          proseRef={proseRef}
          onAiSelection={onAiSelection}
          onFillGaps={d.onFillGaps}
          gapsLoading={d.gapsLoading}
          onAiCheck={d.onAiCheck}
          onStyleSuggest={d.onStyleSuggest}
          promptSavedSignal={d.promptSavedSignal}
          onRunReconcile={(kind) => {
            const ref = d.chapterRef;
            if (!ref) return;
            void (async () => {
              try {
                const r = await runReconcile(projectId, ref, kind);
                if (r.started) {
                  toast.info("已开始收尾提取，产出在「伏笔」页签待确认");
                } else {
                  toast.info("本章已有收尾任务在跑，稍后到「伏笔」页签看产出");
                }
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "触发失败，请重试");
              }
            })();
          }}
        />
      )}
    </div>
  );
}
