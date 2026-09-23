/** 卷视图（storyline 卷视图整页，c-volume-view-storyline）：头部＋四页签。
 *  卷纲＝查看/编辑两态（六分组＋本卷进度线）；本卷章节＝主线台账（ghost 只汇总）；
 *  角色关系/伏笔＝卷域投影（截至本卷末，只读）。右栏卷语境经 onRailData 上抛
 *  （与章模式 onRailData 同构；卸载即清空防残留）。 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { nodeLabel } from "@/lib/nodeTitle";
import type { UseWorkbenchReturn } from "@/hooks/useWorkbench";
import type { VolumeExpandDraft } from "@/lib/volumePlanApi";
import {
  toVolumeFormData,
  volumeFormToPayload,
  type VolumeFormData,
} from "../volume/form";
import {
  PLOT_STAGES,
  type VolumeDetail,
} from "../volume/types";
import { ResplitConfirmModal } from "./modals";
import { RelationsGraphPane } from "./RelationsGraphPane";
import { HooksPane } from "./HooksPane";

export type VolumeTab = "outline" | "chapters" | "rels" | "hooks";

/** 上抛右栏的卷语境（Rail mode="volume" 消费；与 RailChapterData 平级） */
export interface VolumeRailData {
  volume: number;
  title: string;
  tab: VolumeTab;
  detail: VolumeDetail;
  /** 主线写作位所在卷号（c-chapter-plan-ai 末端门禁；null＝全书无章） */
  frontierVol: number | null;
}

interface VolumeWorkspaceProps {
  projectId: string;
  volumeRef: string;
  wb: UseWorkbenchReturn;
  onGoChapter: (ref: string) => void;
  onVolumeMutated: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onRailData: (data: VolumeRailData | null) => void;
  /** 规划台回填（c-volume-antagonist）：seq 递增触发一次逐段落下 */
  backfill?: {
    seq: number;
    draft: VolumeExpandDraft;
  } | null;
  /** 保存成功后回调（采纳路径：落写作默认页） */
  onSaved?: () => void;
  /** 「拆下一章」手写五段（c-chapter-plan-ai；全档） */
  onSplitManual: () => void;
  /** 回改这一章（5.6）：派生视图行／左树共用同一张本章卡 */
  onEditChapter: (ref: string) => void;
}

const TABS: Array<[VolumeTab, string]> = [
  ["outline", "卷纲"],
  ["chapters", "本卷章节"],
  ["rels", "角色关系"],
  ["hooks", "伏笔"],
];

