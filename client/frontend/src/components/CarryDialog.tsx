/**
 * 带回告知卡（c-lossless-upgrade）：四步闭环——① 告知（作品＋模型配置两块平级
 * 清单）→ ② 用户点「把作品和模型配置带过来」（唯一操作）→ ③ 进度（**锁定**：
 * 无取消/无收起——引擎单事务长写锁，收起去写作会撞 database is locked；关窗＝
 * 中断，下次重来无半成品）→ ④ 完成点确认收尾（队列在这时才放行给能力包弹窗）。
 *
 * 数据面＝carryStore 单例（进度轮询/job 报告）；结构对齐原型
 * docs/design-c/prototypes/upgrade-carry.html（.mcard/两块 section 清单/警示块）。
 * 多候选口径：本卡只针对 recommended 那份；更早候选留一行提示，入口在
 * 「账户 › 本机旧版本数据」（LegacyMigrateModal 手动路径）。
 */

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Modal from '@/components/design/Modal';
import { api } from '@/lib/api';
import { toast } from '@/lib/toast';
import { finishDialog } from '@/lib/dialogQueue';
import { useCarryStore, watchCarryJob, type CarryReport } from '@/lib/carryStore';
import type { LegacyCandidate } from '@/hooks/useLegacyDb';

type Step = 'card' | 'progress' | 'result';

const fmtWords = (n: number): string => (n >= 10000 ? `${(n / 10000).toFixed(1)} 万` : `${n}`);

