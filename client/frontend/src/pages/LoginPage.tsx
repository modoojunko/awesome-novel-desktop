import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { request } from '../lib/api';
import { toast } from '../lib/toast';
import { useDeviceActivation } from '../hooks/useDeviceActivation';
import { Ico, P } from '@/components/icons';
import { BRAND } from '@/lib/brand';
import UpgradeGate from '@/components/auth/UpgradeGate';
import OfflineExportModal from '@/components/OfflineExportModal';
import { api } from '@/lib/api';

export default function LoginPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  // 静默检测超 2s 仍无结果：多半是云端冷启动（MinNum=0 缩容后首次 30-60s），给出提示避免"假死"观感
  const [checkingSlow, setCheckingSlow] = useState(false);
  const [error, setError] = useState('');
  // 会话失效/注销撤销期提示（useAuthHeal 写入 sessionStorage，登录页展示后清除）
  const [authNotice, setAuthNotice] = useState(() => {
    const msg = sessionStorage.getItem('auth_notice');
    if (msg) sessionStorage.removeItem('auth_notice');
    return msg ?? '';
  });
  // heal 晚于本页挂载写入提示时（如 401 拦截器先把人送到 /login）补读一次，
  // 保证「账号已注销」的提示必达（account-deletion tasks 5.2）
  useEffect(() => {
    const reread = () => {
      const msg = sessionStorage.getItem('auth_notice');
      if (msg) {
        sessionStorage.removeItem('auth_notice');
        setAuthNotice(msg);
      }
    };
    window.addEventListener('auth-notice-updated', reread);
    return () => window.removeEventListener('auth-notice-updated', reread);
  }, []);
  const [authUrl, setAuthUrl] = useState('');
  // loginless-data-exit：升级卡（两场景）＋免登备份弹窗＋本地库计数行
  const [outdated, setOutdated] = useState<{ scenario: 'upgrade' | 'unavailable'; latest?: string; download_url?: string } | null>(null);
  const [offlineExport, setOfflineExport] = useState<null | 'gate' | 'plain'>(null);
  const [libraryCount, setLibraryCount] = useState<{ books: number; words: number } | null>(null);
  const cancelledRef = useRef(false);
  const pollingRef = useRef(false);
  const { refreshStatus, showToast } = useDeviceActivation();

  // 单次 check-auth：已授权则写入 token 并跳转作品列表；返回是否成功
  const checkAuthorized = useCallback(async (successMsg: string) => {
    try {
      const res = await request('/auth/check-auth');
      // s-auth-outdated-signal：S端 判定客户端需更新 → 停轮询就地升级卡（场景一）
      if (res.code === 3 && res.data?.client_outdated) {
        setOutdated({
          scenario: 'upgrade',
          latest: res.data.latest_version || undefined,
          download_url: res.data.download_url || undefined,
        });
        return 'outdated' as const;
      }
      if (res.code === 0 && res.data?.token && res.data.token !== 'dev-token') {
        localStorage.setItem('auth_token', res.data.token);
        if (res.data.username) localStorage.setItem('auth_username', res.data.username);
        toast.success(successMsg);
        // 获取设备激活状态
        const devStatus = await refreshStatus();
        if (devStatus) showToast(devStatus);
        navigate('/novels', { replace: true });
        return true;
      }
    } catch {
      // S端 不可用或未登录（code=-1 绝不升级卡——防误闸，场景二由显式错误触发）
    }
    return false;
  }, [navigate, refreshStatus, showToast]);

  // 静默检测：当前浏览器在 S端 是否已登录
  useEffect(() => {
    // 如果用户刚手动退出，跳过自动检测，让用户看到登录按钮
    if (sessionStorage.getItem("manual_logout")) {
      sessionStorage.removeItem("manual_logout");
      setChecking(false);
      return;
    }
    // 反弹熔断（c-session-flip-stability「失效处理不循环」）：刚被 401 踢出
    // （3 秒内）就跳过自动登录——否则「自动登录写回凭据 ↔ 业务 401 踢出」
    // 互踢成环，实测可达每秒百次请求。熔断后停留本页走手动登录。
    const kickedAt = Number(sessionStorage.getItem("last_auth_kick_at") || 0);
    if (kickedAt && Date.now() - kickedAt < 3000) {
      setChecking(false);
      return;
    }
    (async () => {
      await checkAuthorized('自动登录成功'); // outdated 态已 setOutdated；一律解除 checking
      setChecking(false);
    })();
  }, [checkAuthorized]);

  // 卸载时标记取消，停止进行中的轮询（避免 setState-on-unmounted）
  useEffect(() => {
    return () => { cancelledRef.current = true; };
  }, []);

  useEffect(() => {
    if (!checking) return;
    const t = setTimeout(() => setCheckingSlow(true), 2000);
    return () => clearTimeout(t);
  }, [checking]);

  // loginless-data-exit：本地库计数行（免登 legacy-db/status + 轻量书统计）
  useEffect(() => {
    (async () => {
      try {
        const st = await api.get('/backup/legacy-db/status', { quiet: true });
        const latest = st.data?.all?.[0] ?? st.data;
        if (st.data?.present && latest?.book_count) {
          setLibraryCount({ books: latest.book_count, words: 0 });
          return;
        }
      } catch { /* 静默 */ }
      setLibraryCount({ books: 0, words: 0 });
    })();
  }, []);

  const handleBrowserAuth = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await request('/auth/browser-auth', { method: 'POST' });
      // 后端返回授权页 URL（宿主浏览器打开），不在容器内开浏览器/轮询
      if (res.code === 0 && res.data?.token) {
        // 已有会话
        localStorage.setItem('auth_token', res.data.token);
        toast.success('登录成功');
        const devStatus = await refreshStatus();
        if (devStatus) showToast(devStatus);
        navigate('/novels', { replace: true });
        return;
      }
      const url = res.data?.auth_url;
      if (!url) {
        setError('未能获取授权地址，请稍后重试');
        return;
      }
      setAuthUrl(url);
      // pywebview cocoa 只对「真实锚点点击」转系统浏览器，编程式 window.open 落空
      // （UpdateNotice 同款判例）——壳层桥可用走 open_external，否则回退 window.open
      const bridge = (window as any).pywebview?.api;
      if (typeof bridge?.open_external === "function") {
        // 桥调用失败（如无默认浏览器环境）回退 window.open，不让 rejection 悬空
        Promise.resolve(bridge.open_external(url)).catch(() => window.open(url, "_blank"));
      } else {
        window.open(url, '_blank');
      }

      // 新一次点击先取消上一轮残留轮询，防重入
      /* v8 ignore start -- 防御分支：主按钮在 loading 期禁用，UI 上无法在轮询中再次进入 */
      if (pollingRef.current) cancelledRef.current = true;
      /* v8 ignore stop */
      cancelledRef.current = false;
      pollingRef.current = true;
      let ok = false;
      try {
        // 前端轮询 check-auth 直到授权成功；每轮检查取消标记
        for (let i = 0; i < 60; i++) {
          if (cancelledRef.current) break;
          await new Promise((r) => setTimeout(r, 2000));
          if (cancelledRef.current) break;
          const checked = await checkAuthorized('登录成功');
          if (checked === 'outdated') return;
          if (checked) { ok = true; break; }
        }
      } finally {
        pollingRef.current = false;
      }
      if (!ok && !cancelledRef.current) {
        setError('授权超时，请在浏览器中完成登录，或点击「重新检测」');
      }
    } catch {
      setError('登录失败');
    } finally {
      setLoading(false);
    }
  };

  // 超时后手动触发单次检测（不重复开浏览器/轮询）
  const retryCheck = async () => {
    setLoading(true);
    setError('');
    try {
      const ok = await checkAuthorized('登录成功');
      if (!ok) setError('尚未检测到登录，请确认浏览器已完成后重试');
    } finally {
      setLoading(false);
    }
  };

  if (checking) {
    return (
      <div className="auth-wrap">
        <div className="flex flex-col items-center gap-3">
          <Ico d={P.spinner} className="spin" size={30} style={{ color: "var(--accent)" }} />
          {checkingSlow && (
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              正在唤醒云端服务，首次访问约需 30–60 秒，请稍候…
            </p>
          )}
        </div>
      </div>
    );
  }

  if (outdated) {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h1>{BRAND.name}</h1>
          <UpgradeGate
            scenario={outdated.scenario}
            latest={outdated.latest}
            current={undefined}
            downloadHint={outdated.download_url}
            libraryCount={libraryCount}
            onBackup={() => setOfflineExport('gate')}
          />
        </div>
        <OfflineExportModal open={offlineExport !== null} onClose={() => setOfflineExport(null)} entry={offlineExport ?? 'plain'} />
      </div>
    );
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>{BRAND.name}</h1>
        <p className="sub">登录后即可开始创作</p>
        <button className="btn btn-primary btn-lg btn-block" onClick={handleBrowserAuth} disabled={loading}>
          {loading ? <Ico d={P.spinner} className="spin" size={16} /> : '打开浏览器登录'}
        </button>
        {authNotice && <p className="note" role="status">{authNotice}</p>}
        {error && <p className="err">{error}</p>}
        {loading && authUrl && !error && (
          <p className="note">
            已打开授权页面，等待登录完成；云端唤醒中，首次可能需要 30–60 秒
          </p>
        )}
        {authUrl && error && (
          <button className="btn btn-secondary btn-sm mt-3" onClick={retryCheck} disabled={loading}>
            {/* v8 ignore start -- spinner 臂不可达：按钮渲染要求 error 非空，
                而 handleBrowserAuth/retryCheck 入口都 setError("") —— 进入 loading 时按钮已卸载 */}
            {loading ? <Ico d={P.spinner} className="spin" size={13} /> : '重新检测'}
            {/* v8 ignore stop */}
          </button>
        )}
        <p className="note">将在系统浏览器中打开登录页面</p>
        <button className="text-btn" onClick={() => setOfflineExport('plain')}>不登录也能备份作品</button>
        <Link to="/" className="lnk">返回首页</Link>
      </div>
      <OfflineExportModal open={offlineExport !== null} onClose={() => setOfflineExport(null)} entry={offlineExport ?? 'plain'} />
    </div>
  );
}
