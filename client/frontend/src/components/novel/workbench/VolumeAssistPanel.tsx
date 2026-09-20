/** 右栏「AI 辅助 · 卷」语境面板（volume-plan-ai 三态）：
 *  1) 选中卷＝验证面板（引导语＋「体检这一卷」＋三组报告；免费、只读、可重复）；
 *  2) 未选中 · 零卷（空书）＝「规划第一卷（AI）」入口＋「分卷依据 · 来自你的设定」；
 *  3) 未选中 · 有卷（写作默认页）＝「接着往下规划」（规划第N卷）＋「卷的验证」（各卷一行，
 *     卷号 · 名字 · 章数目标；点一行＝选中该卷并立刻体检）。
 *  原「卷选中态四页签统计卡」与「未选中态四格全书统计」由本 change 退役（workbench delta）。 */
import { useCallback, useEffect, useState } from "react";
import { volumePlanApi, type VolumeCheckResult } from "@/lib/volumePlanApi";
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

const STATUS_GLYPH: Record<string, string> = { ok: "✓", warn: "⚠", none: "—" };

/** 分卷依据 · 来自你的设定（空书态 5 行；缺口标出、不拦） */
function BasisCard({
  projectId,
  active,
  genreLabel,
}: {
  projectId: string;
  active: boolean;
  genreLabel: string;
}) {
  const [rows, setRows] = useState<Array<[string, string, boolean]>>([
    ["主线全景", "…", false],
    ["结局三问", "…", false],
    ["题材阶段", genreLabel || "待定（不拦）", !!genreLabel],
    ["主要角色", "…", false],
    ["目标篇幅", "未设（可不设）", false],
  ]);
  useEffect(() => {
    if (!active || !projectId) return;
    let alive = true;
    (async () => {
      try {
        const arc = (await apiFetchStoryArc(projectId)) ?? {};
        const full = String(arc.fullstory ?? "").trim();
        const e = arc.ending ?? {};
        const chars = await apiGetCharacters(projectId);
        if (alive) {
          setRows([
            ["主线全景", full ? "已填" : "缺口 · 先去设定补主线", !!full],
            ["结局三问", e.scene || e.hero || e.tone ? "已填" : "缺口 · 只作参照", !!(e.scene || e.hero || e.tone)],
            ["题材阶段", genreLabel || "待定（不拦）", !!genreLabel],
            ["主要角色", chars > 0 ? `${chars} 人` : "还没有角色卡（不拦）", chars > 0],
            ["目标篇幅", "按结局估——打开规划台看 AI 的估算", false],
          ]);
        }
      } catch {
        if (alive) setRows((rs) => rs.map(([k, , ])=> [k, "（读取失败，不拦）", false] as [string,string,boolean]));
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, active, genreLabel]);
  return (
    <details className="cfg">
      <summary>分卷依据 · 来自你的设定</summary>
      <ul className="pv-mat" data-testid="plan-basis">
        {rows.map(([k, v, ok]) => (
          <li key={k}>
            <span className="k">{k}</span>
            <span className={ok ? "v ok" : "v gap"}>{v}</span>
          </li>
        ))}
      </ul>
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

/** 选中卷＝验证面板（体检动作＋三组报告；免费、只读、不代笔） */
function VolumeVerifyPanel({
  projectId,
  data,
  autoCheckSeq,
}: {
  projectId: string;
  data: VolumeRailData;
  autoCheckSeq: number;
}) {
  const [checking, setChecking] = useState(false);
  const [report, setReport] = useState<VolumeCheckResult | null>(null);
  const [error, setError] = useState("");
  const volRef = `vol-${data.volume}`;

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
        <span>卷的验证</span>
      </div>
      <div className="rail-assist" data-testid="volume-verify-panel">
        <p className="ai-lead">
          这一卷的验证：对不对得上全书设定、接不接得上主线、跟已经写出来的部分有没有出入。只给判断，不代笔。
        </p>
        <button
          className="btn btn-secondary btn-sm"
          data-testid="volume-check-btn"
          disabled={checking}
          onClick={() => void runCheck()}
        >
          {checking ? "体检中…" : "体检这一卷"}
        </button>
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
            {report.report.map((g) => (
              <div className="pv-group" key={g.name}>
                <p className="pv-group-t">{g.name}</p>
                <ul>
                  {g.items.map((it, i) => (
                    <li key={i} className={`pv-item ${it.status}`}>
                      <span className="pv-glyph">{STATUS_GLYPH[it.status] ?? "—"}</span>
                      <span className="pv-text">
                        {it.text}
                        {it.evidence ? <em className="pv-ev">（{it.evidence}）</em> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
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
}: {
  projectId: string;
  data: VolumeRailData | null;
  idle: RailIdleData;
  genreLabel: string;
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
        <div className="pv-entry" data-testid="plan-entry-empty">
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
  const nextNo = vols.length + 1;
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
          <ul className="pv-vols" data-testid="volume-verify-list">
            {vols.map((v) => {
              const no = Number((v.name.match(/^vol-(\d+)$/) ?? [])[1] ?? 0);
              return (
                <li key={v.name}>
                  <button
                    className="pv-vol-row"
                    data-testid={`verify-vol-${no}`}
                    onClick={() => onSelectVolume(v.name)}
                  >
                    第{no}卷 · {v.title || "未命名"} ·{" "}
                    {v.chapter_target != null ? `${v.chapter_target} 章` : "不设章数"}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
      <p className="ai-foot">
        免费版：体检与建议只读；生成、改写与归档需 PRO。点一卷立刻体检，只读不拦。
      </p>
    </>
  );
}
