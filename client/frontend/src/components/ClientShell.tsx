import { useEffect } from "react";
import { Toaster, toast } from "@/lib/toast";
import { useAuthHeal } from "@/hooks/useAuthHeal";
import UpdateNotice from "@/components/UpdateNotice";
import ExpiryNoticeBar from "@/components/ExpiryNoticeBar";
import StatusBar from "@/components/StatusBar";
import { LicenseProvider } from "@/components/novel/license/LicenseProvider";
import { isLoggedIn } from "@/lib/auth";

export default function ClientShell({ children }: { children: React.ReactNode }) {
  useAuthHeal(); // 启动自愈登录态：后端会话有效则写回 localStorage

  useEffect(() => {
    const handler = (e: PromiseRejectionEvent) => {
      toast.error(e.reason?.message || String(e.reason));
    };
    window.addEventListener("unhandledrejection", handler);
    return () => window.removeEventListener("unhandledrejection", handler);
  }, []);

  // 权益上下文上移至壳层已登录分支（c-account-control-center）：控制中心面板在
  // 全部已登录路由（含 /config）都有徽章数据；未登录页不挂 Provider、不发 verify。
  const inner = (
    <div className="app-shell">
      <UpdateNotice />
      <ExpiryNoticeBar />
      {children}
      <StatusBar />
      <Toaster />
    </div>
  );

  if (!isLoggedIn()) return inner;
  return <LicenseProvider>{inner}</LicenseProvider>;
}
