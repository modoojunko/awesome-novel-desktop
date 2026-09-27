// 右栏（book.html .col-ai 复刻）：
//   卷选中 → AI 辅助·卷语境（随卷页签切换引导语＋统计卡；VolumeAssistPanel，无占位卡）
//   章选中 → 纯 AI 助手（随页签切换的 AiAssistPanel＋AI 工具卡）
//   本章进度卡已退役（c-rail-ai-only 2026-09-27）：字数/完成度/本书总字数并入
//   中栏头部 e-meta 徽章行，右栏 SHALL 只承载 AI 相关功能。
// 免费态与原型逐像素一致；PRO 态把续写/润色/扩写升为真实工具卡
// （应用侧已有功能，换皮不减功能；原型标「规划中」——已登记 ADJUSTMENTS）。
// AI 写入工具全部经 onAi* 走页面级解锁链（归档章先弹「解除只读」，真 bug #1）。
import type { RefObject } from "react";
import type { ProseAIState, ProseHandle } from "./ProsePane";
import { toast } from "@/lib/toast";
import { AiAssistPanel, type OgStats } from "./AiAssistPanel";
import {
  VolumeAssistPanel,
  type RailIdleData,
  type VolumeRailData,
} from "./VolumeAssistPanel";
import type { AiCheckKind, RefineMode } from "@/lib/aiCheck";
import { runReconcile } from "@/lib/reconcileApi";

export interface RailChapterData {
  wordCount: number;
  targetWords: number;
  setTargetWords: (n: number) => void;
  archived: boolean;
  bookWords: number;
  /** 退出归档只读（解锁链确认后由页面调用） */
  unarchive: () => Promise<void>;
  /** 中栏当前页签（storyline col-ai 口径：右栏 AI 辅助随页签切换） */
  tab?: string;
  /** 章纲页签统计（归档门槛/计划字数/关键事件/出场角色） */
  ogStats?: OgStats;
  /** AI 起草（章纲页签动作；缺省=不可用） */
  canAiDraft?: boolean;
  aiDrafting?: boolean;
  onAiDraft?: () => void;
  /** 剧情推演（章纲页签动作） */
  onSimulate?: () => void;
  /** AI 帮写剧情（章纲页签动作；三版选一弹层，生成类归 PRO） */
  onPlotDraw?: () => void;
  /** 当前章 ref（右栏辅助面板按章取数） */
  chapterRef?: string;
  /** chapter-rewrite：下游「基于旧设定」章计数（NovelWorkspace 由树计算注入） */
  staleDownstream?: number;
  /** 章纲缺项补全（AI 产物回填章纲表单） */
  onFillGaps?: () => void;
  gapsLoading?: boolean;
  /** 六类案头检查（就地弹窗） */
  onAiCheck?: (kind: AiCheckKind) => void;
  /** 提示词精修（提案制弹窗） */
  onPromptRefine?: (mode: RefineMode) => void;
  /** 文风「AI 建议本章调整」触发（StyleShadowPane 信号拉取；2026-09-20 入口收口右栏） */
  onStyleSuggest?: () => void;
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
  /** 拆下一章（AI）——卷纲页签 PRO 入口（c-chapter-plan-ai） */
  onSplitAi: () => void;
  onSelectVolume: (ref: string) => void;
  /** 选中卷自动体检信号（点行选中时递增） */
  autoCheckSeq: number;
  /** AI 写入工具链入口（归档章先解锁；生成正文再经 AiModal 提示词预览） */
  onAiWrite: () => void;
  onAiContinue: () => void;
  onAiSelection: (mode: "polish" | "expand" | "compress", capture: ReturnType<ProseHandle["captureNow"]>) => void;
}

function ProStar({ size = 10 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" width={size} height={size}>
      <path d="M12 2l2.4 6.2L21 9l-5 4.4 1.6 6.6L12 16.6 6.4 20 8 13.4 3 9l6.6-.8z" />
    </svg>
  );
}

function LockedCard({
  text,
  onUpgrade,
}: {
  text: string;
  onUpgrade: () => void;
}) {
  return (
    <div className="ai-locked">
      <div className="lhead">
        <ProStar size={16} />
        <b>PRO 功能</b>
      </div>
      <p>{text}</p>
      <button className="btn btn-primary btn-sm" onClick={onUpgrade}>
        升级 PRO
      </button>
    </div>
  );
}

