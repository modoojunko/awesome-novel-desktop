/** 卷节奏页签面板（c-volume-pacing）：查看/编辑两态。
 *
 *  数据：GET /volumes/{ref}/pacing（config=卷列已存；prefill/source=未配置时的
 *  展示预填链；plan=章数目标×每段几章；presets=六套全文）。保存＝PUT（配置变更
 *  即失效「已排」）。AI 三动作在右栏（VolumeAssistPanel）——本组件不渲染 AI 按钮。
 *  编辑态基线：卷列有值用卷列，未配置用展示预填（保存即固化到卷列）。 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { volumePacingApi, type VolumePacingResult } from "@/lib/volumePacingApi";
import type { PacingConfig } from "@/lib/volumePacing";
import { segmentPlan } from "@/lib/volumePacing";

interface Props {
  projectId: string;
  volumeRef: string;
  volumeNo: number;
  chapterTarget: number | null;
  /** 配置保存后回调（父级刷新卷纲页签派生徽章等） */
  onChanged: () => void;
  onDirtyChange: (dirty: boolean) => void;
}

const wan = (target: number) => {
  const w = (target * 2500) / 10000;
  return Number.isInteger(w) ? String(w) : w.toFixed(1);
};

export default function VolumePacingPane({
  projectId,
  volumeRef,
  volumeNo,
  chapterTarget,
  onChanged,
  onDirtyChange,
}: Props) {
  const [data, setData] = useState<VolumePacingResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [draft, setDraft] = useState<PacingConfig | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await volumePacingApi.getVolume(projectId, volumeRef);
      setData(r);
      setDraft(null);
    } catch {
      setError("节奏加载失败，可重试");
    } finally {
      setLoading(false);
    }
  }, [projectId, volumeRef]);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(() => data?.config ?? data?.prefill ?? null, [data]);
  const preset = useMemo(
    () => data?.presets.find((p) => p.key === (draft ?? shown)?.preset) ?? null,
    [data, draft, shown],
  );
  const plan = useMemo(() => {
    const len = (draft ?? shown)?.steps_len ?? data?.plan.steps_len ?? 3;
    const target = chapterTarget ?? data?.plan.target ?? 0;
    return { ...segmentPlan(target, len), target, len };
  }, [draft, shown, data, chapterTarget]);

  // 编辑基线＝卷列有值用卷列，未配置用展示预填（保存即固化到卷列）
  const baseline = useMemo(() => data?.config ?? data?.prefill ?? null, [data]);
  const dirty = useMemo(
    () => !!draft && !!baseline && JSON.stringify(draft) !== JSON.stringify(baseline),
    [draft, baseline],
  );
  useEffect(() => {
    onDirtyChange(dirty && mode === "edit");
  }, [dirty, mode, onDirtyChange]);

  const overlong = !!(preset && (draft ?? shown)?.steps_len !== undefined &&
    (draft?.steps_len ?? shown?.steps_len ?? 0) >= preset.warn_len);

  const save = useCallback(async () => {
    if (!draft) return;
    setSaving(true);
    try {
      // 配置变更即失效「已排」：保存恒落 planned=false（重排由右栏 AI 再次采纳）
      await volumePacingApi.saveVolume(projectId, volumeRef, { ...draft, planned: false });
      setMode("view");
      await load();
      onChanged();
    } finally {
      setSaving(false);
    }
  }, [draft, projectId, volumeRef, load, onChanged]);

  if (loading) return <p className="desc">节奏加载中…</p>;
  if (error) return <p className="desc">{error}</p>;
  if (!data || !shown) return <p className="desc">卷不存在</p>;

  const planLine = chapterTarget
    ? `第 1–${chapterTarget} 章 · 按「${preset?.label ?? shown?.preset ?? ""}」约 ${plan.n} 段${plan.rem ? `（末段 ${plan.rem} 章收尾）` : ""}；AI 排卷纲时落成本卷章纲。`
    : "本卷还没设章数目标——填上后这里按套路给段表。";

  return (
    <div>
      {/* 顶栏（查看/编辑随 mode 切换，沿用卷纲页签 ol-top 惯例） */}
      {mode === "view" ? (
        <div className="ol-top">
          <span className="note">节奏 · 这卷怎么翻</span>
          <span className="push">
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setDraft(
                  shown
                    ? {
                        preset: shown.preset,
                        steps: shown.steps.map((s) => ({ ...s })),
                        steps_len: shown.steps_len,
                        ch1_extra_on: shown.ch1_extra_on,
                        ch1_extra: shown.ch1_extra,
                        planned: false,
                      }
                    : null,
                );
                setMode("edit");
              }}
            >
              编辑节奏
            </button>
          </span>
        </div>
      ) : (
        <div className="ol-top">
          <span className="note">正在编辑节奏</span>
          <span className="push">
            <button className="btn btn-primary btn-sm" disabled={saving || !dirty} onClick={() => void save()}>
              保存
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setDraft(null);
                setMode("view");
              }}
            >
              取消
            </button>
          </span>
        </div>
      )}

      {mode === "view" ? (
        <div data-testid="pacing-view">
          <div className="vc-summary">
            <span className="vc-k">套路</span>
            <b>{preset?.label}</b>
            <span className="vc-sub">{preset?.sub}</span>
            <span className="vc-k">一段</span>
            <b>{shown?.steps_len ?? 3} 章</b>
            {volumeNo === 1 && (
              <>
                <span className="vc-k">全书第 1 章</span>
                <span className="vc-sub">
                  {shown?.ch1_extra_on ? "黄金开篇" : "照套路走"}
                </span>
              </>
            )}
          </div>
          {chapterTarget ? (
            <span className={`vc-recon${overlong ? " warn" : ""}`}>
              ✓ 本卷目标 {chapterTarget} 章 ≈ {wan(chapterTarget)} 万字（网文一卷常见 3–10 万字）
            </span>
          ) : (
            <span className="vc-recon warn">⚠ 先在卷纲里填章数目标，这里才能对体量</span>
          )}
          <div className="vc-planline">
            <em>这一卷的剧情安排</em>
            <span className={`tag${shown?.planned ? " ok-tag" : ""}`}>
              {shown?.planned ? "已排" : "未排"}
            </span>
            <span className="vc-fine">{planLine}</span>
          </div>
          <p className="vc-fine" style={{ marginTop: 12 }}>
            配好之后，AI 出剧情、写正文、体检这一卷，都会照这张表来。
          </p>
        </div>
      ) : (
        <div data-testid="pacing-edit">
          <p className="vc-lead">
            给这一卷定个<b>剧情套路</b>：每 {draft?.steps_len ?? 3} 章讲完一段小剧情，段段落在小高潮上——AI
            拆剧情、写正文都照这张表来。
          </p>
          <p className="vc-fine">这是这本书自己的设定，随时能改；不改就一直用题材默认的套路。</p>

          <div className="vc-rowline" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <span className="vc-k">选个套路（换一种讲法）</span>
            <div className="vc-protos">
              {data.presets.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  className={draft?.preset === p.key ? "on" : ""}
                  onClick={() =>
                    setDraft((d) => ({
                      preset: p.key,
                      steps: p.steps.map((s) => ({ ...s })),
                      steps_len: p.steps_len,
                      ch1_extra_on: d?.ch1_extra_on ?? volumeNo === 1,
                      ch1_extra: p.ch1_extra,
                      planned: false,
                    }))
                  }
                >
                  <span>{p.label}</span>
                  <small>{p.sub}</small>
                </button>
              ))}
            </div>
          </div>

          <div className="vc-rowline" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <span className="vc-k">套路分几步（每步写什么，一句话；润色入口在右栏 AI 助手）</span>
            <div className="vc-steps">
              {(draft?.steps ?? []).map((s, i) => (
                <div className="vc-step" key={i}>
                  <span className="vc-no">{i + 1}</span>
                  <input
                    className="input name"
                    value={s.n}
                    maxLength={12}
                    aria-label={`第${i + 1}步`}
                    onChange={(e) =>
                      setDraft((d) => {
                        if (!d) return d;
                        const steps = d.steps.map((x, j) => (j === i ? { ...x, n: e.target.value } : x));
                        return { ...d, steps };
                      })
                    }
                  />
                  <input
                    className="input task"
                    value={s.t}
                    maxLength={60}
                    aria-label={`第${i + 1}步写什么`}
                    onChange={(e) =>
                      setDraft((d) => {
                        if (!d) return d;
                        const steps = d.steps.map((x, j) => (j === i ? { ...x, t: e.target.value } : x));
                        return { ...d, steps };
                      })
                    }
                  />
                  <button
                    className="icon-btn"
                    title="删掉这一步"
                    aria-label="删掉这一步"
                    hidden={(draft?.steps.length ?? 0) <= 2}
                    onClick={() =>
                      setDraft((d) => (d ? { ...d, steps: d.steps.filter((_, j) => j !== i) } : d))
                    }
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
            <button
              className="lnk"
              hidden={(draft?.steps.length ?? 0) >= 6}
              onClick={() =>
                setDraft((d) =>
                  d ? { ...d, steps: [...d.steps, { n: "新的一步", t: "这一步写什么，一句话。" }] } : d,
                )
              }
            >
              ＋ 加一步
            </button>
          </div>

          <div className="vc-rowline">
            <label htmlFor="pacing-len">一段剧情讲几章</label>
            <input
              id="pacing-len"
              className="input num"
              type="number"
              min={1}
              max={30}
              value={draft?.steps_len ?? 3}
              onChange={(e) => {
                const n = Math.min(30, Math.max(1, parseInt(e.target.value, 10) || 3));
                setDraft((d) => (d ? { ...d, steps_len: n } : d));
              }}
            />
            <span className="vc-lenhint">{preset?.hint}</span>
          </div>

          {volumeNo === 1 && (
            <div className="vc-rowline" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <span className="vc-k">全书第 1 章 · 额外交代</span>
              <div className="vc-rowline" style={{ marginTop: 6 }}>
                <button
                  className="switch-btn"
                  role="switch"
                  aria-checked={!!draft?.ch1_extra_on}
                  onClick={() => setDraft((d) => (d ? { ...d, ch1_extra_on: !d.ch1_extra_on } : d))}
                >
                  <span className="sw-track">
                    <span className="sw-knob"></span>
                  </span>
                  <span className="sw-label">{draft?.ch1_extra_on ? "开" : "关"}</span>
                </button>
                <span className="vc-lenhint">
                  只对第一卷的第 1 章生效（网文黄金开篇）；关掉＝第 1 章照套路第一步正常走
                </span>
              </div>
              <input
                className="input"
                style={{ marginTop: 8 }}
                maxLength={80}
                disabled={!draft?.ch1_extra_on}
                value={draft?.ch1_extra ?? ""}
                onChange={(e) => setDraft((d) => (d ? { ...d, ch1_extra: e.target.value } : d))}
              />
            </div>
          )}

          <div className={`vc-recon${overlong ? " warn" : ""}`}>
            {overlong
              ? `⚠ 一段剧情 ${(draft?.steps_len ?? 3)} 章有点拖：超过 ${(preset?.warn_len ?? 6) - 1} 章，读者会等疲。要么压回来，要么把这一卷的目标章数调小。`
              : chapterTarget
                ? `✓ 这卷目标 ${chapterTarget} 章 ≈ ${wan(chapterTarget)} 万字（网文一卷常见 3–10 万字）；一段剧情约 ${draft?.steps_len ?? 3} 章，全卷 ${plan.n} 段${plan.rem ? `（末段 ${plan.rem} 章收尾）` : ""}；第 1–${chapterTarget} 章都走「${preset?.label}」。`
                : `✓ 一段剧情约 ${draft?.steps_len ?? 3} 章；填了章数目标后这里对体量。`}
          </div>
        </div>
      )}
    </div>
  );
}
