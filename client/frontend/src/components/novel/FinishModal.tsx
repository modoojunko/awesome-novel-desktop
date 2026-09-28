/**
 * 完本清单弹窗（works-finish-flow，works.html 原型 fin-* 家族 React 化）：
 * 完结前的最后一眼——三行检查（归档派生 / 伏笔真数据 / 收尾引导）＋完结动作；
 * 已完结态＝完结信息＋撤完本。
 *
 * 口径（design.md D4/D8）：
 *   - 伏笔「留白」勾选仅弹窗内辅助确认（useState，重开重置），SHALL NOT 写回伏笔表；
 *   - 不提「全书收尾后台跑」——归档收尾提案既有机制在书内「操作」页签逐条确认；
 *   - 完结/撤完本成功后回调页面本地更新（响应的 finished_at），不整表重拉。
 */
import { useCallback, useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import { Ico } from "@/components/icons";
import { api, errMessage } from "@/lib/api";
import { hooksApi, type HookEntry } from "@/lib/hooksApi";
import { toast } from "@/lib/toast";
import { parseServerTime } from "@/lib/serverTime";

export interface FinishTarget {
  id: string;
  name: string;
  total_volumes: number;
  total_chapters: number;
  word_count?: number;
  finished_at?: string | null;
  updated_at: string;
}

interface FinishModalProps {
  /** 非空＝弹窗打开；finished_at 非空＝已完结态 */
  target: FinishTarget | null;
  onClose: () => void;
  /** 完结成功（上抛端点完整响应，页面据 finished_at/updated_at 本地更新） */
  onFinished: (updated: { id: string; finished_at: string | null; updated_at: string }) => void;
  /** 撤完本成功（同上） */
  onReopened: (updated: { id: string; finished_at: string | null; updated_at: string }) => void;
}

const CHECK = "M5 13l4 4L19 7";
const fmt = (n: number) => n.toLocaleString("zh-CN");

export default function FinishModal({ target, onClose, onFinished, onReopened }: FinishModalProps) {
  const finished = !!target?.finished_at;
  const [hooks, setHooks] = useState<HookEntry[] | null>(null);
  const [hookChapter, setHookChapter] = useState<Map<string, number>>(new Map());
  /** 清单加载失败——失败不得呈现为「无伏笔」（c-silent-data-guards：确认钮禁用至重试成功） */
  const [hooksError, setHooksError] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  /** 留白标记：仅本弹窗内确认辅助，不落库 */
  const [parked, setParked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  // 打开（target 变化）即取数据：active 伏笔 + 卷章树（id→章号，「第 N 章埋下」）
  useEffect(() => {
    setHooks(null);
    setParked(new Set());
    setHooksError(false);
    if (!target || target.finished_at) return;
    let alive = true;
    hooksApi
      .list(target.id)
      .then((d) => {
        if (!alive) return;
        setHooks(d.items.filter((h) => h.status === "active"));
      })
      .catch(() => {
        if (alive) setHooksError(true); // 失败≠没有伏笔：不再静默置空数组
      });
    hooksApi
      .volumes(target.id)
      .then((vols) => {
        if (!alive) return;
        const m = new Map<string, number>();
        for (const v of vols) for (const c of v.chapters || []) if (c.id) m.set(c.id, c.chapter);
        setHookChapter(m);
      })
      .catch(() => {
        if (alive) setHooksError(true);
      });
    return () => {
      alive = false;
    };
  }, [target?.id, target?.finished_at, reloadTick]);

  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  const doFinish = useCallback(async () => {
    if (!target) return;
    setBusy(true);
    try {
      const updated = await api.finishNovel(target.id);
      toast.success(`《${target.name}》已完结 · 归档收尾提案可在「设定 / 伏笔」页签逐条确认`);
      onFinished(updated);
      onClose();
    } catch (e) {
      // 守卫 409 或网络异常：透出服务端 detail（如「这本书已完结，不用重复完本」——
      // 分组头「去完本」入口使「已完结 409」可达，不能只报「未归档」）；无响应时回落，留在弹窗
      toast.error(errMessage(e, "完本前先把主线章节全部归档"));
    } finally {
      setBusy(false);
    }
  }, [target, onFinished, onClose]);

  const doReopen = useCallback(async () => {
    if (!target) return;
    setBusy(true);
    try {
      const updated = await api.reopenNovel(target.id);
      toast.success(`已撤完本 · 《${target.name}》回到待完本，可以接着写或加新章`);
      onReopened(updated);
      onClose();
    } catch (e) {
      toast.error(errMessage(e, "撤完本失败，请重试"));
    } finally {
      setBusy(false);
    }
  }, [target, onReopened, onClose]);

  if (!target) return null;

  const lead = finished
    ? `主线 ${target.total_chapters} 章 · ${target.total_volumes} 卷 · 约 ${fmt(target.word_count ?? 0)} 字 · 完结于${relDay(target.finished_at)}。`
    : `主线 ${target.total_chapters} 章 · ${target.total_volumes} 卷 · 约 ${fmt(target.word_count ?? 0)} 字都已归档。` +
      "完本是一个动作，按下后这本书标为已完结；收尾结论都留在这本书的「操作」页等你逐条确认。";

  return (
    <Modal
      open
      onClose={onClose}
      locked={busy}
      width={560}
      title={finished ? "已完结 · 全书收尾" : "完本 · 全书收尾"}
      footer={
        finished ? (
          <>
            <button className="btn btn-secondary" disabled={busy} onClick={() => void doReopen()}>
              撤完本 · 继续写
            </button>
            <button className="btn btn-primary" disabled={busy} onClick={onClose}>
              关闭
            </button>
          </>
        ) : (
          <>
            <button className="btn btn-secondary" disabled={busy} onClick={onClose}>
              再想想
            </button>
            <button
              className="btn btn-primary"
              disabled={busy || hooksError}
              data-testid="finish-confirm"
              onClick={() => void doFinish()}
            >
              完结这本书
            </button>
          </>
        )
      }
    >
      <h2 className="fin-title serif">{finished ? `《${target.name}》已完结` : `完结《${target.name}》？`}</h2>
      <p className="fin-lead">{lead}</p>

      {finished ? (
        <div className="fin-sec">
          <div className="fin-done">
            <span className="fin-ico ok">
              <Ico d={CHECK} />
            </span>
            <div>
              <b>已完结</b>
              <p>读者与编辑看到的状态是「已完结 · 连载结束」。想加新章或改结局，就先撤完本。</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="fin-sec">
          {/* ① 章节归档：判据与端点守卫同源（主线全归档才可能走到这里） */}
          <div className="fin-row">
            <span className="fin-ico ok">
              <Ico d={CHECK} />
            </span>
            <div className="fin-t">
              <b>章节已全部归档</b>
              <p>没有草稿、待写或拟定章，主线完整。</p>
            </div>
          </div>
          {/* ② 伏笔：active 真数据；留白＝弹窗内确认辅助，不写伏笔表 */}
          <div className="fin-row">
            <span className={"fin-ico" + ((hooksError || (hooks != null && hooks.length > 0)) ? " warn" : " ok")}>
              {hooksError || (hooks != null && hooks.length > 0) ? "!" : <Ico d={CHECK} />}
            </span>
            <div className="fin-t">
              <b>
                {hooksError
                  ? "伏笔清单没加载出来"
                  : hooks === null
                    ? "正在读取伏笔…"
                    : hooks.length > 0
                      ? `还有 ${hooks.length} 条伏笔悬着`
                      : "伏笔都已回收"}
              </b>
              <p>
                {hooksError
                  ? "为避免没核对伏笔就完本，请重新加载后再确认。"
                  : hooks !== null && hooks.length > 0
                    ? "下面是全书里埋下却还没回收的伏笔。确认是故意留白的就勾上，完本照常；否则先回去收掉。"
                    : "没有埋下未收的伏笔，这本书的线都收干净了。"}
              </p>
              {hooksError && (
                <button className="btn btn-ghost btn-sm" data-testid="finish-reload" onClick={reload}>
                  重新加载
                </button>
              )}
              {hooks !== null && hooks.length > 0 && (
                <ul className="fin-hooks">
                  {hooks.map((h) => {
                    const on = parked.has(h.id);
                    const ch = h.introduced_chapter_id ? hookChapter.get(h.introduced_chapter_id) : undefined;
                    return (
                      <button
                        type="button"
                        key={h.id}
                        className={"fin-hook" + (on ? " on" : "")}
                        aria-pressed={on}
                        onClick={() =>
                          setParked((prev) => {
                            const next = new Set(prev);
                            if (next.has(h.id)) next.delete(h.id);
                            else next.add(h.id);
                            return next;
                          })
                        }
                      >
                        <span className="mk">{on ? "留白" : "未收"}</span>
                        <span className="nm">{h.description}</span>
                        <span className="from">{ch != null ? `第 ${ch} 章埋下` : "埋下章未定"}</span>
                      </button>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
          {/* ③ 收尾：章级归档收尾提案既有机制，去「操作」页签确认（不建书级后台任务） */}
          <div className="fin-row">
            <span className="fin-ico ok">
              <Ico d={CHECK} />
            </span>
            <div className="fin-t">
              <b>归档收尾都已清</b>
              <p>每一章归档后的写回提案都处理完了；未处理的在「设定 / 伏笔」页签逐条确认。</p>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

/** 「完结于 X」文案口径与书架 relTime 一致：刚完结显示「刚刚」，其余落日期。 */
function relDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = parseServerTime(iso);
  const ms = Date.now() - t.getTime();
  if (ms < 60_000) return "刚刚";
  return t.toLocaleDateString("zh-CN");
}
