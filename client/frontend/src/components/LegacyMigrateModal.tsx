/** 找回向导（db-generation）：发现 → 预览 → 进度 → 结果；「保留旧文件，
 *  不再提醒」；清理=结果页可选折叠 L2 确认。文案对齐 UX 规格（用户层禁
 *  「迁入/数据库」术语——「找回」「旧版数据」）。 */

import { useEffect, useRef, useState } from 'react';
import Modal from '@/components/design/Modal';
import { api } from '@/lib/api';
import type { LegacyCandidate } from '@/hooks/useLegacyDb';

interface PreviewReport {
  v: number;
  tables: Array<{ table: string; rows_source: number | null; rows_inserted: number | null }>;
  tables_skipped: Array<{ table: string; reason: string }>;
  book_count_source: number | null;
}

type Step = 'detect' | 'preview' | 'working' | 'result';

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
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!open) { setStep('detect'); setPreview(null); setError(''); }
  }, [open]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const startPreview = async () => {
    setError('');
    try {
      const res = await api.post('/backup/db-migration/preview', { source_filename: picked }, { quiet: true });
      if (res.code === 1 && res.data?.reason === 'pre_adr_generation') {
        setError(res.data.message);
        return;
      }
      setPreview(res.data as PreviewReport);
      setStep('preview');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '预览失败');
    }
  };

  const startMigrate = async () => {
    setError('');
    setStep('working');
    try {
      const res = await api.post('/backup/db-migration/start', { source_filename: picked }, { quiet: true });
      if (res.code !== 0) throw new Error(res.msg || '找回失败');
      setProgress(100);
      setStep('result');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '找回失败');
      setStep('detect');
    }
  };

  const pickedCand = candidates.find((c) => c.filename === picked);

  return (
    <Modal open={open} onClose={step === 'working' ? () => {} : onClose} locked={step === 'working'} width={440} title="找回作品">
      {step === 'detect' && (
        <div className="bk-body">
          <p className="bk-note">没有丢失——在这台电脑上找到了旧版作品。</p>
          {candidates.length > 1 && (
            <p className="bk-note">找到 {candidates.length} 份旧版数据，选一份先找回；两份内容可能不同，找回后可随时再来找回另一份。</p>
          )}
          <div className="bk-row">
            <select className="input" value={picked} onChange={(e) => setPicked(e.target.value)}>
              {candidates.map((c) => (
                <option key={c.filename} value={c.filename}>
                  {new Date(c.mtime * 1000).toLocaleDateString('zh-CN')} · {c.book_count ?? '?'} 本书
                  {c.unreadable ? '（无法读取）' : ''}
                </option>
              ))}
            </select>
          </div>
          <p className="bk-note">找回是把作品复制回书架，原来的文件一个字都不会动。</p>
          {error && <p className="bk-err">{error}</p>}
          <div className="bk-foot">
            <button className="btn" onClick={onClose}>取消</button>
            <button className="btn btn-primary" onClick={() => void startPreview()}>下一步</button>
          </div>
        </div>
      )}
      {step === 'preview' && preview && (
        <div className="bk-body">
          <p className="bk-note">将找回以下作品：</p>
          <div className="bk-row"><span>《旧版数据》 · {preview.book_count_source ?? '?'} 本书</span></div>
          {(preview.tables_skipped || []).map((s) => (
            <p className="bk-note" key={s.table}>表 {s.table} 为旧版格式，其中的内容将跳过（不影响其余数据）。</p>
          ))}
          <p className="bk-note">找回是把作品复制回书架，原来的文件一个字都不会动。</p>
          <div className="bk-foot">
            <button className="btn" onClick={() => setStep('detect')}>上一步</button>
            <button className="btn btn-primary" onClick={() => void startMigrate()}>开始找回</button>
          </div>
        </div>
      )}
      {step === 'working' && (
        <div className="bk-body">
          <p className="bk-pct">{progress}<span>%</span></p>
          <div className="bk-bar"><i style={{ width: `${progress}%` }} /></div>
          <p className="bk-note">正在找回作品，请勿关闭窗口。</p>
        </div>
      )}
      {step === 'result' && (
        <div className="bk-body">
          <p className="bk-ok">已找回作品</p>
          <p className="bk-note">原来的旧文件没有改动，可以重新找回。</p>
          <div className="bk-foot">
            <button className="btn btn-primary" onClick={() => { onDone(); onClose(); }}>去书架看看</button>
          </div>
        </div>
      )}
    </Modal>
  );
}
