/** 本章变化分区（c-chapter-dossier IA 对齐，09-28 用户拍板）：
 *  归档提取的变化**不设独立页签**——设定/物品/认知归「设定」页签（按子领域/角色分组），
 *  人物关系归「角色关系」页签；进度/失败/逃生阀只在操作页签归档卡。
 *  数据＝章作用域四域行（dossierApi）；只取已采纳进下一章提示词，未确认不进。 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  DOSSIER_CHANGED_EVENT,
  dossierApi,
  type DossierRow,
  type DossierState,
} from "@/lib/dossierApi";

/** 共用数据钩子：拉取＋提取中 3s 轮询＋终态补拉（两分区各自条件挂载，各自一份数据）。 */
function useDossierData(projectId: string, chapterRef: string) {
  const [data, setData] = useState<DossierState | null>(null);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await dossierApi.get(projectId, chapterRef));
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [projectId, chapterRef]);

  useEffect(() => {
    setData(null);
    void load();
  }, [load]);

  useEffect(() => {
    if (data?.extraction?.state !== "extracting") return;
    const t = setTimeout(() => void load(), 3000);
    return () => clearTimeout(t);
  }, [data, load]);

  const prevRef = useRef<string | null>(null);
  useEffect(() => {
    const st = data?.extraction?.state ?? null;
    if (prevRef.current === "extracting" && st && st !== "extracting") void load();
    prevRef.current = st;
  }, [data?.extraction?.state, load]);

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      await fn();
      await load();
      // 广播给角色关系图：剧情边随采纳/驳回即时翻面（虚线↔实线）
      window.dispatchEvent(new CustomEvent(DOSSIER_CHANGED_EVENT, { detail: { projectId, chapterRef } }));
    },
    [load, projectId, chapterRef],
  );

  return { data, loadError, act };
}

function RowBody({ r }: { r: DossierRow }) {
  switch (r.domain) {
    case "settings":
      return <>{`${r.area ? `${r.area}：` : ""}${r.content ?? ""}`}</>;
    case "relations":
      return (
        <>
          {`${r.owner ?? "?"} → ${r.other ?? "?"}：${r.rel_type ?? ""}${
            r.change_note ? `（${r.change_note}）` : ""
          }`}
        </>
      );
    case "items":
      return (
        <>
          {`${r.name ?? "?"}：${r.change_type ?? ""}${
            r.holder ? `，现在在 ${r.holder} 手中` : ""
          }`}
        </>
      );
    default:
      return (
        <>
          {`${r.character ?? "?"} ${r.learned ? "已得知" : "仍不知道"}「${r.fact ?? ""}」${
            r.learned ? "" : `（${r.character ?? "?"}不知）`
          }`}
        </>
      );
  }
}

/** 变化行：点行展开证据句；pending 有采纳/驳回，accepted 可删，rejected 可恢复。 */
function ChangeRow({
  projectId,
  chapterRef,
  r,
  busy,
  act,
}: {
  projectId: string;
  chapterRef: string;
  r: DossierRow;
  busy: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`ds-row${open ? " open" : ""}`} data-testid="change-row">
      <div onClick={() => setOpen((v) => !v)}>
        <RowBody r={r} />
        {r.flags.includes("evidence_unverified") && <span className="ds-flag">证据待核</span>}
        {r.flags.includes("unregistered") && <span className="ds-flag">未登记</span>}
      </div>
      <div className="ds-ev">证据：「{r.evidence || "（无）"}」（点击收起）</div>
      {r.status === "pending" ? (
        <div className="ds-actions">
          <button
            className="btn btn-primary btn-sm"
            disabled={busy}
            onClick={() =>
              void act(() => dossierApi.rowAction(projectId, chapterRef, r.id, "accept"))
            }
          >
            采纳
          </button>
          <button
            className="btn btn-ghost btn-sm"
            disabled={busy}
            onClick={() =>
              void act(() => dossierApi.rowAction(projectId, chapterRef, r.id, "reject"))
            }
          >
            驳回
          </button>
        </div>
      ) : r.status === "accepted" ? (
        <div className="ds-actions">
          <span className="cnt ok">已采纳</span>
          <button
            className="btn btn-ghost btn-sm"
            disabled={busy}
            onClick={() => {
              if (window.confirm("删除这条已采纳记录？它将退出下一章提示词。"))
                void act(() => dossierApi.rowDelete(projectId, chapterRef, r.id));
            }}
          >
            删除
          </button>
        </div>
      ) : (
        <div className="ds-actions">
          <span className="cnt">已驳回</span>
          <button
            className="btn btn-ghost btn-sm"
            disabled={busy}
            onClick={() =>
              void act(() => dossierApi.rowAction(projectId, chapterRef, r.id, "restore"))
            }
          >
            恢复待确认
          </button>
        </div>
      )}
    </div>
  );
}

