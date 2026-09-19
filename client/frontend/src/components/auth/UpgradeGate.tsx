/** 登录页升级卡（loginless-data-exit）：登录被拒「客户端需更新」时就地替换主按钮区。
 *  情绪主角=首答句+可核对计数（恐慌由证据化解），主按钮=推进恢复可用；
 *  「先备份作品」恒 secondary 同排可见（数据出口不设墙是可用性承诺不是层级承诺）。
 *  文案逐字采用原型 login.html s2/s3（UX 五路评审规格）。 */

import { useState } from 'react';
import { toast } from '@/lib/toast';
import { resolveDownloadUrl } from '@/lib/updateUrl';

export interface UpgradeGateProps {
  /** 场景一=确需更新（出示版本事实对照）；场景二=服务异常（不出示对照） */
  scenario: 'upgrade' | 'unavailable';
  latest?: string;
  current?: string;
  downloadHint?: string;
  /** 本地库计数行（legacy-db/status 或本地轻查询；空库传 null） */
  libraryCount: { books: number; words: number } | null;
  /** 「先备份作品」→ 打开免登导出弹窗 */
  onBackup: () => void;
  /** 场景二：重试登录 */
  onRetry?: () => void;
}

export default function UpgradeGate({
  scenario,
  latest,
  current,
  downloadHint,
  libraryCount,
  onBackup,
  onRetry,
}: UpgradeGateProps) {
  const [url, setUrl] = useState('');
  const isUpgrade = scenario === 'upgrade';

  const open = async () => {
    const u = url || (await resolveDownloadUrl(downloadHint));
    setUrl(u);
    window.open(u, '_blank', 'noopener,noreferrer');
  };

  const copy = async () => {
    const u = url || (await resolveDownloadUrl(downloadHint));
    setUrl(u);
    try {
      await navigator.clipboard.writeText(u);
      toast.success('已复制下载地址');
    } catch {
      toast.info(u);
    }
  };

  return (
    <div className="gate" data-testid="upgrade-gate">
      <span className="gate-badge">{isUpgrade ? '需要更新' : '暂时无法登录'}</span>
      <p className="gate-first">你的作品都在这台电脑上</p>
      {libraryCount && libraryCount.books > 0 ? (
        <p className="gate-count">
          <b>{libraryCount.books} 本书</b> · {libraryCount.words.toLocaleString('zh-CN')} 字，完好无损
        </p>
      ) : (
        <p className="gate-empty">这台电脑上没有存作品</p>
      )}
      <p className="gate-diag">
        {isUpgrade
          ? '此版本的桌面应用已无法连接登录服务，更新后即可继续使用。'
          : '现在连不上登录服务，稍后重试即可。不是你的操作有问题，作品也没有任何变化。'}
      </p>
      {isUpgrade && current && latest && (
        <p className="gate-ver">
          当前 v{current} · 需更新至 v{latest} 起
        </p>
      )}
      <div className="gate-actions">
        {isUpgrade ? (
          <a className="btn btn-primary btn-lg btn-block" href="#" onClick={(e) => { e.preventDefault(); void open(); }}>
            去下载新版
          </a>
        ) : (
          <button className="btn btn-primary btn-lg btn-block" onClick={onRetry}>
            重试登录
          </button>
        )}
        <button className="btn btn-lg btn-block" onClick={onBackup}>
          先备份作品
        </button>
      </div>
      <div className="gate-exit">
        {isUpgrade ? (
          <button className="text-btn" onClick={() => void open()}>查看更新内容</button>
        ) : null}
        <button className="text-btn" onClick={() => void copy()}>复制下载地址</button>
      </div>
      <p className="gate-foot">
        备份无需登录；{isUpgrade ? '更新只更换程序，不会改动这台电脑上的任何作品。' : '可以随时再来登录。'}
      </p>
    </div>
  );
}
