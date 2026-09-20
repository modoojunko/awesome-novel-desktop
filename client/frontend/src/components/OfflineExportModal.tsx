/** 免登备份导出弹窗（loginless-data-exit）：登录被拒/未登录态的数据出口。
 *  四步流复用备份屏口径；无配置开关（服务端强制 include_config=false——配置
 *  含 api_key 明文永不免登），UI 只留静态说明；完成页次级出口按入口语境。 */

import { useEffect, useRef, useState } from 'react';
import Modal from '@/components/design/Modal';
import { api } from '@/lib/api';
import { toast } from '@/lib/toast';

type Phase = { state: string; phase?: string; books_done?: number; books_total?: number; current_book?: string; error?: { code?: string } | null };

export default function OfflineExportModal({
  open,
  onClose,
  entry,
}: {
  open: boolean;
  onClose: () => void;
  /** 受阻态（升级卡进入）完成页给「去下载新版」次级出口；常态给「打开所在文件夹」 */
  entry: 'gate' | 'plain';
  onGoDownload?: () => void;
}) {
  const [dir, setDir] = useState('');
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<Phase | null>(null);
  const [done, setDone] = useState<{ files: string[] } | null>(null);
  const [error, setError] = useState('');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!open) {
      setRunning(false); setStatus(null); setDone(null); setError('');
      if (timerRef.current) clearInterval(timerRef.current);
    }
  }, [open]);

  const pick = async () => {
    const bridge = (window as unknown as { pywebview?: { api?: { pick_folder?: () => Promise<string> } } }).pywebview;
    if (bridge?.api?.pick_folder) {
      const d = await bridge.api.pick_folder();
      if (d) setDir(d);
    } else {
      toast.info('选择文件夹需要桌面版应用；也可手动输入完整路径');
    }
  };

  const start = async () => {
    if (!dir.trim()) { toast.error('请先选择保存位置'); return; }
    setRunning(true); setError('');
    try {
      const res = await api.post('/backup/export/start', {
        kind: 'backup', target_dir: dir.trim(), include_config: false,
      }, { quiet: true });
      if (res.code !== 0) throw new Error(res.msg || '发起失败');
      timerRef.current = setInterval(async () => {
        try {
          const st = await api.get('/backup/export/status', { quiet: true });
          const d = st.data as Phase;
          setStatus(d);
          if (d.state === 'done') {
            if (timerRef.current) clearInterval(timerRef.current);
            setRunning(false); setDone({ files: (d as unknown as { files?: string[] }).files || [] });
          } else if (d.state === 'error') {
            if (timerRef.current) clearInterval(timerRef.current);
            setRunning(false); setError(d.error?.code || 'export_failed');
          }
        } catch { /* 轮询瞬时失败继续 */ }
      }, 600);
    } catch (e: unknown) {
      setRunning(false);
      const msg = e instanceof Error ? e.message : '发起失败';
      setError(msg.includes('已有') ? '已有备份在进行中，请稍候' : msg);
    }
  };

  const step = done ? 4 : running ? 3 : 2;
  const pct = status?.books_total ? Math.round(((status.books_done || 0) / status.books_total) * 100) : 0;

  return (
    <Modal open={open} onClose={running ? () => {} : onClose} locked={running} width={480} title={`备份 · ${step} / 4`}>
      {done ? (
        <div className="bk-body">
          <p className="bk-ok">备份完成</p>
          <p className="bk-note">
            已生成文件：{done.files.join('、') || '爱小说-备份.zip'}<br />
            保存位置：{dir}
          </p>
          <div className="bk-warn">备份文件请像保管密码一样妥善保存</div>
          <p className="bk-note">
            即使不再使用爱小说，包里的正文也是通用文本文件——用其他软件也能打开，你的作品不锁定在爱小说里。
          </p>
          <div className="bk-foot">
            {entry === 'gate' ? (
              <button className="btn" onClick={onClose}>去下载新版</button>
            ) : (
              <button className="btn" onClick={onClose}>打开所在文件夹</button>
            )}
            <button className="btn btn-primary" onClick={onClose}>完成</button>
          </div>
        </div>
      ) : running ? (
        <div className="bk-body">
          <p className="bk-pct">{pct}<span>%</span></p>
          <div className="bk-bar"><i style={{ width: `${pct}%` }} /></div>
          <p className="bk-note">
            正在打包第 {(status?.books_done || 0) + 1}/{status?.books_total || '…'} 本
            {status?.current_book ? `《${status.current_book}》` : ''}
          </p>
          <p className="bk-note">正在打包作品 · 配置不包含在本次备份中</p>
        </div>
      ) : (
        <div className="bk-body">
          <p className="bk-note">
            无需登录即可完成备份。将生成 1 个文件：全部作品的正文、大纲与设定。
          </p>
          <div className="bk-row">
            <span className="bk-k">保存位置</span>
            <button className="btn btn-sm" onClick={() => void pick()}>选择文件夹</button>
            <span className="bk-mono">{dir || '未选择'}</span>
          </div>
          <input
            className="input"
            placeholder="或直接输入完整保存路径"
            value={dir}
            onChange={(e) => setDir(e.target.value)}
          />
          <p className="bk-note">配置包含敏感信息（登录账号与模型密钥），登录后可一并备份；本次仅备份作品。</p>
          {error && <p className="bk-err">{error}</p>}
          <div className="bk-foot">
            <button className="btn" onClick={onClose}>取消</button>
            <button className="btn btn-primary" disabled={!dir.trim()} onClick={() => void start()}>开始备份</button>
          </div>
        </div>
      )}
    </Modal>
  );
}