function ExtractingHint() {
  return (
    <p className="ds-note" data-testid="changes-extracting">
      AI 提取本章变化中……完成后此处出现待确认条目（进度见操作页签归档卡）
    </p>
  );
}

function StaleBanner({
  projectId,
  chapterRef,
  busy,
  act,
}: {
  projectId: string;
  chapterRef: string;
  busy: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  return (
    <div className="ds-banner warn" data-testid="changes-stale-banner">
      本章重写过，下面的变化基于旧设定
      <button
        className="btn btn-ghost btn-sm"
        disabled={busy}
        onClick={() => void act(() => dossierApi.extract(projectId, chapterRef))}
      >
        重新提取
      </button>
    </div>
  );
}

function useBusyAct(act: (fn: () => Promise<unknown>) => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await act(fn);
      } finally {
        setBusy(false);
      }
    },
    [act],
  );
  return { busy, run };
}

/** 「设定」页签区块：设定（按子领域分组）＋物品＋角色认知。 */
export function SettingChangesSection({
  projectId,
  chapterRef,
}: {
  projectId: string;
  chapterRef: string;
}) {
  const { data, loadError, act } = useDossierData(projectId, chapterRef);
  const { busy, run } = useBusyAct(act);

  if (loadError && !data) return <p className="ds-note">本章变化加载失败，稍后重试。</p>;
  if (!data) return <p className="ds-note">本章变化载入中…</p>;

  const rows = data.rows.filter((r) => r.domain !== "relations");
  const pending = rows.filter((r) => r.status === "pending").length;
  const extracting = data.extraction?.state === "extracting";
  if (rows.length === 0 && !extracting && !data.stale) return null;

  const settings = rows.filter((r) => r.domain === "settings");
  const items = rows.filter((r) => r.domain === "items");
  const knowledge = rows.filter((r) => r.domain === "knowledge");
  const byArea = new Map<string, DossierRow[]>();
  for (const r of settings) {
    const k = r.area || "其他";
    byArea.set(k, [...(byArea.get(k) ?? []), r]);
  }
  const cnt = (list: DossierRow[]) => {
    const p = list.filter((r) => r.status === "pending").length;
    return p ? `${p} 待确认` : "已处理";
  };

  return (
    <div className="ds-domain-wrap" data-testid="setting-changes-section">
      <div className="ds-head">
        <h3>本章变化</h3>
        <span className="ds-sub">确认后喂给下一章提示词；不改你的初始设定</span>
        <div className="ds-batch">
          <button
            className="btn btn-primary btn-sm"
            data-testid="changes-accept-all"
            disabled={busy || pending === 0}
            onClick={() =>
              void run(async () => {
                // 只批量本分区呈现的三个域；后端缺省域＝全章，不传会把用户在这里
                // 看不到的关系行一并采纳（关系域在「角色关系」页签确认）
                for (const domain of ["settings", "items", "knowledge"] as const) {
                  await dossierApi.batch(projectId, chapterRef, "accept", domain);
                }
              })
            }
          >
            全部采纳（{pending}）
          </button>
          <button
            className="btn btn-secondary btn-sm"
            disabled={busy || pending === 0}
            onClick={() =>
              void run(async () => {
                for (const domain of ["settings", "items", "knowledge"] as const) {
                  await dossierApi.batch(projectId, chapterRef, "reject", domain);
                }
              })
            }
          >
            全部驳回
          </button>
        </div>
      </div>
      {data.stale && rows.length > 0 && (
        <StaleBanner projectId={projectId} chapterRef={chapterRef} busy={busy} act={run} />
      )}
      {extracting && rows.length === 0 && <ExtractingHint />}
      {extracting && rows.length > 0 && <ExtractingHint />}
      {[...byArea.entries()].map(([area, list]) => (
        <div key={area} className="ds-domain" data-testid="changes-area">
          <div className="ds-domain-head">
            <b>{area}</b>
            <span className="cnt">{cnt(list)}</span>
          </div>
          {list.map((r) => (
            <ChangeRow
              key={r.id}
              projectId={projectId}
              chapterRef={chapterRef}
              r={r}
              busy={busy}
              act={run}
            />
          ))}
        </div>
      ))}
      {items.length > 0 && (
        <div className="ds-domain" data-testid="changes-items">
          <div className="ds-domain-head">
            <b>物品</b>
            <span className="cnt">{cnt(items)}</span>
          </div>
          {items.map((r) => (
            <ChangeRow
              key={r.id}
              projectId={projectId}
              chapterRef={chapterRef}
              r={r}
              busy={busy}
              act={run}
            />
          ))}
        </div>
      )}
      {knowledge.length > 0 && (
        <div className="ds-domain" data-testid="changes-knowledge">
          <div className="ds-domain-head">
            <b>角色认知</b>
            <span className="cnt">{cnt(knowledge)}</span>
          </div>
          {knowledge.map((r) => (
            <ChangeRow
              key={r.id}
              projectId={projectId}
              chapterRef={chapterRef}
              r={r}
              busy={busy}
              act={run}
            />
          ))}
        </div>
      )}
      <div className="ds-note">伏笔 / 世界要素提案在「操作」页签（PRO）→</div>
    </div>
  );
}

