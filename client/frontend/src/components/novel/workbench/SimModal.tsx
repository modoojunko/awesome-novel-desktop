/** 「剧情推演」弹窗（storyline.html sim modal 复刻）：
 * 从上一章结尾按回合走一遍本章——每回合先替角色选一次走法（顺 / 拗），
 * 全部回合走完可「按这条走法收进章纲」（c-og-slim-v2：追加为本章一条剧情条目）。
 * 走法只作参考，不自动改动章纲；推演产物不落库。
 */
import { useCallback, useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import { runSimulation, type SimResult } from "@/lib/plotSim";
import { toast } from "@/lib/toast";

interface SimModalProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  /** 完整章标题（第X章 · 名称） */
  chapterLabel: string;
  /** 计划篇幅（章目标字数；未定显示「未定」） */
  planWords?: number;
  /** 收进章纲：把走法行追加为本章一条剧情条目（失败由上层 toast） */
  onAdopt: (strategyLine: string) => Promise<boolean>;
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

/** 走法 → 收进章纲的剧情条目行（原型 simAdopt 口径：任一回合一「拗」即中途接意外） */
export function strategyLineOf(picks: Record<number, "ok" | "warn">): string {
  const anyWarn = Object.values(picks).includes("warn");
  return anyWarn
    ? "推演走法 · 中途先接一次意外，再拉回主线"
    : "推演走法 · 顺着章纲节奏推进，不多加波折";
}

export default function SimModal({
  open,
  onClose,
  projectId,
  chapterRef,
  chapterLabel,
  planWords,
  onAdopt,
}: SimModalProps) {
  const [data, setData] = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState(1);
  const [picks, setPicks] = useState<Record<number, "ok" | "warn">>({});
  const [adopting, setAdopting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setStep(1);
    setPicks({});
    try {
      setData(await runSimulation(projectId, chapterRef));
    } catch (e) {
      setError((e as Error).message || "推演失败，请重试");
    } finally {
      setLoading(false);
    }
  }, [projectId, chapterRef]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const rounds = data?.rounds ?? [];
  const total = rounds.length;
  const done = total > 0 && step >= total;

  const next = () => {
    const cur = rounds[step - 1];
    if (cur && !picks[cur.n]) {
      toast.info("先替这一回合选一个走法，再往下推");
      return;
    }
    setStep((s) => Math.min(s + 1, total));
  };

  const adopt = async () => {
    const cur = rounds[step - 1];
    if (cur && !picks[cur.n]) {
      toast.info("先把这一回合的走法定下来，再收进章纲");
      return;
    }
    setAdopting(true);
    try {
      const ok = await onAdopt(strategyLineOf(picks));
      if (ok) {
        toast.success(`${chapterLabel}已按推演走法加了一条剧情`);
        onClose();
      }
    } finally {
      setAdopting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="剧情推演 · 按回合走一遍"
      wbStyle
      width={560}
      locked={adopting}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            关闭
          </button>
          <button
            className="btn btn-secondary"
            data-testid="sim-again"
            disabled={loading}
            onClick={() => void load()}
          >
            重新推演
          </button>
          {done ? (
            <button
              className="btn btn-primary"
              data-testid="sim-adopt"
              disabled={adopting}
              onClick={() => void adopt()}
            >
              {adopting ? "收进章纲…" : "按这条走法收进章纲"}
            </button>
          ) : (
            <button
              className="btn btn-primary"
              data-testid="sim-next"
              disabled={loading || total === 0}
              onClick={next}
            >
              推演下一个回合
            </button>
          )}
        </>
      }
    >
      <div className="sim-body" data-testid="sim-body">
        <p className="sim-ch">{chapterLabel}</p>
        <p className="sim-lead">
          以上一章的结尾为起点，用本章章纲的关键事件与出场角色，一回合一步往下推：每一回合先替角色做一次选择，再推到本章结尾。
        </p>

        {loading && <p className="sim-note">正在推演……</p>}
        {error && (
          <p className="sim-note">
            {error}
            <button className="btn btn-ghost btn-sm" onClick={() => void load()}>
              重试
            </button>
          </p>
        )}

        {data && !loading && (
          <>
            <ul className="sim-stats">
              <li>
                <span className="k">起点</span>
                <span className="v">
                  {data.prev_label === "开书" ? "开书" : `${data.prev_label}结尾`}
                </span>
              </li>
              <li>
                <span className="k">终点</span>
                <span className="v">{chapterLabel}</span>
              </li>
              <li>
                <span className="k">回合</span>
                <span className="v">{total} 回合</span>
              </li>
              <li>
                <span className="k">出场角色</span>
                <span className="v">{data.cast.length} 人</span>
              </li>
            </ul>

            <div className="sim-card">
              <p className="sim-card-t">推演的起与收</p>
              <ul className="sim-list">
                <li>
                  <b>承接上一章</b> · {data.entry}
                </li>
                <li>
                  <b>收束到本章</b> · {data.exit}
                </li>
                <li>
                  <b>计划篇幅</b> · {planWords ? `${fmt(planWords)} 字` : "未定"}
                </li>
              </ul>
            </div>

            {rounds.map((r, i) => {
              if (i >= step) {
                return (
                  <div className="sim-card" key={r.n} data-testid={`sim-round-${r.n}`}>
                    <p className="sim-card-t">回合 {r.n}</p>
                    <p className="sim-note">还没走到——推到这里才会展开。</p>
                  </div>
                );
              }
              const onNow = i === step - 1;
              const pick = picks[r.n];
              return (
                <div className="sim-card" key={r.n} data-testid={`sim-round-${r.n}`}>
                  <p className="sim-card-t">
                    回合 {r.n}
                    {onNow ? " · 待你定" : pick ? " · 已定" : ""}
                  </p>
                  <p className="sim-note">{r.at}</p>
                  <ul className="sim-list">
                    <li>
                      <b>关键事件</b> · {r.beat}
                    </li>
                    <li>
                      <b>在场</b> · {r.who}
                      {r.place ? ` · ${r.place}` : ""}
                      {r.time ? ` · ${r.time}` : ""}
                    </li>
                    <li>
                      <b>这一回合落下</b> · {r.shift}
                    </li>
                  </ul>
                  <div className="sim-acts">
                    {r.moves.map((m) => (
                      <button
                        key={m.tone}
                        className={`btn btn-sm${pick === m.tone ? " btn-primary" : ""}`}
                        data-testid={`sim-pick-${r.n}-${m.tone}`}
                        onClick={() => setPicks((p) => ({ ...p, [r.n]: m.tone }))}
                      >
                        {m.k} · {m.label}
                      </button>
                    ))}
                  </div>
                  {pick ? (
                    <p className="sim-note">
                      走法已定 · {pick === "ok" ? "顺" : "拗"}　
                      {pick === "ok" ? r.moves[0]?.out : r.moves[1]?.out}
                    </p>
                  ) : onNow ? (
                    <p className="sim-note">先替这一回合选一个走法，再往下推。</p>
                  ) : null}
                </div>
              );
            })}

            {!done && (
              <div className="sim-card">
                <p className="sim-card-t">还剩 {total - step} 回合</p>
                <p className="sim-note">
                  每定一步，推演就更贴近本章结尾；走法只作参考，不会自动改动章纲。
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
