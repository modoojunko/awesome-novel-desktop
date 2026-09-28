// CastReviewModal — 盘点出场人物弹窗（c-character-intro，设计稿 v2.4 十一态复刻）。
// 盘点中②／盘点结果③（含零新增④·免费锁⑥·写入回程⑧）／抽卡三方向⑤／抽卡中⑩／
// 抽卡失败⑪／写入前确认⑦（两形态：选卡进＝预填＋「‹ 返回换一张」；手填进＝空格无返回，
// 不露任何 AI 预填——免费分割命门）／盘点失败⑨（重试/去模型配置/先不盘点，无「自己填」）。
// 缺口表按 gapId 独立（三选一＋抽卡批次互不影响）；改段/延后零请求零落库；落账回执
// 回结果页（缺口转已处理、剩余继续、全部处理完收场）。视觉词汇照设计稿（cr-*/pick-*/
// pk-corner g-S「最合适」/g-A「也行」/g-B「备选」/lock-card/no-card/cr-sug）。
import { useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import {
  cardDuty,
  cardWhyNotOld,
  CHOICES,
  EXIT_KINDS,
  GRADES,
  GRADE_NOTE,
  RANK_DIMS,
  type CastChoice,
  type CastWriteFields,
  type CastWriteRequest,
  type CastWriteOutcome,
} from "@/lib/castReviewApi";
import type { CastGapView, CastReviewController } from "@/hooks/useCastReview";

const EMPTY_FIELDS: CastWriteFields = {
  name: "",
  duty: "",
  persona: "",
  entrance: "",
  exitKind: "",
  exitNote: "",
};

const CHOICE_TESTID: Record<CastChoice, string> = {
  加人: "cr-opt-add",
  改段: "cr-opt-edit",
  延后: "cr-opt-defer",
};

export default function CastReviewModal({
  cast,
  chapterLabel,
  plotItems,
  roster,
  castLines,
  isPro,
  onUpgrade,
  onOpenConfig,
  onQuickCreateChar,
}: {
  cast: CastReviewController;
  chapterLabel: string;
  /** 剧情条目（表单快照，判「没判出来」缺行用） */
  plotItems: string[];
  /** 本书角色卡名（不含别名）：缺口「选已有角色」候选（c-character-intro 6.x） */
  roster: string[];
  /** 本章出场名单现值（live）：已有角色候选标「已在名单」 */
  castLines: string[];
  isPro: boolean;
  /** 升级出口（免费锁卡/抽卡 403） */
  onUpgrade: () => void;
  /** 去模型配置（失败态出口） */
  onOpenConfig: () => void;
  /** 行级建卡入口（软提示/没卡标旁；只预填称呼） */
  onQuickCreateChar?: (name: string) => void;
}) {
  const { state } = cast;
  const activeGap = state.gaps.find((g) => g.gapId === state.activeGapId) ?? null;
  const writing = state.writing;

  // 确认页格子（受控态放弹窗内部：关窗丢格子改动）
  const [fields, setFields] = useState<CastWriteFields>(EMPTY_FIELDS);
  useEffect(() => {
    if (state.phase !== "picked") return;
    const card =
      state.pickFrom === "card" && activeGap
        ? activeGap.batches[activeGap.batches.length - 1]?.[state.pickIndex ?? -1]
        : undefined;
    if (card) {
      setFields({
        name: card.name,
        duty: cardDuty(card),
        persona: card.persona,
        entrance: card.entrance,
        exitKind: card.exit_kind,
        exitNote: card.exit_note,
      });
    } else {
      // 手填进＝空格表单、无返回、不露任何 AI 预填
      setFields(EMPTY_FIELDS);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.pickFrom, state.pickIndex, state.activeGapId]);

  const patch = (p: Partial<CastWriteFields>) => setFields((f) => ({ ...f, ...p }));
  const nameOk = fields.name.trim().length > 0;

  const submit = (mode: CastWriteRequest["mode"]) => {
    if (!nameOk || writing || !activeGap) return;
    void (async () => {
      const req: CastWriteRequest = {
        mode,
        fields,
        listOnlyAfterCreate:
          mode === "with-card" &&
          state.writeError?.kind === "save_failed" &&
          state.writeError.created,
      };
      const out: CastWriteOutcome | null = await cast.submitWrite(req);
      if (out?.ok) cast.markWritten(activeGap.gapId, out);
    })();
  };

  // ── 底条（按态切换，设计稿 SCENES 口径）────────────────────────────────
  const allDone = state.gaps.length > 0 && state.gaps.every((g) => g.status !== "open");
  let footNote = "盘点不会改动你的任何内容；要写进章纲的，都走你平时那套保存。";
  let cancelLabel = "先不调整";
  if (state.phase === "result") {
    footNote =
      state.gaps.length === 0
        ? "零新增是正常结果，不是出错。"
        : isPro
          ? "改段／延后不留记录：改段去剧情区改那一条；延后的那条，剧情挪到哪一章就在哪一章再遇到。"
          : "盘点免费；AI 抽人是 PRO。自己填名字、选已有角色，全档免费。";
    cancelLabel = state.gaps.length === 0 ? "知道了" : allDone ? "完成" : "先不调整";
  } else if (state.phase === "cards" || state.phase === "drawing") {
    footNote = "这批卡跟这一章走：误关重开还是同一批，不会重复生成花钱。";
    cancelLabel = "先不抽了";
  } else if (state.phase === "picked") {
    footNote = "两个出口各自独立写入——AI 永远不会替你点。";
    cancelLabel = "先不写入";
  } else if (state.phase === "error") {
    footNote = "失败不会动你的任何内容。";
    cancelLabel = state.error?.kind === "review" ? "先不盘点" : "先不抽了";
  }

  const footer = (
    <>
      <span className="note">{footNote}</span>
      <button className="btn btn-ghost btn-sm" data-testid="cr-cancel" disabled={writing} onClick={cast.close}>
        {cancelLabel}
      </button>
      {state.phase === "picked" && (
        <>
          {state.pickFrom === "card" && (
            <button
              className="btn btn-ghost btn-sm"
              data-testid="cr-back-cards"
              disabled={writing}
              onClick={cast.backToCards}
            >
              ‹ 返回换一张
            </button>
          )}
          <button
            className="btn btn-secondary btn-sm"
            data-testid="cr-list-only"
            disabled={!nameOk || writing}
            onClick={() => submit("list-only")}
          >
            只加名单，先不建卡
          </button>
          <button
            className="btn btn-primary btn-sm"
            data-testid="cr-write"
            disabled={!nameOk || writing}
            onClick={() => submit("with-card")}
          >
            {state.writeError?.kind === "save_failed" && state.writeError.created
              ? "再写入一次名单"
              : "建卡并写入章纲"}
          </button>
        </>
      )}
    </>
  );

  return (
    <Modal
      open={state.open}
      onClose={cast.close}
      title="盘点出场人物"
      width={940}
      wbStyle
      locked={writing}
      footer={footer}
    >
      <div className="cast-review" data-testid="cast-review-modal">
        <p className="kicker">{chapterLabel} · 只看已写好的剧情与现有角色，不替你编剧情</p>

        {/* ② 盘点中 */}
        {state.phase === "reviewing" && (
          <div className="pick-busy" data-testid="cr-reviewing">
            <span>
              <span className="ra-spin" aria-hidden="true" />
              <span aria-live="polite">正在逐段对照这一章的剧情…</span>
            </span>
            <span className="none">
              每段剧情分别看：老角色能不能演、不起名的配角行不行、哪里缺新角色
            </span>
          </div>
        )}

        {/* ⑨/⑪ 失败态（error.kind 分流；盘点失败无「自己填」） */}
        {state.phase === "error" && state.error && (
          <div
            className="pick-error"
            data-testid={state.error.kind === "review" ? "cr-error" : "cr-draw-error"}
          >
            <p className="pv-error">{state.error.message}</p>
            <div className="edit-bar">
              {state.error.kind === "review" ? (
                <>
                  <button className="btn btn-primary btn-sm" data-testid="cr-error-retry" onClick={cast.recheck}>
                    重试
                  </button>
                  <button className="btn btn-secondary btn-sm" data-testid="cr-error-config" onClick={onOpenConfig}>
                    去模型配置
                  </button>
                  <button className="btn btn-ghost btn-sm" data-testid="cr-error-close" onClick={cast.close}>
                    先不盘点
                  </button>
                </>
              ) : (
                <>
                  {state.error.noModel ? (
                    <button className="btn btn-primary btn-sm" data-testid="cr-draw-config" onClick={onOpenConfig}>
                      去模型配置
                    </button>
                  ) : (
                    <button
                      className="btn btn-primary btn-sm"
                      data-testid="cr-draw-retry"
                      onClick={() => state.activeGapId && cast.startDraw(state.activeGapId)}
                    >
                      重试
                    </button>
                  )}
                  <button
                    className="btn btn-secondary btn-sm"
                    data-testid="cr-draw-fill"
                    onClick={() => state.activeGapId && cast.fillManual(state.activeGapId)}
                  >
                    自己填一个
                  </button>
                  <button className="btn btn-ghost btn-sm" data-testid="cr-draw-close" onClick={cast.close}>
                    先不抽了
                  </button>
                </>
              )}
            </div>
          </div>
        )}

        {/* ⑩ 抽卡中 */}
        {state.phase === "drawing" && (
          <div className="pick-busy" data-testid="cr-drawing">
            <span>
              <span className="ra-spin" aria-hidden="true" />
              <span aria-live="polite">
                正在想「{activeGap?.label ?? ""}」的 3 个人物方向…
              </span>
            </span>
            <span className="none">按这段戏缺的人和现有角色推——只给人物方向，不编剧情</span>
          </div>
        )}

        {/* ③④⑥⑧ 盘点结果（零新增/免费锁/写入回程同相） */}
        {state.phase === "result" && (
          <ResultBody
            cast={cast}
            state={state}
            plotItems={plotItems}
            roster={roster}
            castLines={castLines}
            isPro={isPro}
            onUpgrade={onUpgrade}
            onQuickCreateChar={onQuickCreateChar}
          />
        )}

        {/* ⑤ 抽卡三方向 */}
        {state.phase === "cards" && activeGap && (
          <>
            <p className="plans-h">
              {activeGap.label} 缺的这个人，给 3 个互不相同的方向 · 挑一个
            </p>
            <div className="pick-grid" role="radiogroup" aria-label="人物方向三选一">
              {state.cards.map((c, i) => (
                <button
                  type="button"
                  key={`${c.name}-${i}`}
                  className={`pick-card${c.grade === "S" ? " top" : ""}`}
                  data-testid={`cr-pick-card-${i + 1}`}
                  role="radio"
                  aria-checked={false}
                  onClick={() => cast.pickCard(activeGap.gapId, i)}
                >
                  {GRADES.includes(c.grade as (typeof GRADES)[number]) && (
                    <span className={`pk-corner g-${c.grade}`}>
                      {c.grade}
                      <i>{GRADE_NOTE[c.grade]}</i>
                    </span>
                  )}
                  <span className="pk-axis">{c.axis}</span>
                  <p className="pk-title">{c.name}</p>
                  <div className="pk-row">
                    <b>他是干什么的</b>
                    <span>{cardDuty(c)}</span>
                  </div>
                  <div className="pk-row">
                    <b>一句人设</b>
                    <span>{c.persona}</span>
                  </div>
                  <div className="pk-row">
                    <b>怎么出场</b>
                    <span>{c.entrance}</span>
                  </div>
                  <div className="pk-row">
                    <b>怎么退场</b>
                    <span>
                      {c.exit_kind}
                      {c.exit_note ? ` · ${c.exit_note}` : ""}
                    </span>
                  </div>
                  <div className="pk-row">
                    <b>老角色为什么不行</b>
                    <span>{cardWhyNotOld(c, activeGap.whyNotOld)}</span>
                  </div>
                  <div className="pk-read">
                    {RANK_DIMS.map((d) => (
                      <p key={d}>
                        <b>{d}</b>
                        {c.reasons?.[d] ?? ""}
                      </p>
                    ))}
                  </div>
                </button>
              ))}
            </div>
            <div className="pick-foot">
              <button className="btn btn-ghost btn-sm" data-testid="cr-back-review" onClick={cast.backToReview}>
                ‹ 返回盘点结果
              </button>
              <button
                className="btn btn-secondary btn-sm"
                data-testid="cr-redraw"
                onClick={() => cast.redraw(activeGap.gapId)}
              >
                ↻ 都不满意？换一批
              </button>
              <button
                className="btn btn-secondary btn-sm"
                data-testid="cr-fresh"
                onClick={() => cast.freshRedraw(activeGap.gapId)}
              >
                从头再来
              </button>
              <button
                className="btn btn-ghost btn-sm"
                data-testid="cr-fill-manual-2"
                onClick={() => cast.fillManual(activeGap.gapId)}
              >
                自己填一个
              </button>
              <span className="note push">
                换一批避开已出的人物路数（同轴只换人设）；从头再来＝清掉记录重出，可能再遇到之前的方向。选卡后每个格子还能改。
              </span>
            </div>
          </>
        )}

        {/* ⑦ 写入前确认（两形态；申报输入受控态在弹窗内部） */}
        {state.phase === "picked" && (
          <>
            <p className="plans-h">
              {state.pickFrom === "manual"
                ? "自己填——每个格子都可以自己写（不用 AI）"
                : "写入前最后改一遍 · 每个格子都能改"}
            </p>
            <div className="split-row">
              <span className="s-no">新</span>
              <div className="s-main">
                <div className="s-lab">
                  <b>称呼</b>
                  <input
                    className="input"
                    aria-label="称呼"
                    data-testid="claim-name"
                    maxLength={12}
                    value={fields.name}
                    onChange={(e) => patch({ name: e.target.value })}
                  />
                </div>
                <div className="s-lab">
                  <b>他是干什么的</b>
                  <input
                    className="input"
                    aria-label="他是干什么的"
                    value={fields.duty}
                    onChange={(e) => patch({ duty: e.target.value })}
                  />
                </div>
                <div className="s-lab">
                  <b>一句人设</b>
                  <input
                    className="input"
                    aria-label="一句人设"
                    value={fields.persona}
                    onChange={(e) => patch({ persona: e.target.value })}
                  />
                </div>
                <div className="s-lab">
                  <b>怎么出场</b>
                  <input
                    className="input"
                    aria-label="怎么出场"
                    value={fields.entrance}
                    onChange={(e) => patch({ entrance: e.target.value })}
                  />
                </div>
                <div className="s-lab">
                  <b>怎么退场</b>
                  <div style={{ display: "flex", gap: 7, alignItems: "center", flexWrap: "wrap" }}>
                    <select
                      className="input"
                      style={{ width: 130 }}
                      aria-label="怎么退场"
                      value={fields.exitKind}
                      onChange={(e) => patch({ exitKind: e.target.value })}
                    >
                      <option value="">请选择</option>
                      {EXIT_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </select>
                    <input
                      className="input"
                      style={{ flex: 1, minWidth: 180 }}
                      aria-label="退场说明"
                      value={fields.exitNote}
                      onChange={(e) => patch({ exitNote: e.target.value })}
                    />
                  </div>
                </div>
              </div>
            </div>
            {state.writeError && (
              <p className="pv-error" data-testid="cr-write-error" style={{ marginTop: 10 }}>
                {state.writeError.message}
                {state.writeError.kind === "create_failed"
                  ? "（也可以改走「只加名单」，格子里的改动都留着）"
                  : state.writeError.created
                    ? "（卡已建好，这就把名字写进名单）"
                    : ""}
              </p>
            )}
            <p className="hint">
              建卡＝角色表多一张卡，上面几格照抄进卡面，之后在设定页随便改；
              <b>只加名单＝本章出场角色多一行字，暂不建卡</b>
              （选它的话上面几格不保存，之后建卡只带称呼）。两样都算数，AI 都不会替你点。
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}

/** 结果页（③④⑥⑧）：逐段三分类＋缺口卡（gapId 独立）＋软提示＋回执 */
function ResultBody({
  cast,
  state,
  plotItems,
  roster,
  castLines,
  isPro,
  onUpgrade,
  onQuickCreateChar,
}: {
  cast: CastReviewController;
  state: CastReviewController["state"];
  plotItems: string[];
  /** 本书角色卡名（不含别名）：缺口「选已有角色」候选 */
  roster: string[];
  /** 本章出场名单现值（live）：已有角色候选标「已在名单」 */
  castLines: string[];
  isPro: boolean;
  onUpgrade: () => void;
  onQuickCreateChar?: (name: string) => void;
}) {
  const rows = state.rows;
  const gapsByRow = new Map<number | null, CastGapView>();
  for (const g of state.gaps) gapsByRow.set(g.idx, g);

  // 判不出来行：verdict 出闭集的行与缺行以「这一段没判出来」呈现＋重试（不静默少行）
  const knownRows = rows.filter((r) =>
    ["老角色能演", "不起名也行", "缺一个新角色"].includes(r.verdict),
  );
  const covered = new Set(rows.map((r) => r.idx));
  const missingIdx: number[] = [];
  for (let i = 0; i < plotItems.length; i++) {
    if (!covered.has(i)) missingIdx.push(i);
  }
  const unknownRows = rows.filter(
    (r) => !["老角色能演", "不起名也行", "缺一个新角色"].includes(r.verdict),
  );
  const openGaps = state.gaps.filter((g) => g.status === "open");
  const quota = state.review?.quota;
  const quotaLine = quota
    ? quota.regime === "open"
      ? `本卷刚开始，有名有姓的角色一般 5–8 个就够讲，现在 ${quota.named_count} 个——这只影响 AI 抽卡时的建议，你自己填名单永远不受限。`
      : `本卷越往后越要收着加人：每章新加 1–3 个就够，现在 ${quota.named_count} 个——这只影响 AI 抽卡时的建议，你自己填名单永远不受限。`
    : "";

  return (
    <>
      <p className="plans-h">
        逐段盘点 · {plotItems.length || rows.length} 段剧情 · 怎么判的：老角色能演／不起名也行／缺一个新角色
      </p>
      <p className="ai-note" style={{ margin: "-6px 0 10px" }}>
        剧情改过了？
        <button className="lnk" data-testid="cr-recheck" onClick={cast.recheck}>
          重新盘点
        </button>
        ——整章重新盘；已处理的按条目对回，改过的条目重来。
      </p>

      {/* 落账回执（aria-live done-notice；「还有 N 个」/全清两分支） */}
      {state.notice && (
        <div className="notice info" data-testid="done-notice" aria-live="polite" style={{ marginBottom: 10 }}>
          <div className="nt">{state.notice}</div>
        </div>
      )}

      {knownRows.map((row, ri) => {
        const gap = gapsByRow.get(row.idx) ?? null;
        const isOld = row.verdict === "老角色能演";
        const isUnnamed = row.verdict === "不起名也行";
        return (
          <div key={`${row.idx}-${ri}`}>
            <div className="cr-row">
              <div className="cr-top">
                <span className="cr-no">{row.idx == null ? "整章" : `剧情 ${row.idx + 1}`}</span>
                <span className="cr-tx">{row.echo}</span>
                <span className={`pill ${isOld || isUnnamed ? "pill-ok" : "pill-warn"}`}>{row.verdict}</span>
              </div>
              {row.why && <p className="cr-why">{row.why}</p>}
              {(row.who?.length || (isUnnamed && row.as)) ? (
                <p className="cr-who">
                  {isUnnamed && row.as ? "不起名的话，叫他：" : null}
                  {(isUnnamed && row.as ? [row.as] : row.who ?? []).map((n) => (
                    <span className="chip" key={n}>
                      {n}
                    </span>
                  ))}
                </p>
              ) : null}
            </div>
            {gap && (
              <GapCard
                gap={gap}
                cast={cast}
                roster={roster}
                castLines={castLines}
                isPro={isPro}
                onUpgrade={onUpgrade}
                state={state}
              />
            )}
          </div>
        );
      })}

      {/* 判不出来行（出界丢行的呈现；重试＝重新盘点对回） */}
      {[...unknownRows.map((r) => r.echo), ...missingIdx.map((i) => plotItems[i])].map((tx, i) => (
        <div className="cr-row" key={`unknown-${i}`} data-testid="cr-row-unknown">
          <div className="cr-top">
            <span className="cr-no">
              {i < unknownRows.length ? "剧情 ?" : `剧情 ${(missingIdx[i - unknownRows.length] ?? 0) + 1}`}
            </span>
            <span className="cr-tx">{tx}</span>
            <span className="pill pill-warn">这一段没判出来</span>
          </div>
          <p className="cr-why">
            服务端没给出这一段的判定——
            <button className="lnk" data-testid="cr-row-retry" onClick={cast.recheck}>
              重试
            </button>
          </p>
        </div>
      ))}

      {/* 零新增一行收场（常态输出，不是出错） */}
      {state.gaps.length === 0 && openGaps.length === 0 && (
        <ul className="rp-list">
          <li className={`rp-row ${unknownRows.length ? "warn" : "ok"}`}>
            <span className="rp-dot" aria-hidden="true" />
            <span>
              这一章不用加人：{plotItems.length || rows.length} 段剧情，老角色和不起名的配角都演得了。
              {quotaLine}
            </span>
          </li>
        </ul>
      )}

      {/* 丢行/滤名警示（服务端 warnings：不重抽，提示自核） */}
      {(state.review?.warnings ?? []).length > 0 && (
        <ul className="rp-list" data-testid="cr-warnings">
          {state.review!.warnings!.map((w) => (
            <li className="rp-row warn" key={w}>
              <span className="rp-dot" aria-hidden="true" />
              <span>{w}</span>
            </li>
          ))}
        </ul>
      )}

      {/* 软提示：无卡名字反复出场（服务端派生，前端不算跨章聚合） */}
      {(state.review?.hints ?? []).length > 0 && (
        <ul className="rp-list">
          {state.review!.hints.map((h) => (
            <li className="rp-row warn" key={h.name}>
              <span className="rp-dot" aria-hidden="true" />
              <span>
                {h.text}
                {onQuickCreateChar && (
                  <>
                    {" "}
                    <button className="lnk" data-testid={`claim-${h.name}`} onClick={() => onQuickCreateChar(h.name)}>
                      顺手建一张卡
                    </button>
                    ，不建也不影响写作。
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** 缺口卡（gapId 独立；三选一＋抽卡批次互不影响） */
function GapCard({
  gap,
  cast,
  state,
  roster,
  castLines,
  isPro,
  onUpgrade,
}: {
  gap: CastGapView;
  cast: CastReviewController;
  state: CastReviewController["state"];
  /** 本书角色卡名（不含别名）：「选已有角色」候选 */
  roster: string[];
  /** 本章出场名单现值（live）：候选标「已在名单」 */
  castLines: string[];
  isPro: boolean;
  onUpgrade: () => void;
}) {
  const [picking, setPicking] = useState(false);
  const open = gap.status === "open";
  const pill =
    gap.status === "written"
      ? { cls: "", tx: "已写入" }
      : gap.status === "deferred"
        ? { cls: "", tx: "已延后" }
        : gap.status === "edited"
          ? { cls: "", tx: "改段 · 本次算处理过" }
          : gap.choice === "加人"
            ? { cls: "pill-warn", tx: "缺 1 人" }
            : gap.choice === "改段"
              ? { cls: "", tx: "改段 · 本次算处理过" }
              : { cls: "", tx: "已延后" };
  const remaining = state.gaps.filter((g) => g.status === "open").length;
  const testid =
    gap.status === "written"
      ? "gap-written"
      : gap.status === "deferred" || gap.choice === "延后"
        ? "gap-deferred"
        : gap.status === "edited" || gap.choice === "改段"
          ? "gap-edited"
          : "gap-active";

  return (
    <div className={`cr-gap${open && gap.choice === "加人" ? "" : " done"}`} data-testid={testid}>
      <div className="g-head">
        <b>
          {gap.label} · 缺一个新角色
        </b>
        <span className={`pill ${pill.cls}`}>{pill.tx}</span>
      </div>
      <p className="g-why">
        这段戏缺的是：{gap.need}。
        <br />
        老角色为什么不行：<b>{gap.whyNotOld}</b>
      </p>

      {/* 三选一（预填=suggest；「AI 建议」/「默认」标随改选消失） */}
      {gap.status !== "written" && (
        <div className="cr-pick" role="radiogroup" aria-label="这段戏缺的人怎么处理">
          <span className="k">
            怎么处理
            <span className="opt">（AI 预填可改）</span>
          </span>
          {CHOICES.map((c) => {
            const on = gap.choice === c;
            return (
              <button
                key={c}
                className={`cr-opt${on ? " on" : ""}`}
                role="radio"
                aria-checked={on}
                data-testid={CHOICE_TESTID[c]}
                onClick={() => cast.setChoice(gap.gapId, c)}
              >
                {c}
                {on && !gap.touched && (
                  <span className="cr-sug" data-testid="cr-sug">
                    {gap.defaulted ? "默认" : "AI 建议"}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {gap.status === "written" ? (
        <>
          <p className="g-why" data-testid="gap-written-line">
            已写入：{gap.writtenName}
            {gap.writtenWithCard
              ? "——建卡并写入章纲。角色表、本章出场角色、本卷出场清单都加了。"
              : gap.writtenExisting
                ? "——选的已有角色卡，名字写进本章名单（不重复建卡）。"
                : "——只加名单（暂未建卡）。本章出场角色多一行名字。"}
          </p>
          <p className="g-done">
            <span className="rp-dot" aria-hidden="true" />
            这个缺的人处理完了；
            {remaining > 0
              ? `本章还有 ${remaining} 个缺的人没处理。`
              : "本章的缺的人都处理完了，可以关掉弹窗。"}
          </p>
        </>
      ) : gap.choice === "改段" ? (
        <div className="g-act">
          <span className="cr-done" data-testid="cr-done-note">
            这次盘点里就算处理过了，不做记录——去改{gap.label}那一条。
          </span>
          <button className="btn btn-secondary btn-sm" data-testid="cr-go-edit" onClick={cast.close}>
            关掉弹窗，去改剧情
          </button>
        </div>
      ) : gap.choice === "延后" ? (
        <div className="g-act">
          <span className="cr-done" data-testid="cr-done-note">
            这次盘点里就算处理过了，不做记录——你自己把这段剧情挪到哪一章，就在哪一章再遇到。
          </span>
        </div>
      ) : (
        <div className="g-act">
          {isPro ? (
            <button
              className="btn btn-primary btn-sm"
              data-testid="cr-draw"
              onClick={() => cast.startDraw(gap.gapId)}
            >
              抽卡选人
            </button>
          ) : (
            <button className="btn btn-primary btn-sm" data-testid="cr-draw-locked" disabled>
              抽卡选人
            </button>
          )}
          <span className="ai-tag">PRO</span>
          <button className="lnk" data-testid="cr-fill-manual" onClick={() => cast.fillManual(gap.gapId)}>
            不抽了，自己填一个名字
          </button>
          <button
            className="lnk"
            data-testid="cr-pick-existing"
            onClick={() => setPicking((p) => !p)}
          >
            选已有角色
          </button>
        </div>
      )}
      {picking && open && gap.choice === "加人" && (
        <div className="cr-existing" data-testid="cr-existing">
          <span className="cr-done">
            点谁就让谁上这段戏：名字进本章出场名单，不新建卡、不花 AI。
          </span>
          <div className="cr-exist-row">
            {roster.length === 0 ? (
              <span className="cr-done" data-testid="cr-exist-empty">
                书里还没有角色卡——去设定页建一张，或用上面两种方式直接加人。
              </span>
            ) : (
              roster.map((n) => {
                const inCast = castLines.includes(n);
                return (
                  <button
                    key={n}
                    className="chip"
                    disabled={inCast || state.writing}
                    data-testid={`cr-exist-${n}`}
                    title={
                      inCast
                        ? "已在本章出场名单"
                        : "选 TA 演这段戏：名字进本章出场名单，不新建卡、不花 AI"
                    }
                    onClick={() => void cast.pickExisting(gap.gapId, n)}
                  >
                    {n}
                    {inCast && <span className="no-card">已在名单</span>}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* 免费锁（按钮级，无假卡面）：升级出口＋自己填全免费 */}
      {!isPro && open && gap.choice === "加人" && (
        <div className="lock-card" data-testid="cr-lock">
          <b>AI 抽人是 PRO 功能</b>
          <p>
            AI 能按这段戏缺的人一次给 3 个互不相同的人物方向——叫什么、什么性格、怎么出场怎么退场都配好，挑一个直接用。
            缺的人自己填全免费：在出场名单里直接加名字、建角色卡都不要钱。
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" data-testid="cr-upgrade" onClick={onUpgrade}>
              升级 PRO
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => cast.fillManual(gap.gapId)}>
              自己填一个
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
