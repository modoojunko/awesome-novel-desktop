/** 迁移向导（c-db-per-version）：发现 → 预览 → 进度（异步轮询）→ 结果。
 *  文案口径＝「迁移」——新版本用新库，把上一版的作品与模型配置迁进来（用户层禁
 *  「迁入/迁移/数据库/版本号/文件路径」）。
 *  异步化（2026-09-20 评审实施）：start 立返→1s 轮询 status 的 progress 事件
 *  （stage/tables_done/tables_total→百分比）。c-lossless-upgrade：进度期**锁定**
 *  （用户拍板「不让离开」——引擎单事务长写锁，收起去写作会撞库锁）；关窗＝中断，
 *  下次重来无半成品（源只读＋OR IGNORE 幂等）；重开时先探测 status 附着现有任务。 */

import { useCallback, useEffect, useRef, useState } from 'react';
import Modal from '@/components/design/Modal';
import { api } from '@/lib/api';
import { toast } from '@/lib/toast';
import type { LegacyCandidate, QuarantinedLibrary } from '@/hooks/useLegacyDb';

interface ProgressEvent {
  stage: 'copy' | 'prepare' | 'plan' | 'transfer' | 'verify';
  tables_total?: number;
  tables_done?: number;
  table?: string;
  rows_inserted?: number;
}

interface PreviewReport {
  v: number;
  tables: Array<{ table: string; rows_source: number | null; rows_inserted: number | null }>;
  tables_skipped: Array<{ table: string; reason: string }>;
  book_count_source: number | null;
  manifest?: { configs_total: number } | null;
}

export interface RetentionItem {
  filename: string;
  book_count: number | null;
  size_bytes: number;
  mtime: number;
}

interface MigrationReport {
  status: string;
  reason?: string;
  book_count_source?: number;
  book_count_migrated?: number;
  /** 源书在目标库的在场数（c-carry-retry-complete：重带幂等的完整口径） */
  book_count_present?: number;
  complete?: boolean;
  book_count_target_after?: number;
  fk_violations?: unknown[];
}

type Step = 'detect' | 'preview' | 'working' | 'result' | 'error';

const STAGE_LABEL: Record<string, string> = {
  copy: '正在复制安全副本…',
  prepare: '正在检查数据完整性…',
  plan: '正在分析数据结构…',
  transfer: '正在迁移作品…',
  verify: '正在核对写入结果…',
};

