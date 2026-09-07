import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { request } from '../lib/api';
import { toast } from '../lib/toast';
import { useDeviceActivation } from '../hooks/useDeviceActivation';
import { Ico, P } from '@/components/icons';
import { BRAND } from '@/lib/brand';

export default function LoginPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  // 静默检测超 2s 仍无结果：多半是云端冷启动（MinNum=0 缩容后首次 30-60s），给出提示避免"假死"观感
  const [checkingSlow, setCheckingSlow] = useState(false);
  const [error, setError] = useState('');
  // 会话失效/注销撤销期提示（useAuthHeal 写入 sessionStorage，登录页展示后清除）
  const [authNotice] = useState(() => {
    const msg = sessionStorage.getItem('auth_notice');
    if (msg) sessionStorage.removeItem('auth_notice');
    return msg ?? '';
  });
  const [authUrl, setAuthUrl] = useState('');
  const cancelledRef = useRef(false);
  const pollingRef = useRef(false);
  const { refreshStatus, showToast } = useDeviceActivation();

  // 单次 check-auth：已授权则写入 token 并跳转作品列表；返回是否成功
  const checkAuthorized = useCallback(async (successMsg: string) => {
    try {
      const res = await request('/auth/check-auth');
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
      // S端 不可用或未登录
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
    (async () => {
      const ok = await checkAuthorized('自动登录成功');
      if (!ok) setChecking(false);
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
      window.open(url, '_blank');

      // 新一次点击先取消上一轮残留轮询，防重入
      if (pollingRef.current) cancelledRef.current = true;
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
            {loading ? <Ico d={P.spinner} className="spin" size={13} /> : '重新检测'}
          </button>
        )}
        <p className="note">将在系统浏览器中打开登录页面</p>
        <Link to="/" className="lnk">返回首页</Link>
      </div>
    </div>
  );
}