export default function CarryDialog({
  candidate,
  others,
  open,
  onLater,
  onConfirmed,
}: {
  candidate: LegacyCandidate;
  /** 更早候选份数（卡上只留一行提示，不带不带在设置入口决定） */
  others: number;
  open: boolean;
  onLater: () => void;
  onConfirmed: () => void;
}) {
  const [step, setStep] = useState<Step>('card');
  const [pct, setPct] = useState(0);
  const [report, setReport] = useState<CarryReport | null>(null);
  const starting = useRef(false);
  const queryClient = useQueryClient();
  const { job } = useCarryStore();

  useEffect(() => {
    if (!open) {
      setStep('card');
      setPct(0);
      setReport(null);
      starting.current = false;
    }
  }, [open]);

  // job 报告落位（progress 轮询由 carryStore 承载，这里只消费）
  useEffect(() => {
    if (step !== 'progress') return;
    if (job?.progress) {
      const p = job.progress;
      if (p.stage === 'transfer' && p.tables_total) {
        setPct(Math.round(((p.tables_done || 0) / p.tables_total) * 100));
      } else if (p.stage === 'verify') {
        setPct(100);
      }
    }
    if (job?.state === 'done' && job.report) {
      setReport(job.report);
      setStep('result');
    } else if (job?.state === 'error' || job?.state === 'idle') {
      setReport((job.report ?? null) as CarryReport | null);
      setStep('result'); // 结果卡按「不完整/未完成」变体承接
    }
  }, [step, job]);

  const start = async () => {
    if (starting.current) return;
    starting.current = true;
    setStep('progress');
    setPct(0);
    try {
      const res = await api.post('/backup/db-migration/start',
        { source_filename: candidate.filename }, { quiet: true });
      if (res.code !== 0) throw new Error(res.msg || '发起失败');
      watchCarryJob();
    } catch (e: unknown) {
      if ((e as { status?: number })?.status === 409) {
        watchCarryJob(); // 单飞互斥：附着既有任务
        return;
      }
      starting.current = false;
      setStep('card');
      toast.error(e instanceof Error ? e.message : '发起失败，稍后可重试');
    }
  };

  const confirmDone = () => {
    finishDialog('carry'); // 放行队列（能力包弹窗此刻才可入场）
    onConfirmed();
    void queryClient.invalidateQueries({ queryKey: ['novels'] });
  };

  if (!open) return null;

  const m = candidate.manifest ?? null;
  const bookCount = m?.books_total ?? candidate.book_count ?? 0;
  const bookRows = (m?.books ?? []).map((b) => (
    <li key={b.name} style={{ display: 'flex', gap: 12, padding: '9px 14px', fontSize: 13 }}>
      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--font-display)' }}>{b.name}</span>
      <span style={{ color: 'var(--muted)', fontSize: 12 }} className="num">{fmtWords(b.words)}字</span>
    </li>
  ));
  const configRows = (m?.configs ?? []).map((c) => (
    <li key={c.name} style={{ display: 'flex', gap: 12, padding: '9px 14px', fontSize: 13 }}>
      <span style={{ flex: 1, fontFamily: 'var(--font-display)' }}>{c.name}</span>
    </li>
  ));
  const listStyle: React.CSSProperties = {
    listStyle: 'none', margin: '10px 0 0', padding: 0,
    border: '1px solid var(--line)', borderRadius: 'var(--radius, 9px)',
    background: 'var(--bg-deep, var(--bg))', overflow: 'hidden',
  };
  const secTitle = (label: string, meta: React.ReactNode) => (
    <h3 style={{ fontSize: 12, color: 'var(--muted)', margin: '12px 0 6px', fontWeight: 500 }}>
      <b style={{ color: 'var(--fg)', fontSize: 12.5, marginRight: 8 }}>{label}</b>{meta}
    </h3>
  );
  const wordsTotal = (m?.books ?? []).reduce((n, b) => n + b.words, 0);

  return (
    <Modal open={open} onClose={() => { /* 锁定态：进度期不可关，由各步自己的按钮收尾 */ }} width={460} title="把上一版的作品带过来">
      {step === 'card' && (
        <div data-testid="carry-card">
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 4px' }}>
            连同模型配置一起——检测到上一版里要带过来的内容：
          </p>
          <section>
            {secTitle('作品', <><span className="num">{bookCount}</span> 本{wordsTotal > 0 && <> · <span className="num">{fmtWords(wordsTotal)}</span> 字</>}</>)}
            <ul style={listStyle}>{bookRows}</ul>
          </section>
          {m && (m.configs_total > 0) && (
            <section>
              {secTitle('模型配置', <><span className="num">{m.configs_total}</span> 条 · 含 API Key 与用量统计</>)}
              <ul style={listStyle}>{configRows}</ul>
            </section>
          )}
          {!m && candidate.book_count != null && candidate.book_count > 0 && (
            <p style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0 0' }}>
              模型配置随作品一并带过来。
            </p>
          )}
          {others > 0 && (
            <p style={{ fontSize: 12, color: 'var(--muted)', margin: '8px 0 0' }}>
              另有更早的 <span className="num">{others}</span> 份数据，之后可在「账户 › 本机旧版本数据」里带。
            </p>
          )}
          <ul style={{ listStyle: 'none', margin: '14px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <li style={{ display: 'flex', gap: 10 }}>
              <b style={{ fontSize: 13, fontWeight: 500 }}>复制到新版本</b>
              <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>点「带过来」后，作品与模型配置的副本会进入这一版。</span>
            </li>
            <li style={{ display: 'flex', gap: 10 }}>
              <b style={{ fontSize: 13, fontWeight: 500 }}>旧文件一个字不动</b>
              <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>上一版的数据文件原位保留，随时可以装回旧版本。</span>
            </li>
            <li style={{ display: 'flex', gap: 10 }}>
              <b style={{ fontSize: 13, fontWeight: 500 }}>Key 不用重新粘贴</b>
              <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>模型配置连 Key 一起带；登录状态、字号等偏好本来就跟随本机。</span>
            </li>
          </ul>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <button className="btn" data-testid="carry-later" onClick={onLater}>稍后带</button>
            <button className="btn btn-primary" data-testid="carry-start" onClick={() => void start()}>
              把作品和模型配置带过来
            </button>
          </div>
        </div>
      )}

      {step === 'progress' && (
        <div data-testid="carry-progress">
          <div style={{ height: 6, background: 'var(--fg-soft)', borderRadius: 3, overflow: 'hidden', marginTop: 4 }}>
            <div style={{ height: '100%', background: 'var(--accent)', width: `${pct}%`, transition: 'width 0.4s ease' }} />
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '12px 0 4px' }}>
            正在带回…{job?.progress?.stage === 'transfer' && job.progress.tables_total
              ? ` 第 ${job.progress.tables_done ?? 0}/${job.progress.tables_total} 段`
              : ''}
          </p>
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 8px' }}>
            旧文件原样保留，一个字都不会动。带回期间请保持本窗口开启，通常几秒钟完成；
            万一关了，下次打开会重新提示，已带回的部分不会重复。
          </p>
          {/* 锁定态（用户拍板 10-08「不让离开」）：无取消、无收起出口 */}
        </div>
      )}

      {step === 'result' && report && (
        <div data-testid="carry-result">
          {report.status === 'ok' && report.complete !== false ? (
            <>
              <p style={{ fontSize: 15, fontFamily: 'var(--font-display)', fontWeight: 600, margin: '0 0 8px' }}>
                作品和模型配置已经带过来
              </p>
              <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 4px' }}>
                跟升级前一模一样——书架、设定、章节都在；模型配置连 Key 一起可用，不用重新粘贴。
              </p>
              <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
                已带回 <span className="num">{report.book_count_migrated ?? '?'}</span> 本书；旧文件仍在原位置，随时可以装回旧版本。
              </p>
            </>
          ) : (
            <>
              <p style={{ fontSize: 15, fontFamily: 'var(--font-display)', fontWeight: 600, margin: '0 0 8px' }}>
                作品已经带过来，有一项要留意
              </p>
              <div
                data-testid="carry-partial"
                style={{
                  margin: '8px 0 4px', padding: '10px 12px', fontSize: 12.5, lineHeight: 1.7,
                  border: '1px solid var(--warn)', background: 'var(--warn-soft)',
                  borderRadius: 9,
                }}
              >
                {report.status === 'ok'
                  ? `有 ${(report.tables_skipped?.length ?? 0) > 0 ? '数据段' : '内容'}没有完整迁入，旧版里可能有内容没带过来。可以重新带一次，或用备份包恢复。`
                  : report.reason || '带回没有完成——已带过来的部分不会重复，稍后可重新执行。'}
              </div>
            </>
          )}
          {(report.dead_keys ?? 0) > 0 && (
            <p style={{ fontSize: 12, color: 'var(--muted)', margin: '8px 0 0' }}>
              其中 <span className="num">{report.dead_keys}</span> 条配置的 Key 无法直接迁过来，需在「模型配置」里重新粘贴。
            </p>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            {report.status === 'ok' && report.complete !== false ? (
              <>
                <button className="btn" onClick={() => window.dispatchEvent(new CustomEvent('legacy-migrate:open'))}>
                  查看旧文件
                </button>
                <button className="btn btn-primary" data-testid="carry-confirm" onClick={confirmDone}>
                  好，开始写作
                </button>
              </>
            ) : (
              <>
                <button className="btn" data-testid="carry-confirm-partial" onClick={confirmDone}>
                  先这样，开始写作
                </button>
                <button className="btn btn-primary" onClick={() => void start()}>
                  重新带一次
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