export default function LegacyMigrateModal({
  open,
  candidates,
  quarantined = [],
  onClose,
  onDone,
}: {
  open: boolean;
  candidates: LegacyCandidate[];
  /** 不可读的隔离件：只读清单（原地保留、不进候选、不提供带回动作） */
  quarantined?: QuarantinedLibrary[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState<Step>('detect');
  // 来源初值＝**后端给的推荐位**（`recommended` 单源），不得用列表顺序推断（specs）
  const [picked, setPicked] = useState<string>(
    candidates.find((c) => c.recommended)?.filename ?? candidates[0]?.filename ?? '',
  );
  const [preview, setPreview] = useState<PreviewReport | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  const [result, setResult] = useState<MigrationReport | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  /* 旧库留存（c-db-per-version）：待删清单由后端单源给（仅「已成功带回」的件、
     默认保留最近 2 份）；两段确认——展开清单 → 确认删除，全程可关 */
  const [retention, setRetention] = useState<RetentionItem[] | null>(null);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const failCountRef = useRef(0);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    clearPoll();
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.get('/backup/db-migration/status', { quiet: true });
        failCountRef.current = 0;
        const d = res.data;
        if (d?.state === 'running') {
          if (d.progress) {
            setProgress(d.progress as ProgressEvent);
            if (d.progress.stage === 'transfer' && d.progress.tables_total) {
              setProgressPct(Math.round(((d.progress.tables_done || 0) / d.progress.tables_total) * 100));
            } else if (d.progress.stage === 'verify') {
              setProgressPct(100);
            }
          }
        } else if (d?.state === 'done') {
          clearPoll();
          const rep = d.report as MigrationReport;
          setResult(rep);
          setStep(rep?.status === 'ok' ? 'result' : 'error');
          if (rep?.status !== 'ok') setErrorMsg(rep?.reason || '迁移未完成');
        } else if (d?.state === 'error') {
          clearPoll();
          setStep('error');
          setErrorMsg(d.error?.message || '迁移过程中出现错误');
        } else if (d?.state === 'idle') {
          clearPoll();
          setStep('error');
          setErrorMsg('迁移可能未完成（应用曾重启），可重新执行——已迁移的部分不会重复。');
        }
      } catch {
        failCountRef.current += 1;
        if (failCountRef.current > 3) {
          clearPoll();
          setStep('error');
          setErrorMsg('连接中断。任务可能在后台继续，可稍后重新打开向导确认。');
        }
      }
    }, 1000);
  }, [clearPoll]);

  // open 时重置 + 探测是否有正在跑的任务（附着）
  useEffect(() => {
    if (!open) {
      clearPoll();
      setStep('detect'); setPreview(null); setProgress(null);
      setProgressPct(0); setResult(null); setErrorMsg(''); failCountRef.current = 0;
      return;
    }
    (async () => {
      try {
        const res = await api.get('/backup/db-migration/status', { quiet: true });
        const d = res.data;
        if (d?.state === 'running' && d?.kind === 'migration') {
          setStep('working');
          startPolling();
        }
      } catch { /* 静默——正常走 detect */ }
    })();
  }, [open, clearPoll, startPolling]);

  useEffect(() => () => clearPoll(), [clearPoll]);

  /* 一次确认（specs：常态为单次确认完成搬运）：可搬运候选恰一份时，打开即预演——
     用户从空态出口行点进来后只需点一次主按钮。多候选/异常仍走发现步选来源。 */
  const autoPreviewedRef = useRef(false);
  useEffect(() => {
    if (!open) {
      autoPreviewedRef.current = false;
      return;
    }
    if (autoPreviewedRef.current || candidates.length !== 1) return;
    autoPreviewedRef.current = true;
    const only = candidates.find((c) => c.recommended) ?? candidates[0];
    setPicked(only.filename);
    void startPreview(only.filename);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅在「打开且单候选」时触发一次
  }, [open, candidates]);

  const startPreview = async (source: string = picked) => {
    setErrorMsg('');
    try {
      const res = await api.post('/backup/db-migration/preview', { source_filename: source }, { quiet: true });
      // 两道人话通道：ADR 前世代（设定在盘上 yaml）与「novel 正名」之前世代
      if (res.code === 1 && (res.data?.reason === 'pre_adr_generation'
        || res.data?.reason === 'pre_rename_generation')) {
        setErrorMsg(res.data.message);
        return;
      }
      setPreview(res.data as PreviewReport);
      setStep('preview');
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : '预览失败');
    }
  };

  /** 清理入口的显示条件：**全部成功**才出现（部分失败不得引导删旧文件）。
   *  书覆盖按在场数（present）——migrated 是「本次插入」数，重带幂等下恒 0，
   *  拿它对拍会让成功重带永远出不来清理入口（c-carry-retry-complete）。 */
  const cleanupEligible = (rep: MigrationReport | null): boolean =>
    !!rep && rep.status === 'ok'
    && (rep.fk_violations?.length ?? 0) === 0
    && (rep.book_count_source ?? 0)
      === (rep.book_count_present ?? rep.book_count_migrated ?? -1);

  const loadRetention = async () => {
    setBusy(true);
    try {
      const res = await api.get('/backup/db-migration/retention', { quiet: true });
      setRetention((res.data?.items ?? []) as RetentionItem[]);
      setCleanupOpen(true);
    } catch {
      toast.error('读不到可清理的旧文件，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const runCleanup = async () => {
    setBusy(true);
    try {
      const names = (retention ?? []).map((r) => r.filename);
      const res = await api.post('/backup/db-migration/cleanup', { filenames: names }, { quiet: true });
      const deleted = (res.data?.deleted ?? []) as string[];
      toast.success(`已清理 ${deleted.length} 份旧文件`);
      setRetention((retention ?? []).filter((r) => !deleted.includes(r.filename)));
      setConfirmingDelete(false);
      setCleanupOpen(false);
    } catch {
      toast.error('清理没有完成，可稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const startMigrate = async () => {
    setErrorMsg('');
    setStep('working');
    setProgressPct(0);
    try {
      const res = await api.post('/backup/db-migration/start', { source_filename: picked }, { quiet: true });
      if (res.code !== 0) throw new Error(res.msg || '发起失败');
      startPolling();
    } catch (e: unknown) {
      // 409＝已有任务在跑（备份/导出/搬运单飞互斥）——转进度态 attach 轮询；
      // 不按文案子串判定（后端 409 文案「已有任务在进行中」不含「迁入/迁移」，
      // 旧分支实为死路，双击/互斥时永远退回发现步）
      if ((e as { status?: number })?.status === 409) {
        startPolling();
        return;
      }
      const msg = e instanceof Error ? e.message : '';
      setErrorMsg(msg || '发起失败');
      setStep('detect');
    }
  };

  /** 隔离件只读清单（规格「损坏库只读可见」）：detect 与 preview 两步都渲染——
   *  单候选自动预演会跳过发现步，清单必须仍可达（c-db-version-hardening）。 */
  const quarantinedList = quarantined.length > 0 ? (
    <div style={{ marginBottom: 12 }} data-testid="migrate-quarantined">
      <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 6px' }}>
        另有 {quarantined.length} 份旧文件读不出来（已原地保留，不会自动删除）：
      </p>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
        {quarantined.map((q) => (
          <li key={q.filename} style={{ fontSize: 12, color: 'var(--muted)' }}>
            {Math.round(q.size_bytes / 1024)} KB · {new Date(q.mtime * 1000).toLocaleDateString('zh-CN')}
          </li>
        ))}
      </ul>
    </div>
  ) : null;

  const pct = progressPct;
  const stageText = progress ? STAGE_LABEL[progress.stage] || progress.stage : '准备中…';

  return (
    <Modal open={open} onClose={onClose} width={440} title="迁移上一版的作品与模型配置">
      {step === 'detect' && (
        <div>
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 12px' }}>
            没有丢失——在这台电脑上找到了旧版作品。
            {candidates.length > 1 && ` 找到 ${candidates.length} 份，选一份先迁移。`}
          </p>
          {candidates.length > 1 && (
            <select className="input" value={picked} onChange={(e) => setPicked(e.target.value)} style={{ marginBottom: 10 }}>
              {candidates.map((c) => (
                <option key={c.filename} value={c.filename}>
                  {new Date(c.mtime * 1000).toLocaleDateString('zh-CN')} · {c.book_count ?? '?'} 本书
                  {c.unreadable ? '（无法读取）' : ''}
                </option>
              ))}
            </select>
          )}
          {candidates.length === 1 && (
            <p style={{ fontSize: 13.5, fontWeight: 500, margin: '0 0 8px' }}>
              {new Date((candidates[0]?.mtime || 0) * 1000).toLocaleDateString('zh-CN')} 的数据 · {candidates[0]?.book_count ?? '?'} 本书
            </p>
          )}
          {quarantinedList}
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 16px' }}>
            迁移会把作品与模型配置复制进书架，原来的文件一个字都不会动（旧文件原位保留，可随时装回旧版本）。
          </p>
          {errorMsg && <p style={{ fontSize: 12.5, color: 'var(--err)', margin: '0 0 10px' }}>{errorMsg}</p>}
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <button className="btn" onClick={onClose}>取消</button>
            <button className="btn btn-primary" onClick={() => void startPreview()}>下一步</button>
          </div>
        </div>
      )}
      {step === 'preview' && preview && (
        <div>
          {quarantinedList}
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 8px' }}>将迁移：</p>
          <p style={{ fontSize: 14, fontWeight: 500, margin: '0 0 8px' }}>{preview.book_count_source ?? '?'} 本书</p>
          {(preview.manifest?.configs_total ?? 0) > 0 && (
            <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 8px' }}>
              模型配置 <span className="num">{preview.manifest!.configs_total}</span> 条（含 API Key）一并迁移
            </p>
          )}
          {(preview.tables_skipped || []).length > 0 && (
            <p style={{ fontSize: 12, color: 'var(--warn)', margin: '0 0 8px' }}>
              {preview.tables_skipped.length} 个旧格式数据段将跳过（不影响其余内容）
            </p>
          )}
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 16px' }}>
            原来的文件一个字都不会动。
          </p>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <button className="btn" onClick={() => setStep('detect')}>上一步</button>
            <button className="btn btn-primary" onClick={() => void startMigrate()}>立即迁移</button>
          </div>
        </div>
      )}
      {step === 'working' && (
        <div>
          <p style={{ fontSize: 22, fontFamily: 'var(--font-display)', margin: '0 0 4px', textAlign: 'center' }}>
            {pct}<span style={{ fontSize: 14, color: 'var(--muted)' }}>%</span>
          </p>
          <div style={{ height: 6, background: 'var(--fg-soft)', borderRadius: 3, overflow: 'hidden', marginBottom: 12 }}>
            <div style={{ height: '100%', background: 'var(--accent)', width: `${pct}%`, transition: 'width 0.5s ease' }} />
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 4px', textAlign: 'center' }}>{stageText}</p>
          {progress?.stage === 'transfer' && progress.table && (
            <p style={{ fontSize: 11.5, color: 'var(--muted)', margin: '0 0 12px', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
              {progress.tables_done || 0}/{progress.tables_total || '?'} · {progress.rows_inserted ?? 0} 行
            </p>
          )}
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 4px', textAlign: 'center' }}>
            请保持本窗口开启，通常几秒钟完成
          </p>
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0, textAlign: 'center' }}>
            万一关闭了，下次打开会重新提示，已迁移的部分不会重复
          </p>
          {/* c-lossless-upgrade：进度期锁定（用户拍板「不让离开」）——无取消、无收起 */}
        </div>
      )}
      {step === 'result' && result && (
        <div>
          {/* 书数取在场数（present）：重带幂等下「本次插入」恒 0（c-carry-retry-complete） */}
          <p style={{ fontSize: 18, fontFamily: 'var(--font-display)', fontWeight: 600, margin: '0 0 8px', textAlign: 'center' }}>
            已迁移 {result.book_count_present ?? result.book_count_migrated ?? '?'} 本书
          </p>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 16px', textAlign: 'center' }}>
            原来的旧文件没有改动，保留在原处。
          </p>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <button className="btn btn-primary" onClick={() => { onDone(); onClose(); }}>去书架看看</button>
          </div>
          {cleanupEligible(result) && (
            <div style={{ marginTop: 16, borderTop: '1px solid var(--line, #2a2a2a)', paddingTop: 12 }}>
              {!cleanupOpen ? (
                <button className="text-btn" disabled={busy} onClick={() => void loadRetention()}>
                  清理旧文件（默认保留最近 2 份）
                </button>
              ) : (retention ?? []).length === 0 ? (
                <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
                  没有可清理的旧文件（最近 2 份会被保留）。
                </p>
              ) : (
                <div>
                  <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 8px' }}>
                    将清理下列旧文件——删除不可撤销，已迁移的内容不受影响。建议先
                    <button className="text-btn" onClick={() => { onClose(); onDone(); }}>备份一份</button>。
                  </p>
                  <ul style={{ margin: '0 0 10px', padding: 0, listStyle: 'none' }}>
                    {(retention ?? []).map((r) => (
                      <li key={r.filename} style={{ fontSize: 12.5, display: 'flex', gap: 10, padding: '2px 0' }}>
                        <span className="num">{r.book_count ?? '?'} 本</span>
                        <span style={{ color: 'var(--muted)' }}>{Math.round(r.size_bytes / 1024)} KB</span>
                        <span style={{ color: 'var(--muted)' }}>
                          {new Date(r.mtime * 1000).toLocaleDateString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {!confirmingDelete ? (
                    <button className="btn btn-danger btn-sm" onClick={() => setConfirmingDelete(true)}>
                      删除这些旧文件
                    </button>
                  ) : (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-sm" onClick={() => setConfirmingDelete(false)}>取消</button>
                      <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => void runCleanup()}>
                        确认删除（不可撤销）
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {step === 'error' && (
        <div>
          <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--err)', margin: '0 0 8px' }}>迁移没有完成</p>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 16px' }}>{errorMsg || '请稍后重试。'}</p>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <button className="btn" onClick={onClose}>关闭</button>
            <button className="btn btn-primary" onClick={() => { setErrorMsg(''); setStep('detect'); }}>重新开始</button>
          </div>
        </div>
      )}
    </Modal>
  );
}