function PlannedFeat({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="ai-feat">
      <div className="ai-feat-head">
        <b>{title}</b>
        <span className="tag-plan">规划中</span>
      </div>
      <p>{desc}</p>
    </div>
  );
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
  onSelectVolume,
  autoCheckSeq,
  onAiWrite,
  onAiContinue,
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
        isPro={isPro}
        onUpgrade={onUpgrade}
      />
    );
  }

  const d = data;
  const words = d?.wordCount ?? 0;

  const TAB_NAME: Record<string, string> = {
    og: "章纲", prompt: "提示词", prose: "正文", settings: "设定",
    style: "文风", relations: "角色关系", hooks: "伏笔", actions: "操作",
  };
  return (
    <div>
      <div className="ai-head">
        <span className="ai-title">AI 助手</span>
        <span className="pill-pro">PRO</span>
      </div>
      <div className="ai-ctx">
        <em>当前页签</em>
        <span>{TAB_NAME[d?.tab ?? ""] ?? "—"}</span>
      </div>
      {!isPro && (
        <LockedCard
          text="解锁后可由「设定 + 章纲」生成正文；续写、润色等能力规划中。免费版创作流程不受影响。"
          onUpgrade={onUpgrade}
        />
      )}
      {/* 原型 #aiWriteTools：免费态保留可见、rail-locked 置灰（opacity .45 + 禁点） */}
      <div className={!isPro ? "rail-locked" : undefined}>
        <div className="ai-tool">
          <div className="ai-feat-head">
            <b>AI 生成正文</b>
            <span className="ai-tag">
              <ProStar />
              PRO
            </span>
          </div>
          <p>提示词由设定 + 章纲组装，可编辑后流式写入正文末尾。</p>
          <button
            className="btn btn-primary btn-sm"
            data-testid="ai-write-btn"
            disabled={aiState.streaming}
            onClick={onAiWrite}
          >
            生成正文
          </button>
        </div>
      </div>

      {isPro && d?.tab === "prose" && (
        <>
          <p className="ai-sec">AI 工具</p>
          <div>
            <div className="ai-tool">
              <div className="ai-feat-head">
                <b>续写建议</b>
                <span className="ai-tag">
                  <ProStar />
                  PRO
                </span>
              </div>
              <p>从光标处（或选区末尾）流式续写，保持风格与上下文一致。</p>
              <button
                className="btn btn-secondary btn-sm"
                disabled={aiState.streaming}
                onClick={onAiContinue}
              >
                续写
              </button>
            </div>
            <div className="ai-tool">
              <div className="ai-feat-head">
                <b>段落润色</b>
                <span className="ai-tag">
                  <ProStar />
                  PRO
                </span>
              </div>
              <p>选中段落后给出风格一致的润色版本，对照预览后替换。</p>
              <button
                className="btn btn-secondary btn-sm"
                disabled={!aiState.hasSelection || aiState.polishLoading}
                onClick={() => onAiSelection("polish", proseRef.current?.captureNow() ?? null)}
              >
                {aiState.polishLoading ? "润色中…" : "润色选段"}
              </button>
            </div>
            <div className="ai-tool">
              <div className="ai-feat-head">
                <b>场景扩写</b>
                <span className="ai-tag">
                  <ProStar />
                  PRO
                </span>
              </div>
              <p>把选中的一句话场景扩展为完整段落，保持设定一致。</p>
              <button
                className="btn btn-secondary btn-sm"
                disabled={!aiState.hasSelection || aiState.expandLoading}
                onClick={() => onAiSelection("expand", proseRef.current?.captureNow() ?? null)}
              >
                {aiState.expandLoading ? "扩写中…" : "扩写选段"}
              </button>
            </div>
          </div>
        </>
      )}

      {!isPro && d?.tab === "prose" && (
        <>
          <p className="ai-sec">规划中的能力</p>
          <div className="rail-locked">
            <PlannedFeat title="续写建议" desc="在光标处给出下句 / 下一段的续写建议。" />
            <PlannedFeat title="段落润色" desc="选中段落，提供风格一致的润色版本。" />
            <PlannedFeat title="场景扩写" desc="把一句话场景扩展为完整段落，保持设定一致。" />
          </div>
        </>
      )}

      {d?.tab && d.ogStats && d.chapterRef && d.onAiDraft && d.onSimulate && (
        <AiAssistPanel
          projectId={projectId}
          chapterRef={d.chapterRef}
          tab={d.tab}
          isPro={isPro}
          ogStats={d.ogStats}
          wordCount={words}
          planWords={d.ogStats.planWords ?? d.targetWords ?? null}
          archived={!!d.archived}
          canAiDraft={!!d.canAiDraft}
          aiDrafting={!!d.aiDrafting}
          onAiDraft={d.onAiDraft}
          onSimulate={d.onSimulate}
          onPlotDraw={d.onPlotDraw}
          onUpgrade={onUpgrade}
          staleDownstream={d.staleDownstream}
          aiState={aiState}
          proseRef={proseRef}
          onAiSelection={onAiSelection}
          onFillGaps={d.onFillGaps}
          gapsLoading={d.gapsLoading}
          onAiCheck={d.onAiCheck}
          onPromptRefine={d.onPromptRefine}
          onStyleSuggest={d.onStyleSuggest}
          onRunReconcile={(kind) => {
            const ref = d.chapterRef;
            if (!ref) return;
            void (async () => {
              try {
                const r = await runReconcile(projectId, ref, kind);
                if (r.started) {
                  toast.info("已开始收尾提取，产出在「操作」页签待确认");
                } else {
                  toast.info("本章已有收尾任务在跑，稍后到「操作」页签看产出");
                }
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "触发失败，请重试");
              }
            })();
          }}
        />
      )}

      {/* 本章进度卡已退役（c-rail-ai-only）：字数/完成度/本书总字数并入中栏头部
          e-meta 徽章行，目标字数改值走章纲「本章目标字数」格与本书偏好。 */}
    </div>
  );
}
