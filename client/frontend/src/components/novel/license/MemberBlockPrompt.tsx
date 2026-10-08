import { useEffect, useState } from "react";
import { fetchPortalUrl } from "@/lib/portal";
import Modal from "@/components/design/Modal";

/**
 * 全局会员拦截弹窗（2026-08-18 口径）：AI 调用被后端 member_required 403
 * 拦截时，api.request 广播 "member-block" 事件，本组件统一弹升级引导
 * （含 S端 门户跳转），替代各调用点散落的裸错误处理。
 * 门户地址缓存与重置钩子收敛在 lib/portal（UpgradeModal 同源取用）。
 */
export default function MemberBlockPrompt() {
  const [message, setMessage] = useState<string | null>(null);
  const [portalUrl, setPortalUrl] = useState("");

  useEffect(() => {
    const onBlock = async (e: Event) => {
      const msg =
        (e as CustomEvent<{ message?: string }>).detail?.message ||
        "AI 是会员功能";
      setMessage(msg);
      setPortalUrl(await fetchPortalUrl());
    };
    window.addEventListener("member-block", onBlock as EventListener);
    return () =>
      window.removeEventListener("member-block", onBlock as EventListener);
  }, []);

  return (
    <Modal
      open={message !== null}
      onClose={() => setMessage(null)}
      title="升级套餐解锁"
      footer={
        <>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setMessage(null)}
          >
            稍后再说
          </button>
          {portalUrl ? (
            <a
              className="btn btn-primary btn-sm"
              href={portalUrl}
              target="_blank"
              rel="noreferrer"
              onClick={() => setMessage(null)}
            >
              去 S 端开通 / 续费
            </a>
          ) : (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setMessage(null)}
            >
              知道了
            </button>
          )}
        </>
      }
    >
      <div data-testid="member-block-prompt">
        <p
          className="text-sm"
          style={{
            color: "color-mix(in oklch, var(--fg) 75%, transparent)",
            padding: "6px 0 10px",
          }}
        >
          {message}
        </p>
      </div>
    </Modal>
  );
}