/** 「角色关系」页签区块：本章关系变化。 */
export function RelationChangesSection({
  projectId,
  chapterRef,
}: {
  projectId: string;
  chapterRef: string;
}) {
  const { data, loadError, act } = useDossierData(projectId, chapterRef);
  const { busy, run } = useBusyAct(act);

  if (loadError && !data) return <p className="ds-note">本章关系变化加载失败，稍后重试。</p>;
  if (!data) return <p className="ds-note">本章关系变化载入中…</p>;

  const rows = data.rows.filter((r) => r.domain === "relations");
  const pending = rows.filter((r) => r.status === "pending").length;
  const extracting = data.extraction?.state === "extracting";
  if (rows.length === 0 && !extracting && !data.stale) return null;

  return (
    <div className="ds-domain-wrap" data-testid="relation-changes-section">
      <div className="ds-head">
        <h3>本章关系变化</h3>
        <div className="ds-batch">
          <button
            className="btn btn-primary btn-sm"
            disabled={busy || pending === 0}
            onClick={() =>
              void run(() => dossierApi.batch(projectId, chapterRef, "accept", "relations"))
            }
          >
            本域全采纳（{pending}）
          </button>
        </div>
      </div>
      {data.stale && rows.length > 0 && (
        <StaleBanner projectId={projectId} chapterRef={chapterRef} busy={busy} act={run} />
      )}
      {extracting && <ExtractingHint />}
      {rows.length > 0 && (
        <div className="ds-domain" data-testid="changes-relations">
          {rows.map((r) => (
            <ChangeRow
              key={r.id}
              projectId={projectId}
              chapterRef={chapterRef}
              r={r}
              busy={busy}
              act={run}
            />
          ))}
        </div>
      )}
    </div>
  );
}
