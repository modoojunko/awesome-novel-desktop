// VolumePlanModal — 四问手写页（c-volume-antagonist 免费路径/付费转手写）。
// 四问：①讲什么②主要冲突③这一卷的坎（类型＋一句话）④卷末收在哪里；
// 底部两动作：「让 AI 铺完剩下的问题」（PRO）＋「直接创建这一卷」（免费）。
// 手动入口（各处「＋ 新增一卷」，state.openMode==="manual"）下 SHALL NOT 出现 AI 动作：
// 手写页只留「直接创建这一卷」，AI 铺空缺改由右栏 AI 助手入口进（用户 2026-09-22 拍板）。
// 生成中 genbox 进度只在弹窗内；关弹窗不中断（完成后中栏自动回填）。
import { useEffect } from "react";
import Modal from "@/components/design/Modal";
import { api } from "@/lib/api";
import { cnNum } from "@/lib/nodeTitle";
import { GEN_STEPS, type VolumePlanController } from "@/hooks/useVolumePlan";

const ANT_TYPES = ["先不选", "人物", "难题", "环境", "自我", "势力"] as const;

const RULES_FOR_AUTHOR = [
  "不凭空添人添事：只用你设定里已有的人物、势力、事件和地点。",
  "接着上一卷的结尾往下写，不跳空——第一卷从你写的起步开始。",
  "这一卷要解决的事，得是全书主线走到这一步该解决的事，不另开一条线。",
  "卷末要给读者一个交代，同时把故事朝你写的那个结局推近一步。",
  "不跟你的设定打架：人物性格、世界规矩、已经埋下的伏笔。",
  "伏笔不重复埋、不提前揭；埋下的说清打算哪一卷收。",
  "只把你的那句话铺成结构，不替你改走向——有冲突它会说出来。",
  "每卷都要有自己的小高潮：卷末点出这一卷的高潮事件和大致位置，再写交代。",
];

