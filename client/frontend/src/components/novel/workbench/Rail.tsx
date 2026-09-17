// 右栏（book.html .col-ai 复刻）：
//   卷选中 → AI 辅助·大纲（免费 ai-locked 卡 + 规划中三卡）
//   章选中 → AI 辅助·本章 + 本章进度卡（大百分数/进度条/目标字数就地编辑）
// 免费态与原型逐像素一致；PRO 态把续写/润色/扩写升为真实工具卡
// （应用侧已有功能，换皮不减功能；原型标「规划中」——已登记 ADJUSTMENTS）。
// AI 写入工具全部经 onAi* 走页面级解锁链（归档章先弹「解除只读」，真 bug #1）。
import { useState, type RefObject } from "react";
import type { ProseAIState, ProseHandle } from "./ProsePane";
import { toast } from "@/lib/toast";
import { DEFAULT_TARGET } from "@/hooks/useChapterData";
import { AiAssistPanel, type OgStats } from "./AiAssistPanel";

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
  /** 当前章 ref（右栏辅助面板按章取数） */
  chapterRef?: string;
  /** chapter-rewrite：下游「基于旧设定」章计数（NovelWorkspace 由树计算注入） */
  staleDownstream?: number;
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
  /** AI 写入工具链入口（归档章先解锁；生成正文再经 AiModal 提示词预览） */
  onAiWrite: () => void;
  onAiContinue: () => void;
  onAiSelection: (mode: "polish" | "expand", capture: ReturnType<ProseHandle["captureNow"]>) => void;
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

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
  onAiWrite,
  onAiContinue,
  onAiSelection,
}: RailProps) {
  const [editingTarget, setEditingTarget] = useState(false);
  const [targetDraft, setTargetDraft] = useState("");

  if (mode === "volume") {
    return (
      <div>
        <p className="progress-head">AI 辅助 · 大纲</p>
        {!isPro && (
          <LockedCard
            text="大纲阶段的 AI 能力正在规划中。升级后由设定与已有卷纲辅助生成，免费版创作流程不受影响。"
            onUpgrade={onUpgrade}
          />
        )}
        <p className="ai-sec">规划中的能力</p>
        <div className={!isPro ? "rail-locked" : undefined}>
          <PlannedFeat title="卷纲生成" desc="基于设定与卷摘要，生成卷纲草稿，一键填入。" />
          <PlannedFeat title="矛盾检查" desc="扫描已确认章纲，标出人物状态与伏笔冲突。" />
          <PlannedFeat title="提示词预览" desc="当前章的生成提示词（由设定 + 章纲组装），与正文生成共用。" />
        </div>
      </div>
    );
  }

  const d = data;
  const words = d?.wordCount ?? 0;
  const target = d?.targetWords ?? DEFAULT_TARGET;
  const pct = Math.min(100, Math.round((words / target) * 100));

  const commitTarget = () => {
    setEditingTarget(false);
    const v = parseInt(targetDraft, 10);
    if (v > 0 && d) {
      d.setTargetWords(v);
      toast.success("目标字数已更新");
    }
  };

  return (
    <div>
      <p className="progress-head">AI 辅助 · 本章</p>
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
          staleDownstream={d.staleDownstream}
        />
      )}

      <p className="ai-sec">本章进度</p>
      <div className="pct">
        {pct}
        <span className="sub">%</span>
      </div>
      <div className="pbar">
        <i style={{ width: `${pct}%` }} />
      </div>
      <div className="target-row">
        <span>目标字数</span>
        <span>
          <button
            className="edit num"
            hidden={editingTarget}
            onClick={() => {
              setTargetDraft(String(target));
              setEditingTarget(true);
            }}
          >
            {fmt(target)}
          </button>
          <input
            className="num"
            hidden={!editingTarget}
            type="number"
            min={100}
            step={100}
            value={targetDraft}
            onChange={(e) => setTargetDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitTarget();
              else if (e.key === "Escape") setEditingTarget(false);
            }}
            onBlur={commitTarget}
            ref={(el) => {
              if (el) {
                el.focus();
                el.select();
              }
            }}
          />
        </span>
      </div>
      <p className="progress-note">
        {d?.archived ? (
          <>本章已归档 · 正文锁定。</>
        ) : words === 0 ? (
          <>写下第一段，开始本章。</>
        ) : pct >= 100 ? (
          <>已达成目标 · 可以归档本章了。</>
        ) : (
          <>
            再写 <b className="num">{fmt(Math.max(0, target - words))}</b> 字，完成本章目标。
          </>
        )}
      </p>
      {d?.archived && (
        <div className="arch-card">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="4" y="10" width="16" height="10" rx="2" />
            <path d="M8 10V7a4 4 0 018 0v3" />
          </svg>
          <span>本章已归档 · 只读查看</span>
        </div>
      )}
      <div className="mini-stat">
        <div className="row">
          <span>本书总字数</span>
          <b className="num">{fmt(d?.bookWords ?? 0)}</b>
        </div>
        <div className="row">
          <span>本章草稿</span>
          <b className="num">{fmt(words)}</b>
        </div>
        <div className="row">
          <span>目标达成</span>
          <b className="num">{pct}%</b>
        </div>
      </div>
    </div>
  );
}
