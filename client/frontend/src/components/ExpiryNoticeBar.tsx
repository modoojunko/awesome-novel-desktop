import { useCallback, useEffect, useState } from "react";
import { request } from "@/lib/api";
import { fetchPortalUrl, isSafeExternalUrl, PORTAL_URL } from "@/lib/portal";

interface Attention {
  refund_processing?: boolean;
  verify_pending?: boolean;
}

interface CheckAuthExt {
  days_remaining?: number;
  attention?: Attention;
  tier?: string;
}

/** 单条待展示提醒：key 用于「已关闭当日不重显、状态变化重显」 */
interface Notice {
  key: string;
  text: string;
  linkText: string;
  linkPath: string;
}

/**
 * 账号动态提示条（s-pay-foundation · C端唯一改动点）。
 * 数据源：S端 check-auth 扩展字段（days_remaining / attention），启动拉一次。
 * 优先级：支付核对中 > 退款处理中 > 套餐临期（≤7 天），同时只显示一条；
 * 「不再显示」按 notice key + 当日记忆（localStorage），状态变化（key 变化）重显。
 * 「查看订单/进度/去续费」为 S端 门户真实锚点（target=_blank，pywebview cocoa
 * 只认 LinkActivated 锚点外跳），与 UpdateNotice 同款写法。
 */
export default function ExpiryNoticeBar() {
  const [notice, setNotice] = useState<Notice | null>(null);
  const [portal, setPortal] = useState("");

  // portal 地址延迟拉取：仅在确认要展示提示条后请求。
  // 启动即拉会在未登录/令牌失效场景触发 /auth/config 401 全局副作用
  // （request() 401 → 清凭据回登录），与 useAuthHeal 的静默自愈相冲突。
  useEffect(() => {
    if (!notice) return;
    let cancelled = false;
    fetchPortalUrl().then((u) => {
      if (!cancelled) setPortal(u || PORTAL_URL);
    });
    return () => {
      cancelled = true;
    };
  }, [notice]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await request("/auth/check-auth", { quiet: true });
        if (cancelled || res.code !== 0 || !res.data) return;
        const ext: CheckAuthExt = res.data;
        const n = pickNotice(ext);
        // 当日已关闭的同态提醒不再显示；状态变化（key 含天数等）自然重显
        if (n) {
          try {
            if (localStorage.getItem(dismissKey(n.key)) === todayTag()) return;
          } catch {
            /* 存储不可用则照常显示 */
          }
        }
        setNotice(n);
      } catch {
        /* 静默：提示条失败不打扰写作 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const dismiss = useCallback(() => {
    /* v8 ignore start -- 防御分支：dismiss 只绑在「已渲染出提示条」的按钮上，那时 notice 恒非空 */
    if (!notice) return;
    /* v8 ignore stop */
    try {
      localStorage.setItem(dismissKey(notice.key), todayTag());
    } catch {
      /* 存储失败无感 */
    }
    setNotice(null);
  }, [notice]);

  if (!notice) return null;

  const href = `${portal}${notice.linkPath}`;
  const safe = isSafeExternalUrl(portal);

  return (
    <div className="update-strip">
      <div className="notice">
        <span className="nt">
          <b>{notice.text}</b>
        </span>
        {safe ? (
          <a className="btn btn-secondary btn-sm" href={href} target="_blank" rel="noopener noreferrer">
            {notice.linkText}
          </a>
        ) : null}
        <button type="button" className="btn btn-ghost btn-sm" onClick={dismiss}>
          不再显示
        </button>
      </div>
    </div>
  );
}

/** 优先级裁决：核对中 > 退款处理中 > 临期（≤7 天）；无套餐/免费不提示 */
function pickNotice(ext: CheckAuthExt): Notice | null {
  const a = ext.attention ?? {};
  if (a.verify_pending) {
    return {
      key: "verify_pending",
      text: "支付核对中：您近期一笔支付正在核对金额，请勿重复支付。",
      linkText: "查看订单",
      linkPath: "/dashboard/orders",
    };
  }
  if (a.refund_processing) {
    return {
      key: "refund_processing",
      text: "退款处理中：退款将原路退回您的微信，一般数分钟至 3 个工作日到账。",
      linkText: "查看进度",
      linkPath: "/dashboard/orders",
    };
  }
  const days = ext.days_remaining;
  if (typeof days === "number" && days > 0 && days <= 7) {
    return {
      key: `expiring:${days}`,
      text: `套餐还剩 ${days} 天，到期后本地作品不受影响、AI 功能需续费继续。`,
      linkText: "去续费",
      linkPath: "/pay",
    };
  }
  return null;
}

function dismissKey(key: string): string {
  return `account-notice-dismissed:${key}`;
}

function todayTag(): string {
  const d = new Date();
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}