export function VolumePlanModal({
  projectId,
  plan,
  isPro,
  onUpgrade,
  onDirectCreate,
  onBackfill,
  onClose,
  onGoSettings,
  creating = false,
}: {
  projectId: string;
  plan: VolumePlanController;
  isPro: boolean;
  onUpgrade: () => void;
  /** 免费路：答多少建多少（外层走 createVolume 四问扩展） */
  onDirectCreate: () => void;
  onBackfill: () => void;
  onClose: () => void;
  onGoSettings?: () => void;
  /** 建卷请求在途（双发闸，c-silent-data-guards） */
  creating?: boolean;
}) {
  const { state, setAnswer, expandDesk, resetError } = plan;
  const cn = cnNum(state.volNo);
  const first = state.volNo <= 1;

  useEffect(() => {
    if (!state.deskOpen) resetError();
  }, [state.deskOpen, resetError]);

  /** 手动入口（加号）＝纯手写页：不出现任何 AI 动作与 AI 承诺文案 */
  const manual = state.openMode === "manual";
  const genBusy = state.deskPhase === "generating";
  const genDone = state.deskPhase === "done" && state.draft && !state.degradedText;

  return (
    <Modal open={state.deskOpen} onClose={onClose} title={`规划第${cn}卷`} width={680} wbStyle>
      <div className="plan-modal" data-testid="volume-plan-modal">
        <p className="kicker">分卷规划 · 第{cn}卷</p>

        <p className="plans-h" style={{ marginTop: 12 }}>
          {manual
            ? "四个问题 · 答得出就答，答不出的可以空着"
            : "四个问题 · 答得出就答，答不出的交给 AI"}
        </p>

        <div className="fro">
          <em>
            <span className="qno">1</span>这一卷讲什么？ <span className="note">{manual ? "可空" : "可空——空着 AI 按设定推"}</span>
          </em>
          <textarea
            className="textarea"
            rows={2}
            maxLength={150}
            data-testid="q-what"
            placeholder={first ? "例：她为追信号把坐标押给船队，欠下一条命" : "一句话说清：接着上一卷的结尾，谁想干什么"}
            value={state.answers.q1}
            onChange={(e) => setAnswer("q1", e.target.value)}
          />
        </div>
        <div className="fro">
          <em>
            <span className="qno">2</span>主要冲突是什么？ <span className="note">想做什么，被什么拦住</span>
          </em>
          <textarea
            className="textarea"
            rows={2}
            maxLength={150}
            data-testid="q-conflict"
            placeholder="例：想只靠自己，可补给单上没有她的名字"
            value={state.answers.conflict}
            onChange={(e) => setAnswer("conflict", e.target.value)}
          />
        </div>
        <div className="fro">
          <em>
            <span className="qno">3</span>这一卷的坎是谁／是什么？{" "}
            <span className="note">反派 · 难题 · 环境 · 自我——卷与卷要递进</span>
          </em>
          <div className="hurdle-row">
            <select
              className="input"
              data-testid="q-ant-type"
              value={state.answers.antagonist_type}
              onChange={(e) => setAnswer("antagonist_type", e.target.value)}
            >
              {ANT_TYPES.map((t) => (
                <option key={t} value={t === "先不选" ? "" : t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              className="input"
              maxLength={150}
              data-testid="q-ant-line"
              placeholder="例：体内饥渴——越压越饿，还是得用它"
              value={state.answers.antagonist_line}
              onChange={(e) => setAnswer("antagonist_line", e.target.value)}
            />
          </div>
        </div>
        <div className="fro">
          <em>
            <span className="qno">4</span>卷末收在哪里？ <span className="note">这一卷结束时，局面变成什么样</span>
          </em>
          <textarea
            className="textarea"
            rows={2}
            maxLength={300}
            data-testid="q-ending"
            placeholder="例：没有退路，也没有人可以怪"
            value={state.answers.q4}
            onChange={(e) => setAnswer("q4", e.target.value)}
          />
        </div>

        <div className="plan-desk-acts">
          {!manual && (
            <button
              className="btn btn-primary"
              data-testid="desk-expand"
              disabled={!isPro || state.error.includes("主线")}
              title={isPro ? undefined : "铺空缺需 PRO——升级后可用"}
              onClick={() => void expandDesk()}
            >
              让 AI 铺完剩下的问题
            </button>
          )}
          <button
            className="btn btn-secondary"
            data-testid="desk-create"
            disabled={creating}
            onClick={onDirectCreate}
          >
            {creating ? "创建中…" : "直接创建这一卷"}
          </button>
          <span className="push">
            {manual ? (
              "想让 AI 铺空缺：用右侧 AI 助手的「规划第N卷（AI）」"
            ) : isPro ? (
              "你答过的它不改——AI 只铺空着的"
            ) : (
              <>
                <span className="pill-pro">PRO</span>
                <span>铺空缺需 PRO；手写与创建不受限</span>
                <button className="btn btn-ghost btn-sm" onClick={onUpgrade}>
                  了解升级
                </button>
              </>
            )}
          </span>
        </div>

        {state.error && (
          <p className="ai-note" style={{ color: "var(--warn)" }} data-testid="desk-error">
            {state.error}
            {state.error.includes("主线") && "（回到设定 → 主线）"}
          </p>
        )}
        {state.degradedText && (
          <div data-testid="desk-degraded" className="plans">
            <p className="plans-h">AI 的输出没法结构化</p>
            <p className="ai-note">{state.degradedText}</p>
            <p className="ai-note">{state.hint || "可重试，或按上面这段手动定走向"}</p>
          </div>
        )}

        {genBusy && (
          <div className="genbox" data-testid="desk-generating">
            <p className="gen-k">正在铺第{cn}卷</p>
            <p className="gen-t">
              按你答过的＋你的全书设定，把空着的问题铺上——冲突、卷末、坎与伏笔建议。
            </p>
            <ul className="ex-steps">
              {GEN_STEPS.map((s) => (
                <li key={s}>
                  <span>{s}</span>
                  <em>
                    <span className="ra-spin" aria-hidden="true" />
                    进行中
                  </em>
                </li>
              ))}
            </ul>
          </div>
        )}

        {genDone && (
          <div className="genbox" data-testid="desk-done">
            <p className="gen-k">第{cn}卷的卷纲已备好</p>
            <p className="gen-t">
              {state.draft!.name || "（卷名待定）"} · 建议{" "}
              {state.draft!.chapter_target > 0 ? state.draft!.chapter_target : "—"} 章 · 自查{" "}
              {state.draft!.checks.length} 处要留意。点「回填」，它会一条条写进中栏的卷纲表单——你改完再保存。
            </p>
          </div>
        )}

        <div className="plan-foot">
          {genDone ? (
            <>
              <span className="note">点「回填」，卷纲会在中栏一条条落下来</span>
              <button className="btn btn-sm btn-primary" data-testid="desk-backfill" onClick={onBackfill}>
                回填 →
              </button>
            </>
          ) : genBusy ? (
            <>
              <span className="note">生成在后台跑，关掉它也不影响</span>
              <button className="btn btn-sm btn-secondary" onClick={onClose}>
                关掉
              </button>
            </>
          ) : (
            <>
              <span className="note">
                规划台里的东西不会自己进书；卷名最后起；卷与卷之间留着没写到的部分，是正常的。
              </span>
              <button className="btn btn-sm btn-secondary" onClick={onClose}>
                先不规划
              </button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
