/** 右栏「AI 辅助 · 卷」语境面板（volume-plan-ai 三态）：
 *  1) 选中卷＝验证面板（引导语＋「体检这一卷」＋三组报告；免费、只读、可重复；
 *     c-write-home-rail-anchor 起随卷页签重排：当前页签＝真实页签名、引导语换焦、
 *     组序按页签前置，卷纲页签另有「重新规划这一卷（AI）」）；
 *  2) 未选中 · 零卷（空书）＝「规划第一卷（AI）」入口＋「分卷依据 · 来自你的设定」；
 *  3) 未选中 · 有卷（写作默认页）＝「接着往下规划」（规划第N卷）＋「卷的验证」（各卷一行，
 *     卷号 · 名字 · 章数目标；点一行＝选中该卷并立刻体检）。
 *  原「卷选中态四页签统计卡」与「未选中态四格全书统计」由本 change 退役（workbench delta）。 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { volumePlanApi, type VolumeCheckResult } from "@/lib/volumePlanApi";
import { nextVolNo as nextVolumeNo } from "@/lib/chapterRef";
import type { VolumeRailData } from "./VolumeWorkspace";
import type { WorkbenchVolume } from "@/hooks/useWorkbench";

export type { VolumeRailData };

/** 壳层注入的「未选中」态数据（空书 / 有卷未选中两态共用） */
export interface RailIdleData {
  /** 已有卷（树单源；卷的验证卡逐行用） */
  volumes: Array<WorkbenchVolume>;
  /** 全书章节总数（判空书/落点口径同源） */
  chapters: number;
}

