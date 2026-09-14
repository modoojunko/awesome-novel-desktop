// 章纲面板（book.html renderOgPane 复刻）：5 个 details.cfg 字段组全字段
// + 主情绪选择（9 选 + 自定义 ≤50）+ 段落规划行（增删/上移/合计）
// + 提示词格子（ai-prompt-crafting）：场景卡行（名/目标/阻碍/钩子 + 权重 + 焦点）、
// 读者获得列表（7 类型 + 描述 + 前中后位置）、章末落点、本章目标字数。
// 确认缺读者获得时仅提醒不阻断（存量章不回溯）。
// + gap-line 缺字段 chip（点击滚动 flash 1400ms + focus）+ 底部三按钮。
// 必填口径 = 后端 gate_chapter_ready 六项（task/rstate/rstrat/changes/mood/segs）。
import { useState } from "react";
import {
  PAYOFF_KINDS,
  PAYOFF_LOCATIONS,
  SCENE_FOCUS,
  SCENE_WEIGHTS,
  type OgForm,
  type OgPayoff,
  type OgScene,
} from "./chapterForm";

interface OgPaneProps {
  form: OgForm;
  /** 本书角色名清单（character-settings-v2）：出场角色多选候选取这里 */
  characterNames?: string[];
  /** 完整章标题（第X章 · 名称，nodeLabel 派生）——原型 panel-head 口径 */
  label: string;
  /** 信息差对齐只读块（PR6）：卷级起止 + 本章规划行；null = 卷未配置，不渲染 */
  infoGap?: { volStart: string; volEnd: string; chapterGap: string } | null;
  onPatch: (patch: Partial<OgForm>) => void;
  gaps: { key: string; label: string }[];
  confirmed: boolean;
  saving: boolean;
  onSaveDraft: () => void;
  onConfirm: () => void;
  onGoWrite: () => void;
  /** AI 起草（outline-ai-draft）：免费态不渲染入口；表单有内容时由上层 confirm */
  canAiDraft?: boolean;
  aiDrafting?: boolean;
  onAiDraft?: () => void;
}

const MOODS = ["紧张", "悬疑", "温暖", "悲伤", "激昂", "轻松", "压抑", "浪漫", "惊悚"];

