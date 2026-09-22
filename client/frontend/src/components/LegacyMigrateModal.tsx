/** 带回向导（c-db-per-version）：发现 → 预览 → 进度（异步轮询）→ 结果。
 *  文案口径＝「带回」——新版本用新库，把上一版的作品带过来（用户层禁
 *  「迁入/迁移/数据库/版本号/文件路径」）。
 *  异步化（2026-09-20 评审实施）：start 立返→1s 轮询 status 的 progress 事件
 *  （stage/tables_done/tables_total→百分比）；可关弹窗（迁移后台继续，
 *  源只读＋OR IGNORE 幂等保证中断无损）；重开时先探测 status 附着现有任务。 */

import { useCallback, useEffect, useRef, useState } from 'react';
import Modal from '@/components/design/Modal';
import { api } from '@/lib/api';
import type { LegacyCandidate } from '@/hooks/useLegacyDb';

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
}

interface MigrationReport {
  status: string;
  reason?: string;
  book_count_source?: number;
  book_count_migrated?: number;
}

type Step = 'detect' | 'preview' | 'working' | 'result' | 'error';

const STAGE_LABEL: Record<string, string> = {
  copy: '正在复制安全副本…',
  prepare: '正在检查数据完整性…',
  plan: '正在分析数据结构…',
  transfer: '正在带回作品…',
  verify: '正在核对写入结果…',
};

export default function LegacyMigrateModal({
  open,
  candidates,
  onClose,
  onDone,
}: {
  open: boolean;
  candidates: LegacyCandidate[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState<Step>('detect');
  const [picked, setPicked] = useState<string>(candidates[0]?.filename ?? '');
  const [preview, setPreview] = useState<PreviewReport | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  const [result, setResult] = useState<MigrationReport | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
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
          if (rep?.status !== 'ok') setErrorMsg(rep?.reason || '带回未完成');
        } else if (d?.state === 'error') {
          clearPoll();
          setStep('error');
          setErrorMsg(d.error?.message || '带回过程中出现错误');
        } else if (d?.state === 'idle') {
          clearPoll();
          setStep('error');
          setErrorMsg('带回可能未完成（应用曾重启），可重新执行——已带过来的部分不会重复。');
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

  const startPreview = async () => {
    setErrorMsg('');
    try {
      const res = await api.post('/backup/db-migration/preview', { source_filename: picked }, { quiet: true });
      if (res.code === 1 && res.data?.reason === 'pre_adr_generation') {
        setErrorMsg(res.data.message);
        return;
      }
      setPreview(res.data as PreviewReport);
      setStep('preview');
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : '预览失败');
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
      const msg = e instanceof Error ? e.message : '';
      if (msg.includes('迁入') || msg.includes('迁移') || msg.includes('migration')) {
        startPolling();
        return;
      }
      setErrorMsg(msg || '发起失败');
      setStep('detect');
    }
  };

  const pct = progressPct;
  const stageText = progress ? STAGE_LABEL[progress.stage] || progress.stage : '准备中…';

  return (
    <Modal open={open} onClose={onClose} width={440} title="把上一版的作品带过来">
      {step === 'detect' && (
        <div>
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 12px' }}>
            没有丢失——在这台电脑上找到了旧版作品。
            {candidates.length > 1 && ` 找到 ${candidates.length} 份，选一份先带回。`}
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
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 16px' }}>
            带回是把作品复制回书架，原来的文件一个字都不会动（旧文件原位保留，可随时装回旧版本）。
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
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 8px' }}>将带回以下作品：</p>
          <p style={{ fontSize: 14, fontWeight: 500, margin: '0 0 8px' }}>{preview.book_count_source ?? '?'} 本书</p>
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
            <button className="btn btn-primary" onClick={() => void startMigrate()}>把上一版的作品带过来</button>
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
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 12px', textAlign: 'center' }}>
            可以关闭此窗口，带回会在后台继续完成
          </p>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <button className="btn" onClick={onClose}>后台继续</button>
          </div>
        </div>
      )}
      {step === 'result' && result && (
        <div>
          <p style={{ fontSize: 18, fontFamily: 'var(--font-display)', fontWeight: 600, margin: '0 0 8px', textAlign: 'center' }}>
            已带回 {result.book_count_migrated ?? '?'} 本书
          </p>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 16px', textAlign: 'center' }}>
            原来的旧文件没有改动，保留在原处。
          </p>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <button className="btn btn-primary" onClick={() => { onDone(); onClose(); }}>去书架看看</button>
          </div>
        </div>
      )}
      {step === 'error' && (
        <div>
          <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--err)', margin: '0 0 8px' }}>带回没有完成</p>
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