/** 分卷依据 · 来自你的设定（空书态；dep-row 台账，原型类名；缺口标出、不拦） */
function BasisCard({
  projectId,
  active,
  genreLabel,
}: {
  projectId: string;
  active: boolean;
  genreLabel: string;
}) {
  const [rows, setRows] = useState<
    Array<{ k: string; v: string; s: string; cls: string }>
  >([
    { k: "主线全景", v: "…", s: "读取中", cls: "muted" },
    { k: "结局三问", v: "…", s: "读取中", cls: "muted" },
    { k: "题材", v: genreLabel || "待定（不拦）", s: genreLabel ? "已定" : "待定", cls: genreLabel ? "" : "muted" },
    { k: "主要角色", v: "…", s: "读取中", cls: "muted" },
    { k: "目标篇幅", v: "未设（可不设）", s: "未设", cls: "muted" },
  ]);
  useEffect(() => {
    if (!active || !projectId) return;
    let alive = true;
    (async () => {
      try {
        const arc = (await apiFetchStoryArc(projectId)) ?? {};
        const full = String(arc.fullstory ?? "").trim();
        const e = arc.ending ?? {};
        const ending = [e.scene, e.hero, e.tone].filter(Boolean).join("｜");
        const chars = await apiGetCharacters(projectId);
        if (alive) {
          setRows([
            { k: "主线全景", v: full ? full.slice(0, 80) : "缺口——先去设定补主线", s: full ? "已填" : "缺口", cls: full ? "" : "warn" },
            { k: "结局三问", v: ending ? ending.slice(0, 60) : "缺口——只作参照，不拦拆卷", s: ending ? "已填" : "缺口", cls: ending ? "" : "warn" },
            { k: "题材", v: genreLabel || "待定（不拦）", s: genreLabel ? "已定" : "待定", cls: genreLabel ? "" : "muted" },
            { k: "主要角色", v: chars > 0 ? `${chars} 人` : "还没有角色卡（不拦）", s: chars > 0 ? "已登记" : "缺口", cls: chars > 0 ? "" : "muted" },
            { k: "目标篇幅", v: "未设（可不设）", s: "未设", cls: "muted" },
          ]);
        }
      } catch {
        if (alive)
          setRows((rs) => rs.map((r) => ({ ...r, v: "（读取失败，不拦）", s: "缺口", cls: "warn" })));
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, active, genreLabel]);
  return (
    <details className="cfgset rail-cfg" open>
      <summary>分卷依据 · 来自你的设定</summary>
      <div data-testid="plan-basis">
        {rows.map((r) => (
          <div className="dep-row" key={r.k}>
            <span className="dep-k">{r.k}</span>
            <span className="dep-v">{r.v}</span>
            <span className={`dep-s ${r.cls}`}>{r.s}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

/* 轻封装：便于组件测试打桩（api 模块级 import 会连带拖进测试环境） */
async function apiFetchStoryArc(projectId: string) {
  const { api } = await import("@/lib/api");
  return api.fetchStoryArc(projectId);
}
async function apiGetCharacters(projectId: string): Promise<number> {
  const { api } = await import("@/lib/api");
  const d = (await api.get(`/novels/${projectId}/characters`)) as {
    items?: unknown[];
  };
  return Array.isArray(d?.items) ? d.items.length : 0;
}

/** 卷页签 → 右栏语境（c-write-home-rail-anchor）：同一条「卷的验证」，随页签换视角与组序 */
const VOL_TAB_NAME: Record<string, string> = {
  outline: "卷纲",
  chapters: "本卷章节",
  rels: "角色关系",
  hooks: "伏笔",
};
const VOL_TAB_LEAD: Record<string, string> = {
  outline:
    "这一卷的走向与结构：进场接不接得上上一卷、卷末收不收得住、核心矛盾是不是主线在这一阶段的子集。只给判断，不代笔。",
  chapters:
    "本卷已写内容与卷纲的出入：实际写出来的是不是照卷纲走的。只给判断，不代笔。",
  rels: "本卷人物在全书口径下是否成立：有没有空转、有没有违背性格。只给判断，不代笔。",
  hooks: "本卷伏笔在全书口径上是否成立：有没有重复埋、提前揭、漏收。只给判断，不代笔。",
};
/** 报告组序：按页签把相关一组前置（组名与后端 `volume_check` 的分组同名同义） */
const VOL_TAB_ORDER: Record<string, string[]> = {
  outline: ["对主线", "对设定", "对已写内容"],
  chapters: ["对已写内容", "对主线", "对设定"],
  rels: ["对设定", "对主线", "对已写内容"],
  hooks: ["对设定", "对主线", "对已写内容"],
};
/** 组名归一：模型偶尔把组名写成「对主线（进场与收束）」这类变体——取规范前缀；
 *  认不出的组名原样保留（渲染时按模型原序追加在尾，一个都不丢）。 */
const GROUP_KEYS = ["对主线", "对设定", "对已写内容"];
const normGroupKey = (name: string): string => {
  const t = (name ?? "").trim();
  return GROUP_KEYS.find((k) => t.startsWith(k)) ?? t;
};

/** 选中卷＝验证面板（体检动作＋三组报告；免费、只读、不代笔。随卷页签重排） */
function VolumeVerifyPanel({
  projectId,
  data,
  autoCheckSeq,
  onPlanVolume,
  onSplitAi,
  isPro,
  onUpgrade,
}: {
  projectId: string;
  data: VolumeRailData;
  autoCheckSeq: number;
  /** 卷纲页签的「重新规划这一卷（AI）」：打开规划台，卷号＝本卷 */
  onPlanVolume: (volNo: number) => void;
  /** 卷纲页签的「拆下一章（AI）」（c-chapter-plan-ai） */
  onSplitAi: () => void;
  isPro: boolean;
  onUpgrade: () => void;
}) {
  const [checking, setChecking] = useState(false);
  const [report, setReport] = useState<VolumeCheckResult | null>(null);
  const [error, setError] = useState("");
  const volRef = `vol-${data.volume}`;
  const tab = data.tab;
  // 主线末端门禁（c-chapter-plan-ai，与中栏「拆下一章」同判据）
  const frontierVol = data.frontierVol;
  const splitBlocked = frontierVol != null && data.volume < frontierVol;
  /** 组序按页签重排（不重跑、不改写结论）。逐实例消费（splice）：模型输出重名组时
   *  一组都不吞；顺序表之外/认不出的组名按模型原序追加在尾。 */
  const groups = useMemo(() => {
    if (!report || report.degraded) return [];
    const order = (VOL_TAB_ORDER[tab] ?? VOL_TAB_ORDER.outline).map(normGroupKey);
    const rest = [...report.report];
    const out: VolumeCheckResult["report"] = [];
    for (const key of order) {
      const i = rest.findIndex((g) => normGroupKey(g.name) === key);
      if (i >= 0) out.push(...rest.splice(i, 1));
    }
    return [...out, ...rest];
  }, [report, tab]);

  const runCheck = useCallback(async () => {
    setChecking(true);
    setError("");
    try {
      const d = await volumePlanApi.check(projectId, volRef);
      setReport(d);
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message || "体检失败，请重试";
      setError(
        msg.includes("模型")
          ? "先在模型配置里接一个模型，再回来体检"
          : msg,
      );
    } finally {
      setChecking(false);
    }
  }, [projectId, volRef]);

  // 「卷的验证」点行 → 选中即立刻体检（autoCheckSeq 变化触发）
  useEffect(() => {
    if (autoCheckSeq > 0) void runCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoCheckSeq, volRef]);

  return (
    <div>
      <div className="ai-head">
        <span className="ai-title">AI 助手</span>
        <span className="pill-pro">PRO</span>
      </div>
      <div className="ai-ctx">
        <em>当前页签</em>
        <span data-testid="volume-rail-tab">{VOL_TAB_NAME[tab] ?? "卷纲"}</span>
      </div>
      <div className="rail-assist" data-testid="volume-verify-panel">
        <p className="ai-lead" data-testid="volume-rail-lead">
          {VOL_TAB_LEAD[tab] ??
            "这一卷的验证：对不对得上全书设定、接不接得上主线、跟已经写出来的部分有没有出入。只给判断，不代笔。"}
        </p>
        <button
          className="btn btn-secondary btn-sm"
          data-testid="volume-check-btn"
          disabled={checking}
          onClick={() => void runCheck()}
        >
          {checking ? "体检中…" : "体检这一卷"}
        </button>
        {tab === "outline" && (
          <button
            className="btn btn-secondary btn-sm"
            data-testid="volume-replan"
            title="打开规划台，卷号＝本卷；采纳后仍逐段落进卷纲表单，保存才落库"
            onClick={() => onPlanVolume(data.volume)}
          >
            重新规划这一卷（AI）
          </button>
        )}
        {tab === "outline" && (
          <button
            className="btn btn-primary btn-sm"
            data-testid="volume-split-ai"
            disabled={!isPro || splitBlocked}
            title={
              splitBlocked
                ? `写作位在第${frontierVol}卷——新章要排在写作位所在卷及其之后`
                : undefined
            }
            onClick={() => (isPro && !splitBlocked ? onSplitAi() : isPro ? undefined : onUpgrade())}
          >
            拆下一章（AI）
          </button>
        )}
        {tab === "outline" && !isPro && (
          <p className="none" data-testid="volume-split-ai-locked">
            AI 三方向需 PRO——「自己写这一章」在中栏卷纲页随时可用
          </p>
        )}
        {tab === "outline" && splitBlocked && (
          <p className="none" data-testid="volume-split-ai-blocked">
            写作位在第{frontierVol}卷——先去那一卷拆章
          </p>
        )}
        {error && (
          <p className="pv-error" data-testid="volume-check-error">
            {error}
          </p>
        )}
        {report?.degraded && (
          <div className="pv-degraded" data-testid="volume-check-degraded">
            <p className="pv-degraded-t">体检输出没法结构化</p>
            <p className="pv-degraded-x">{report.text}</p>
            <p className="none">{report.hint || "可重试"}</p>
          </div>
        )}
        {report && !report.degraded && (
          <div data-testid="volume-check-report">
            {groups.map((g, gi) => (
              <div key={`${g.name}#${gi}`}>
                <p className="rp-k">{g.name}</p>
                <ul className="rp-list">
                  {g.items.map((it, i) => (
                    <li key={i} className={`rp-row ${it.status}`}>
                      <span className="rp-dot" aria-hidden="true" />
                      <span className="rp-tx">
                        {it.text}
                        {it.evidence ? <em className="rp-ev">（{it.evidence}）</em> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <p className="ai-note" style={{ marginTop: 10 }}>
              只读 · 不拦；你是最后确认的人。
            </p>
          </div>
        )}
      </div>
      <p className="ai-foot">
        免费版：体检与建议只读；生成、改写与归档需 PRO。体检随时可重复，不会改动任何内容。
      </p>
    </div>
  );
}

export function VolumeAssistPanel({
  projectId,
  data,
  idle,
  genreLabel,
  onPlanVolume,
  onSelectVolume,
  autoCheckSeq,
  onSplitAi,
  isPro,
  onUpgrade,
}: {
  projectId: string;
  data: VolumeRailData | null;
  idle: RailIdleData;
  genreLabel: string;
  /** 「拆下一章（AI）」——逐章拆分的 PRO 入口（c-chapter-plan-ai） */
  onSplitAi: () => void;
  isPro: boolean;
  onUpgrade: () => void;
  /** 打开规划台（空书＝1；写作默认页＝最大卷号+1） */
  onPlanVolume: (volNo: number) => void;
  /** 「卷的验证」点行：选中该卷（外层会立刻触发体检） */
  onSelectVolume: (ref: string) => void;
  /** 选中卷自动体检信号（点行选中时递增） */
  autoCheckSeq: number;
}) {
  const idleActive = !data || !data.detail;
  if (!idleActive) {
    return (
      <VolumeVerifyPanel
        key={`${data.volume}`}
        projectId={projectId}
        data={data}
        autoCheckSeq={autoCheckSeq}
        onPlanVolume={onPlanVolume}
        onSplitAi={onSplitAi}
        isPro={isPro}
        onUpgrade={onUpgrade}
      />
    );
  }

  const vols = idle.volumes;
  // 空书（0 卷）：规划第一卷入口＋分卷依据
  if (vols.length === 0) {
    return (
      <>
        <div className="ai-head">
          <span className="ai-title">AI 助手</span>
          <span className="pill-pro">PRO</span>
        </div>
        <div className="ai-ctx">
          <em>当前页签</em>
          <span>未选</span>
        </div>
        <div className="pv-entry plan-acts" data-testid="plan-entry-empty">
          <p className="ai-lead">
            让 AI 按你的主线拆分卷：先给第一卷定走向，再逐卷往下规划。也可以自己动手——先建一卷、排上第一章。
          </p>
          <button
            className="btn btn-primary btn-sm"
            data-testid="plan-first-volume"
            onClick={() => onPlanVolume(1)}
          >
            规划第一卷（AI）
          </button>
          <BasisCard projectId={projectId} active genreLabel={genreLabel} />
        </div>
        <p className="ai-foot">
          免费版：体检与建议只读；生成、改写与归档需 PRO。规划台里材料与规则随时可看，输入也能先写。
        </p>
      </>
    );
  }

  // 有卷未选中（写作默认页）：接着往下规划＋卷的验证
  const nextNo = nextVolumeNo(vols); // 最大卷号+1（与后端 MAX+1 同口径，见 chapterRef.nextVolNo）
  return (
    <>
      <div className="ai-head">
        <span className="ai-title">AI 助手</span>
        <span className="pill-pro">PRO</span>
      </div>
      <div className="ai-ctx">
        <em>当前页签</em>
        <span>未选</span>
      </div>
      <div className="pv-entry" data-testid="plan-entry-next">
        <p className="ai-lead">接着往下规划，或挑一卷做验证。</p>
        <button
          className="btn btn-primary btn-sm"
          data-testid="plan-next-volume"
          onClick={() => onPlanVolume(nextNo)}
        >
          规划第{nextNo}卷（AI）
        </button>
        <div className="cfg">
          <p className="pv-group-t">卷的验证</p>
          <div className="ledger" data-testid="volume-verify-list">
            {vols.map((v) => {
              const no = Number((v.name.match(/^vol-(\d+)$/) ?? [])[1] ?? 0);
              return (
                <button
                  className="lrow chrow"
                  data-testid={`verify-vol-${no}`}
                  key={v.name}
                  onClick={() => onSelectVolume(v.name)}
                >
                  <span className="lname">
                    第{no}卷 · {v.title || "未命名"}
                    <em>{v.chapter_target != null ? `${v.chapter_target} 章目标` : "未设章数"}</em>
                  </span>
                  <span className="lstate">体检 →</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <p className="ai-foot">
        免费版：体检与建议只读；生成、改写与归档需 PRO。点一卷立刻体检，只读不拦。
      </p>
    </>
  );
}