export default function VolumeWorkspace({
  projectId,
  volumeRef,
  wb,
  onGoChapter,
  onVolumeMutated,
  onDirtyChange,
  onRailData,
  onEditChapter,
  backfill,
  onSaved,
  onSplitManual,
}: VolumeWorkspaceProps) {
  const [detail, setDetail] = useState<VolumeDetail | null>(null);
  const [form, setForm] = useState<VolumeFormData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<VolumeTab>("outline");
  // 主线写作位（首个未归档章，含草稿；与排队门禁同源）
  const [frontier, setFrontier] = useState<{ vol: number; ch: number } | null>(
    null,
  );

  // ── 规划台回填（volume-plan-ai）：逐段落下、跳过作者已改字段、期间保存禁用 ──
  const [filling, setFilling] = useState(false);
  const filledSeqRef = useRef(0);
  const touchedRef = useRef<Set<string>>(new Set());
  const fillTimerRef = useRef<number | null>(null);

  const patch = useCallback((p: Partial<VolumeFormData>) => {
    // 回填期间作者动过的字段记入 touched（后续步骤跳过，不吞输入）
    if (filling) Object.keys(p).forEach((k) => touchedRef.current.add(k));
    setForm((f) => (f ? { ...f, ...p } : f));
  }, [filling]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = (await api.get(
        `/novels/${projectId}/volumes/${volumeRef}`,
      )) as VolumeDetail;
      setDetail(data);
      setForm(null);
    } catch (e: any) {
      setError(e?.message || "加载卷详情失败");
    } finally {
      setLoading(false);
    }
  }, [projectId, volumeRef]);

  // 换卷：页签回落「卷纲」并重取详情
  useEffect(() => {
    setTab("outline");
    void load();
  }, [load]);

  // 主线写作位（详情变化后随刷：建章/归档会改变 frontier）
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = (await api.get(`/novels/${projectId}/frontier`)) as {
          frontier: { volume_no: number; chapter_no: number } | null;
        };
        if (alive) {
          setFrontier(
            d.frontier
              ? { vol: d.frontier.volume_no, ch: d.frontier.chapter_no }
              : null,
          );
        }
      } catch {
        if (alive) setFrontier(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, detail]);

  const dirty = useMemo(
    () =>
      form !== null &&
      detail !== null &&
      JSON.stringify(form) !== JSON.stringify(toVolumeFormData(detail)),
    [form, detail],
  );
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  // 重拆整卷（c-chapter-plan-ai D14）：盘点确认 → 清拟定章（降序）→ 刷新树与详情
  const [resplitOpen, setResplitOpen] = useState(false);
  const doResplit = useCallback(async () => {
    try {
      const r = (await api.post(
        `/novels/${projectId}/volumes/${volumeRef}/chapters/resplit`,
        {},
      )) as { removed?: string[] };
      const n = r?.removed?.length ?? 0;
      toast.success(n ? `已清掉 ${n} 章拟定章——可以重新拆了` : "没有可清掉的拟定章");
      await load();
      onVolumeMutated();
    } catch (e: any) {
      toast.error(e?.message || "重拆失败，请重试");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volumeRef, load, onVolumeMutated]);

  // 右栏卷语境上抛：卸载/换卷/换页签先清空（防未选中卷时残留统计）
  useEffect(() => {
    if (detail) {
      onRailData({
        volume: detail.volume,
        title: nodeLabel("卷", detail.volume, detail.title),
        tab,
        detail,
        frontierVol: frontier ? frontier.vol : null,
      });
    } else {
      onRailData(null);
    }
    return () => onRailData(null);
  }, [detail, tab, frontier, onRailData]);

  // 回填执行：进场/展开依据只读（不占表单步骤），其余按段序 160ms/段
  useEffect(() => {
    if (!backfill || !detail || backfill.seq === filledSeqRef.current) return;
    filledSeqRef.current = backfill.seq;
    const base = toVolumeFormData(detail);
    const d = backfill.draft;
    touchedRef.current = new Set();
    setForm({
      ...base,
      title: d.name?.trim() ? d.name.slice(0, 6) : base.title,
    });
    const steps: Array<[keyof VolumeFormData, string]> = [
      ["summary", d.summary],
      ["core_conflict", d.conflict],
      ["antagonist_type", d.antagonist_type || ""],
      ["antagonist_line", d.antagonist_line || ""],
      ["ending", d.ending],
      ["chapter_target", d.chapter_target > 0 ? String(d.chapter_target) : ""],
    ];
    setFilling(true);
    let i = 0;
    let alive = true;
    const tick = () => {
      if (!alive) return;
      if (i >= steps.length) {
        setFilling(false);
        toast.success("卷纲已填好 · 改完点保存");
        return;
      }
      const [k, v] = steps[i++];
      if (!touchedRef.current.has(k)) setForm((f) => (f ? { ...f, [k]: v } : f));
      fillTimerRef.current = window.setTimeout(tick, 160);
    };
    fillTimerRef.current = window.setTimeout(tick, 120);
    return () => {
      alive = false;
      if (fillTimerRef.current != null) window.clearTimeout(fillTimerRef.current);
      setFilling(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backfill?.seq, detail?.ref]);

  const startEdit = () => {
    if (detail) setForm(toVolumeFormData(detail));
  };
  const cancelEdit = () => setForm(null);

  const save = async () => {
    if (!form || !detail || saving || filling) return;
    if (!form.summary.trim() || !form.core_conflict.trim()) {
      toast.error("本卷主旨与核心矛盾为必填，补上再保存");
      return;
    }
    const target = form.chapter_target.trim();
    if (target !== "" && (!/^\d+$/.test(target) || Number(target) < 1 || Number(target) > 9999)) {
      toast.error("章数目标须为 1-9999，留空为不设");
      return;
    }
    setSaving(true);
    try {
      await api.put(
        `/novels/${projectId}/volumes/${volumeRef}`,
        volumeFormToPayload(form),
      );
      setForm(null);
      await load();
      onVolumeMutated();
      toast.success(`《${detail.title}》卷纲已保存`);
      onSaved?.();
    } catch (e: any) {
      toast.error(
        e?.status === 422
          ? "部分字段超长或格式有误，请检查后重试"
          : e?.message || "保存失败",
      );
    } finally {
      setSaving(false);
    }
  };

  const label = detail ? nodeLabel("卷", detail.volume, detail.title) : "";
  const mainlineCount = detail?.chapters.length ?? 0;
  const archivedCount =
    detail?.chapters.filter((c) => c.archived).length ?? 0;

  return (
    <div className="col-panel vol-shell">
        {loading ? (
          <p className="desc">卷视图加载中…</p>
        ) : error || !detail ? (
          <div className="field">
            <p className="desc">{error || "卷不存在"}</p>
            <button className="btn btn-secondary btn-sm" onClick={() => void load()}>
              重试
            </button>
          </div>
        ) : (
          <>
            <header className="e-head">
              <p className="e-kicker">卷 · 分卷计划</p>
              <h2 className="e-title">{label}</h2>
              <div className="e-meta">
                <span className="tag">{mainlineCount} 章</span>
                <span className="tag">已归档 {archivedCount} 章</span>
                {/* 章数目标（spec：头部卷名＋章数，不设则不显） */}
                {detail.chapter_target ? (
                  <span className="tag" data-testid="vol-target-tag">
                    目标 {detail.chapter_target} 章
                  </span>
                ) : null}
              </div>
            </header>

            <div className="ch-tabs" role="tablist" aria-label="分卷计划">
              {TABS.map(([key, text]) => (
                <button
                  key={key}
                  className={`chtab${tab === key ? " on" : ""}`}
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                >
                  {text}
                </button>
              ))}
            </div>

            <div className="e-pad">
            {tab === "outline" && (
              <VolumeOutlinePane
                detail={detail}
                form={form}
                saving={saving}
                filling={filling}
                frontier={frontier}
                onPatch={patch}
                onEdit={startEdit}
                onCancel={cancelEdit}
                onSave={() => void save()}
                onSplitManual={onSplitManual}
                onResplit={() => setResplitOpen(true)}
                onEditChapter={onEditChapter}
              />
            )}
            {tab === "chapters" && (
              <ChapterLedgerPane
                projectId={projectId}
                volumeRef={volumeRef}
                detail={detail}
                frontier={frontier}
                wb={wb}
                onGoChapter={onGoChapter}
                onMutated={() => void load()}
              />
            )}
            {tab === "rels" && (
              <RelationsGraphPane projectId={projectId} volumeScope={detail.volume} />
            )}
            {tab === "hooks" && (
              <HooksPane projectId={projectId} volumeScope={detail.volume} />
            )}
            </div>
          </>
        )}
      <ResplitConfirmModal
        open={resplitOpen}
        onClose={() => setResplitOpen(false)}
        onConfirm={() => void doResplit()}
        planned={(detail?.chapters ?? [])
          .filter((c) => !c.has_prose && !c.archived)
          .map((c) => ({ no: c.chapter, title: c.title }))}
        kept={(detail?.chapters ?? []).filter((c) => c.has_prose || c.archived).length}
      />
    </div>
  );
}

// ── 卷纲页签：查看/编辑两态 ────────────────────────────────────────────────

function VolumeOutlinePane({
  detail,
  form,
  saving,
  filling,
  frontier,
  onPatch,
  onEdit,
  onCancel,
  onSave,
  onSplitManual,
  onResplit,
  onEditChapter,
}: {
  detail: VolumeDetail;
  form: VolumeFormData | null;
  saving: boolean;
  /** 规划台回填进行中（保存禁用，防半截写库） */
  filling: boolean;
  frontier: { vol: number; ch: number } | null;
  onPatch: (p: Partial<VolumeFormData>) => void;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  /** 「拆下一章」手写五段（c-chapter-plan-ai；全档） */
  onSplitManual: () => void;
  /** 「重拆本卷」盘点确认（c-chapter-plan-ai D14）：清掉拟定章重排 */
  onResplit: () => void;
  /** 回改这一章（5.6）：派生视图行可点开同一张本章卡 */
  onEditChapter: (ref: string) => void;
}) {
  const here =
    frontier && frontier.vol === detail.volume
      ? `第 ${frontier.ch} 章`
      : "不在本卷";
  // 主线末端门禁（c-chapter-plan-ai）：只挡「写作位之前的卷」（那才会插进主线中段）；
  // 写作位所在卷及其之后的卷都可拆——上一卷写完后开新卷第一拆时，frontier 的全归档
  // 待写占位仍落在旧卷，严格等值会把它堵死。
  const splitBlocked = frontier != null && detail.volume < frontier.vol;
  const archived = detail.chapters.filter((c) => c.archived).length;
  const draft = detail.chapters.filter((c) => c.has_prose && !c.archived).length;
  const planned = detail.chapters.filter((c) => !c.has_prose && !c.archived).length;

  if (form) {
    return (
      <>
        <div className="ol-top">
          <span className="note">正在编辑卷纲 · {detail.title}</span>
          <span className="push">
            <button
              className="btn btn-secondary btn-sm"
              disabled={saving || filling}
              onClick={onSave}
            >
              {filling ? "回填中…" : "保存"}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={saving || filling}
              onClick={onCancel}
            >
              取消
            </button>
          </span>
        </div>
        {/* 编辑态（c-volume-antagonist 终版）：四问编号序＋卷名/章数＋节点（与查看态、抽卡卡同骨架） */}
        <div className="fro">
          <em>进场</em>
          <p className="pv-ro" data-testid="vol-prev-ending">
            {detail.prev_ending?.text || "（还没有上一卷的记录）"}
          </p>
          <span className="none">
            {detail.prev_ending?.source || "写到那里之后，这里会换成实际的样子"}
          </span>
        </div>
        <div className="fro">
          <em>
            <span className="qno">1</span>这一卷讲什么？ <span className="req">必填</span>
          </em>
          <textarea
            id="vol-summary"
            aria-label="本卷主旨"
            className="textarea"
            rows={2}
            maxLength={300}
            placeholder="一句话概括这一卷的核心意义"
            value={form.summary}
            onChange={(e) => onPatch({ summary: e.target.value })}
          />
        </div>
        <div className="fro">
          <em>
            <span className="qno">2</span>主要冲突是什么？ <span className="req">必填</span>
          </em>
          <textarea
            id="vol-conflict"
            aria-label="核心矛盾"
            className="textarea"
            rows={2}
            maxLength={150}
            placeholder="想做什么，被什么拦住"
            value={form.core_conflict}
            onChange={(e) => onPatch({ core_conflict: e.target.value })}
          />
        </div>
        <div className="fro">
          <em>
            <span className="qno">3</span>这一卷的坎是谁／是什么？
          </em>
          <div className="hurdle-row">
            <select
              id="vol-ant-type"
              aria-label="坎的类型"
              className="input"
              value={form.antagonist_type}
              onChange={(e) => onPatch({ antagonist_type: e.target.value })}
            >
              <option value="">先不选</option>
              {["人物", "难题", "环境", "自我", "势力"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              id="vol-ant-line"
              aria-label="坎的一句话"
              className="input"
              maxLength={150}
              placeholder="例：执法官雷——点名要他停手"
              value={form.antagonist_line}
              onChange={(e) => onPatch({ antagonist_line: e.target.value })}
            />
          </div>
        </div>
        <div className="fro">
          <em>
            <span className="qno">4</span>卷末收在哪里？
          </em>
          <textarea
            id="vol-ending"
            aria-label="卷末结局"
            className="textarea"
            rows={3}
            maxLength={300}
            placeholder="这一卷结束时，局面变成什么样"
            value={form.ending}
            onChange={(e) => onPatch({ ending: e.target.value })}
          />
        </div>
        <div className="fgrid">
          <div className="fro">
            <em>卷名</em>
            <input
              id="vol-name"
              aria-label="卷名"
              className="input"
              maxLength={200}
              value={form.title}
              onChange={(e) => onPatch({ title: e.target.value })}
            />
          </div>
          <div className="fro">
            <em>章数目标</em>
            <input
              id="vol-target"
              aria-label="章数目标"
              className="input num"
              type="number"
              min={1}
              max={9999}
              placeholder="1-9999，留空为不设"
              value={form.chapter_target}
              onChange={(e) => onPatch({ chapter_target: e.target.value })}
            />
          </div>
        </div>
        <div className="fro">
          <em>本卷角色 <span className="tag">自动聚合</span></em>
          <p className="pv-ro">
            {detail.cast_members.length
              ? detail.cast_members.map((c) => c.name + (c.role ? `（${c.role}）` : "")).join("　")
              : "还没有章——写到谁（章纲登记出场），这里自动有谁"}
          </p>
        </div>
        <div className="fro">
          <em>这一卷的伏笔</em>
          <p className="pv-ro">住在台账里——切「伏笔」页签看与办；登记与收束都在台账。</p>
        </div>

        <p className="hint">卷纲只做剧情规划，人物的具体言行交给角色设定去推导。</p>
      </>
    );
  }

  // ── 查看态：四问一页纸（无折叠块；与抽卡卡同骨架）──
  return (
    <>
      <div className="ol-top">
        <span className="note">卷纲 · 规划本卷剧情</span>
        <span className="push">
          <button
            className="btn btn-secondary btn-sm"
            data-testid="volume-split-manual"
            disabled={splitBlocked}
            title={
              splitBlocked
                ? `写作位在第${frontier!.vol}卷——这一卷还没轮到`
                : "手写这一章的关键剧情（五段），排上后再补章纲"
            }
            onClick={onSplitManual}
          >
            拆下一章
          </button>
          {planned > 0 && (
            <button
              className="btn btn-ghost btn-sm"
              data-testid="volume-resplit"
              title="清掉本卷拟定章（有正文/已归档的保留），之后重新拆"
              onClick={onResplit}
            >
              重拆本卷
            </button>
          )}
          <button className="btn btn-secondary btn-sm" onClick={onEdit}>
            编辑卷纲
          </button>
        </span>
      </div>

      <div className="fro" data-od-id="enter-row">
        <em>
          {detail.volume > 1 ? "上一卷的结尾" : "起点"} <span className="tag">只读</span>
        </em>
        <p>{detail.prev_ending?.text || "（还没有记录）"}</p>
        <span className="none">
          {detail.prev_ending?.source || "写到那里之后，这里会换成实际的样子"}
        </span>
      </div>
      <div className="fro">
        <em><span className="qno">1</span>这一卷讲什么</em>
        <p className="lead">{detail.summary || "（未填）"}</p>
      </div>
      <div className="fro">
        <em><span className="qno">2</span>主要冲突</em>
        <p>{detail.core_conflict || "（未填）"}</p>
      </div>
      <div className="fro">
        <em><span className="qno">3</span>这一卷的坎</em>
        <p>
          {detail.antagonist_line
            ? [detail.antagonist_type, detail.antagonist_line].filter(Boolean).join(" · ")
            : "（未填）"}
        </p>
      </div>
      <div className="fro">
        <em><span className="qno">4</span>卷末收在哪里</em>
        <p>{detail.ending || "（未填）"}</p>
      </div>
      <div className="fro" style={{ marginTop: 2 }}>
        <em>本卷角色 <span className="tag">自动聚合</span></em>
        <p className="none">
          {detail.cast_members.length
            ? detail.cast_members.map((c) => c.name + (c.role ? `（${c.role}）` : "")).join("　")
            : "还没有章——写到谁（章纲登记出场），这里自动有谁"}
        </p>
      </div>
      <div className="fro">
        <em>这一卷的伏笔</em>
        <p className="none">住在台账里——切「伏笔」页签看与办；登记与收束都在台账。</p>
      </div>
      {splitBlocked && (
        <p className="hint" data-testid="volume-split-blocked">
          写作位在第{frontier!.vol}卷——这一卷还没轮到，先去第{frontier!.vol}卷拆章。
        </p>
      )}
      {/* 剧情推进（派生）——c-chapter-plan-ai：从已排章派生，只读；替代已退役的关键剧情节点段 */}
      <details className="cfg" open data-testid="vol-plot-progress">
        <summary>
          剧情推进（派生）{" "}
          <span className="tag">{detail.chapters.length} 章</span>
          <Chev />
        </summary>
        <div className="inner">
          {detail.chapters.length === 0 ? (
            <p className="sub-empty">还没有排章——拆下一章后这里会按章列出推进。</p>
          ) : (
            <div className="sub-list">
              {detail.chapters.map((c, i) => (
                  <div
                    className="rowx"
                    key={c.ref}
                    role="button"
                    tabIndex={0}
                    data-testid={`vol-plot-row-${c.chapter}`}
                    title="改这一章（关键剧情五段）"
                    style={{ cursor: "pointer" }}
                    onClick={() => onEditChapter(c.ref)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") onEditChapter(c.ref);
                    }}
                  >
                    <span className="num">{i + 1}</span>
                    <div className="cols cn">
                      <span className="qno">{c.plot_stage || "（未定阶段）"}</span>
                      <p className="node-tx">{c.title}</p>
                    </div>
                    <span className="tag">
                      {c.archived ? "已归档" : c.has_prose ? "草稿" : "已排"}
                    </span>
                  </div>
                ))}
            </div>
          )}
        </div>
      </details>

      <p className="seg-h">
        本卷进度 <span className="note">由各章实际归属推导</span>
      </p>
      <div className="pos-line" data-testid="vol-progress">
        <span className="pos">
          <em>已归档</em>
          <b>{archived} 章</b>
        </span>
        <span className="pos">
          <em>草稿</em>
          <b>{draft} 章</b>
        </span>
        <span className="pos">
          <em>拟定</em>
          <b>{planned} 章</b>
        </span>
        <span className="pos">
          <em>待写</em>
          <b>{here}</b>
        </span>
      </div>
    </>
  );
}

// ── 本卷章节页签 ──────────────────────────────────────────────────────────

function ChapterLedgerPane({
  projectId,
  volumeRef,
  detail,
  frontier,
  wb,
  onGoChapter,
  onMutated,
}: {
  projectId: string;
  volumeRef: string;
  detail: VolumeDetail;
  frontier: { vol: number; ch: number } | null;
  wb: UseWorkbenchReturn;
  onGoChapter: (ref: string) => void;
  onMutated: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const create = async () => {
    const t = title.trim();
    if (!t) {
      toast.error("章节标题必填");
      return;
    }
    setBusy(true);
    try {
      await api.post(`/novels/${projectId}/volumes/${volumeRef}/chapters`, {
        title: t,
      });
      toast.success("已新增一章，先写它的章纲");
      setTitle("");
      setAdding(false);
      onMutated();
      wb.refresh();
    } catch {
      toast.error("创建章失败");
    } finally {
      setBusy(false);
    }
  };

  const canAdd = frontier != null && frontier.vol === detail.volume;

  return (
    <>
      <p className="seg-h">
        本卷章节 <span className="note">主线章按章序排列 · 点行进入该章</span>
      </p>
      {detail.chapters.length === 0 ? (
        <p className="vempty">这一卷还没有章节。</p>
      ) : (
        <div className="ledger">
          {detail.chapters.map((c) => {
            const state = c.archived
              ? "已归档"
              : c.has_prose
                ? "草稿"
                : "拟定";
            return (
              <button
                className="lrow chrow vol-chrow"
                key={c.ref}
                onClick={() => onGoChapter(c.ref)}
              >
                <span className="lname">
                  第 {c.chapter} 章 · {c.title || "（未命名）"}
                  <em>
                    {c.outline_summary ||
                      (c.has_prose ? "（没有章纲）" : "（待补章纲）")}
                  </em>
                </span>
                <span className={`lstate${!c.archived && c.has_prose ? " open" : ""}`}>
                  {state}
                </span>
              </button>
            );
          })}
        </div>
      )}
      {detail.ghost_count > 0 && (
        <p className="graph-iso">
          旧稿支线 {detail.ghost_count} 章 · 已脱离主线，不计入本书设定
        </p>
      )}
      {canAdd ? (
        adding ? (
          <div className="vol-addrow">
            <input
              className="input"
              autoFocus
              placeholder="章节标题（必填）"
              value={title}
              disabled={busy}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void create();
                if (e.key === "Escape") setAdding(false);
              }}
            />
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void create()}>
              确定
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={busy}
              onClick={() => setAdding(false)}
            >
              取消
            </button>
          </div>
        ) : (
          <div className="edit-bar">
            <button className="btn btn-secondary btn-sm" onClick={() => setAdding(true)}>
              <PlusIcon /> 在本卷新增一章
            </button>
          </div>
        )
      ) : (
        <p className="hint">新增章节排在主线末端；这一卷要等前面写到这里。</p>
      )}
    </>
  );
}

function Chev() {
  return (
    <svg
      className="chev"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      width="13"
      height="13"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
    </svg>
  );
}