function flashField(key: string) {
  const el = document.getElementById(`wf-${key}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1400);
  const focusable = el.querySelector("input, textarea, select") as HTMLElement | null;
  focusable?.focus({ preventScroll: true });
}

export default function OgPane({
  form,
  characterNames,
  label,
  infoGap,
  onPatch,
  gaps,
  confirmed,
  saving,
  onSaveDraft,
  onConfirm,
  onGoWrite,
  canAiDraft,
  aiDrafting,
  onAiDraft,
}: OgPaneProps) {
  const moodVal = form.mood || "";
  const moodCustom = moodVal && !MOODS.includes(moodVal) ? moodVal : "";
  const moodSel = moodCustom ? "__custom" : moodVal;
  const segTotal = form.segs.reduce((a, s) => a + (parseInt(String(s.w), 10) || 0), 0);
  const payoffFilled = form.payoffs.some((p) => p.d.trim());
  // 缺读者获得的确认提醒：一次会话提醒一次，不阻断确认（存量章不回溯）
  const [payoffReminded, setPayoffReminded] = useState(false);
  const showPayoffHint = payoffReminded && !payoffFilled;

  const patchScene = (i: number, patch: Partial<OgScene>) => {
    const scenes = form.scenes.slice();
    scenes[i] = { ...scenes[i], ...patch };
    onPatch({ scenes });
  };
  const patchPayoff = (i: number, patch: Partial<OgPayoff>) => {
    const payoffs = form.payoffs.slice();
    payoffs[i] = { ...payoffs[i], ...patch };
    onPatch({ payoffs });
  };

  return (
    <div className="og-pane">
      <div className="panel">
        <div className="panel-head">
          <h2>章纲 · {label}</h2>
          {canAiDraft && onAiDraft ? (
            <button
              className="btn btn-secondary btn-sm"
              data-testid="og-ai-draft"
              disabled={aiDrafting || saving}
              onClick={onAiDraft}
            >
              {aiDrafting ? "AI 起草中…" : "AI 起草"}
            </button>
          ) : null}
          {confirmed ? (
            <span className="badge ok">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <path d="M5 13l4 4L19 7" />
              </svg>
              章纲已确认
            </span>
          ) : gaps.length ? (
            <span className="badge err">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
              </svg>
              待配章纲
            </span>
          ) : (
            <span className="badge warn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
              </svg>
              草稿
            </span>
          )}
        </div>
        <p className="desc">章纲：明确「这一章写什么」，确认后可作为 AI 生成正文的章级上下文。</p>

        {infoGap ? (
          <div className="og-infogap" data-testid="og-info-gap">
            {infoGap.volStart || infoGap.volEnd ? (
              <div className="ig-row">
                <span className="ig-k">本卷信息差</span>
                <span className="ig-v">
                  {infoGap.volStart || "（未设起点）"} → {infoGap.volEnd || "（未设终点）"}
                </span>
              </div>
            ) : null}
            {infoGap.chapterGap ? (
              <div className="ig-row">
                <span className="ig-k">本章信息差</span>
                <span className="ig-v">{infoGap.chapterGap}</span>
              </div>
            ) : null}
          </div>
        ) : null}

        <details className="cfg" open>
          <summary>
            章纲概要 <Chev />
          </summary>
          <div className="inner">
            <div className="field">
              <label>章纲概要</label>
              <textarea
                className="textarea"
                id="wf-summary"
                placeholder="这一章写什么，一两句话说清"
                value={form.summary}
                onChange={(e) => onPatch({ summary: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                关键事件 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-keys"
                placeholder="一个关键事件"
                value={form.keys}
                onChange={(e) => onPatch({ keys: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                出场角色 <span className="opt">点选角色卡；也可直接输入名字</span>
              </label>
              {characterNames && characterNames.length > 0 && (
                <div className="og-char-picker" role="group" aria-label="从角色卡选择出场角色">
                  {characterNames.map((n) => {
                    const on = form.chars.split("\n").some((line) => line.trim() === n);
                    return (
                      <button
                        key={n}
                        type="button"
                        className={`chip${on ? " on" : ""}`}
                        onClick={() => {
                          const lines = form.chars
                            .split("\n")
                            .map((x) => x.trim())
                            .filter(Boolean);
                          const next = on
                            ? lines.filter((x) => x !== n)
                            : [...lines, n];
                          onPatch({ chars: next.join("\n") });
                        }}
                      >
                        {n}
                      </button>
                    );
                  })}
                </div>
              )}
              <textarea
                className="textarea"
                id="wf-chars"
                placeholder="角色名（一行一个）"
                value={form.chars}
                onChange={(e) => onPatch({ chars: e.target.value })}
              />
            </div>
            <div className="tpl-row">
              <div className="field tpl-select">
                <label>地点</label>
                <input
                  className="input"
                  id="wf-loc"
                  placeholder="本章主要场景地点"
                  value={form.loc}
                  onChange={(e) => onPatch({ loc: e.target.value })}
                />
              </div>
              <div className="field stage-map">
                <label>时间</label>
                <input
                  className="input"
                  id="wf-time"
                  placeholder="本章时间背景"
                  value={form.time}
                  onChange={(e) => onPatch({ time: e.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label>叙事视角</label>
              <input
                className="input"
                id="wf-pov"
                placeholder="如：第三人称有限"
                value={form.pov}
                onChange={(e) => onPatch({ pov: e.target.value })}
              />
            </div>
            <div className="field">
              <label>视角指导</label>
              <textarea
                className="textarea"
                id="wf-pguid"
                placeholder="视角切换注意事项"
                value={form.pguid}
                onChange={(e) => onPatch({ pguid: e.target.value })}
              />
            </div>
          </div>
        </details>

        <details className="cfg" open>
          <summary>
            核心任务 <Chev />
          </summary>
          <div className="inner">
            <div className="field">
              <label>
                核心任务 <span className="req">*</span>
              </label>
              <textarea
                className="textarea"
                id="wf-task"
                placeholder="这一章必须完成什么"
                value={form.task}
                onChange={(e) => onPatch({ task: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                读者当前状态 <span className="req">*</span>
              </label>
              <textarea
                className="textarea"
                id="wf-rstate"
                placeholder="读者此时的情感状态"
                value={form.rstate}
                onChange={(e) => onPatch({ rstate: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                预期策略 <span className="req">*</span>
              </label>
              <textarea
                className="textarea"
                id="wf-rstrat"
                placeholder="希望读者如何感受"
                value={form.rstrat}
                onChange={(e) => onPatch({ rstrat: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                预期细节说明 <span className="opt">可后补</span>
              </label>
              <textarea
                className="textarea"
                id="wf-rdetail"
                placeholder="策略的展开方式与分寸"
                value={form.rdetail}
                onChange={(e) => onPatch({ rdetail: e.target.value })}
              />
            </div>
          </div>
        </details>

        <details className="cfg" open>
          <summary>
            兑现与约束 <Chev />
          </summary>
          <div className="inner">
            <div className="field">
              <label>
                必须在本章回收 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-mres"
                placeholder="一个必须回收的伏笔"
                value={form.mres}
                onChange={(e) => onPatch({ mres: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                必须维持悬念 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-mhold"
                placeholder="一个必须维持的悬念"
                value={form.mhold}
                onChange={(e) => onPatch({ mhold: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                可部分推进 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-padv"
                placeholder="一个可部分推进的线索"
                value={form.padv}
                onChange={(e) => onPatch({ padv: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                必须完成的变化 <span className="req">*</span>
              </label>
              <textarea
                className="textarea"
                id="wf-changes"
                placeholder="一个必须发生的变化"
                value={form.changes}
                onChange={(e) => onPatch({ changes: e.target.value })}
              />
            </div>
            <div className="field">
              <label>
                禁止事项 <span className="opt">一行一个</span>
              </label>
              <textarea
                className="textarea"
                id="wf-ban"
                placeholder="一个禁止发生的事"
                value={form.ban}
                onChange={(e) => onPatch({ ban: e.target.value })}
              />
            </div>
          </div>
        </details>

        <details className="cfg" open>
          <summary>
            情绪设计 <Chev />
          </summary>
          <div className="inner">
            <div className="field" id="wf-mood">
              <label>
                主情绪 <span className="req">*</span>
              </label>
              <div className="mood-row">
                <select
                  className="input"
                  value={moodSel}
                  onChange={(e) => {
                    const v = e.target.value;
                    onPatch({ mood: v === "__custom" ? "" : v });
                  }}
                >
                  <option value="">请选择主情绪</option>
                  {MOODS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  <option value="__custom">自定义…</option>
                </select>
                {moodSel === "__custom" && (
                  <input
                    className="input"
                    placeholder="输入自定义情绪（≤50 字）"
                    maxLength={50}
                    value={moodCustom}
                    onChange={(e) => onPatch({ mood: e.target.value })}
                  />
                )}
              </div>
            </div>
          </div>
        </details>

        <details className="cfg" id="wf-scenes">
          <summary>
            场景卡 <span className="opt">提示词原材料 · 可空</span>
            <Chev />
          </summary>
          <div className="inner">
            <p
              className="note"
              style={{ fontSize: "12.5px", color: "var(--muted)", margin: "0 0 10px" }}
            >
              每卡一条外部动作链（目标 → 阻碍 → 钩子）；权重决定笔墨分配，焦点决定展开方向。
            </p>
            <div className="seg-list" data-testid="scene-list">
              {form.scenes.map((sc, i) => (
                <div className="scene-card" key={i} data-scene={i}>
                  <div className="scene-head">
                    <span className="num seg-i">{i + 1}</span>
                    <input
                      className="input"
                      data-scene="n"
                      placeholder="场景名，如：酒馆对峙"
                      value={sc.n}
                      onChange={(e) => patchScene(i, { n: e.target.value })}
                    />
                    <select
                      className="input"
                      data-scene="w"
                      title="权重（笔墨分配）"
                      value={sc.w}
                      onChange={(e) => patchScene(i, { w: e.target.value as OgScene["w"] })}
                    >
                      <option value="">权重</option>
                      {SCENE_WEIGHTS.map((x) => (
                        <option key={x.value} value={x.value}>
                          {x.label}
                        </option>
                      ))}
                    </select>
                    <select
                      className="input"
                      data-scene="f"
                      title="焦点（展开方向）"
                      value={sc.f}
                      onChange={(e) => patchScene(i, { f: e.target.value as OgScene["f"] })}
                    >
                      <option value="">焦点</option>
                      {SCENE_FOCUS.map((f) => (
                        <option key={f} value={f}>
                          {f}
                        </option>
                      ))}
                    </select>
                    <span className="acts">
                      <button
                        className="icon-btn"
                        title="上移"
                        disabled={i === 0}
                        onClick={() => {
                          const scenes = form.scenes.slice();
                          const [x] = scenes.splice(i, 1);
                          scenes.splice(i - 1, 0, x);
                          onPatch({ scenes });
                        }}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M6 15l6-6 6 6" />
                        </svg>
                      </button>
                      <button
                        className="icon-btn"
                        title="删除场景卡"
                        onClick={() => {
                          const scenes = form.scenes.slice();
                          scenes.splice(i, 1);
                          onPatch({ scenes });
                        }}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                        </svg>
                      </button>
                    </span>
                  </div>
                  <div className="scene-chain">
                    <input
                      className="input"
                      data-scene="g"
                      placeholder="目标（他想要什么）"
                      value={sc.g}
                      onChange={(e) => patchScene(i, { g: e.target.value })}
                    />
                    <input
                      className="input"
                      data-scene="o"
                      placeholder="阻碍（谁/什么拦住他）"
                      value={sc.o}
                      onChange={(e) => patchScene(i, { o: e.target.value })}
                    />
                    <input
                      className="input"
                      data-scene="h"
                      placeholder="钩子（留什么悬念）"
                      value={sc.h}
                      onChange={(e) => patchScene(i, { h: e.target.value })}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="seg-add-row">
              <button
                className="btn btn-secondary btn-sm sub-add"
                data-add="scene"
                onClick={() =>
                  onPatch({ scenes: [...form.scenes, { n: "", g: "", o: "", h: "", w: "", f: "" }] })
                }
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                添加场景卡
              </button>
            </div>
          </div>
        </details>

        <details className="cfg" id="wf-payoffs">
          <summary>
            读者获得与章末落点 <span className="opt">提示词原材料 · 可空</span>
            <Chev />
          </summary>
          <div className="inner">
            <p
              className="note"
              style={{ fontSize: "12.5px", color: "var(--muted)", margin: "0 0 10px" }}
            >
              读者获得 = 本章给读者的爽点（拿到什么/看清什么/情绪被什么击中）。
            </p>
            {showPayoffHint && (
              <p
                className="note"
                data-testid="payoff-hint"
                style={{ fontSize: "12.5px", color: "var(--warn, #b8860b)", margin: "0 0 10px" }}
              >
                本章未设置读者获得——可后补，不拦截确认。
              </p>
            )}
            <div className="seg-list" data-testid="payoff-list">
              {form.payoffs.map((mp, i) => (
                <div className="payoff-row" key={i} data-payoff={i}>
                  <select
                    className="input"
                    data-payoff="k"
                    title="类型"
                    value={mp.k}
                    onChange={(e) => patchPayoff(i, { k: e.target.value })}
                  >
                    {PAYOFF_KINDS.map((x) => (
                      <option key={x.value} value={x.value}>
                        {x.label}
                      </option>
                    ))}
                  </select>
                  <input
                    className="input"
                    data-payoff="d"
                    placeholder="一句话描述，如：主角拿到半块玉佩"
                    value={mp.d}
                    onChange={(e) => patchPayoff(i, { d: e.target.value })}
                  />
                  <select
                    className="input"
                    data-payoff="l"
                    title="位置"
                    value={mp.l}
                    onChange={(e) => patchPayoff(i, { l: e.target.value as OgPayoff["l"] })}
                  >
                    <option value="">位置</option>
                    {PAYOFF_LOCATIONS.map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </select>
                  <span className="acts">
                    <button
                      className="icon-btn"
                      title="删除"
                      onClick={() => {
                        const payoffs = form.payoffs.slice();
                        payoffs.splice(i, 1);
                        onPatch({ payoffs });
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                      </svg>
                    </button>
                  </span>
                </div>
              ))}
            </div>
            <div className="seg-add-row">
              <button
                className="btn btn-secondary btn-sm sub-add"
                data-add="payoff"
                onClick={() =>
                  onPatch({ payoffs: [...form.payoffs, { k: "clue", d: "", l: "" }] })
                }
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                添加读者获得
              </button>
            </div>
            <div className="tpl-row">
              <div className="field">
                <label>
                  章末落点 <span className="opt">结尾停在哪个紧张度上</span>
                </label>
                <input
                  className="input"
                  id="wf-ladder"
                  placeholder="如：拿到半张地图，连夜出门，更不安"
                  value={form.ladder}
                  onChange={(e) => onPatch({ ladder: e.target.value })}
                />
              </div>
              <div className="field">
                <label>
                  本章目标字数 <span className="opt">500-6000，留空默认 2500</span>
                </label>
                <input
                  className="input num"
                  id="wf-wt"
                  type="number"
                  min={500}
                  max={6000}
                  step={100}
                  placeholder="2500"
                  value={form.wt}
                  onChange={(e) => onPatch({ wt: e.target.value })}
                />
              </div>
            </div>
          </div>
        </details>

        <details className="cfg" id="wf-segs" open>
          <summary>
            段落规划 <span className="req">*</span>{" "}
            <span className="tag">章内节奏拆解；正文按整章生成</span>
            <Chev />
          </summary>
          <div className="inner">
            <div className="seg-list">
              {form.segs.length === 0 && (
                <p
                  className="note"
                  style={{ fontSize: "12.5px", color: "var(--muted)", margin: "0 0 10px" }}
                >
                  尚未规划段落 · 至少一段才能确认章纲
                </p>
              )}
              {form.segs.map((s, i) => (
                <div className="seg-row" key={i}>
                  <span className="num seg-i">{i + 1}</span>
                  <textarea
                    className="input"
                    data-seg="s"
                    rows={2}
                    placeholder="段落概要，如：港区之夜 · 信标亮起"
                    value={s.s}
                    onChange={(e) => {
                      const segs = form.segs.slice();
                      segs[i] = { ...segs[i], s: e.target.value };
                      onPatch({ segs });
                    }}
                  />
                  <input
                    className="input num"
                    data-seg="w"
                    type="number"
                    min={100}
                    step={100}
                    value={s.w}
                    onChange={(e) => {
                      const segs = form.segs.slice();
                      segs[i] = { ...segs[i], w: parseInt(e.target.value, 10) || 0 };
                      onPatch({ segs });
                    }}
                  />
                  <span className="acts">
                    <button
                      className="icon-btn"
                      title="上移"
                      disabled={i === 0}
                      onClick={() => {
                        const segs = form.segs.slice();
                        const [x] = segs.splice(i, 1);
                        segs.splice(i - 1, 0, x);
                        onPatch({ segs });
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M6 15l6-6 6 6" />
                      </svg>
                    </button>
                    <button
                      className="icon-btn"
                      title="删除段落"
                      onClick={() => {
                        const segs = form.segs.slice();
                        segs.splice(i, 1);
                        onPatch({ segs });
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                      </svg>
                    </button>
                  </span>
                </div>
              ))}
            </div>
            <div className="seg-add-row">
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onPatch({ segs: [...form.segs, { s: "", w: 800 }] })}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                添加段落
              </button>
              <span className="seg-total">
                合计 <b className="num">{segTotal.toLocaleString("zh-CN")}</b> 字
              </span>
            </div>
          </div>
        </details>

        <div className="panel-foot">
          {gaps.length > 0 ? (
            <span className="gap-line">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
              缺：
              {gaps.map((g) => (
                <span key={g.key} className="gap-chip" onClick={() => flashField(g.key)}>
                  {g.label}
                </span>
              ))}
            </span>
          ) : confirmed ? (
            <span className="done-note">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M5 13l4 4L19 7" />
              </svg>
              章纲已确认
            </span>
          ) : null}
          <span style={{ flex: 1 }} />
          <button className="btn btn-secondary" onClick={onSaveDraft} disabled={saving}>
            保存草稿
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              if (!payoffFilled) setPayoffReminded(true);
              onConfirm();
            }}
            disabled={confirmed || gaps.length > 0 || saving}
          >
            确认章纲
          </button>
          <button
            className="btn btn-primary"
            style={{ background: "var(--accent-strong)" }}
            onClick={onGoWrite}
            disabled={saving}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
            去写正文
          </button>
        </div>
      </div>
    </div>
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
