import { useEffect } from "react";
import { Toaster, toast } from "@/lib/toast";
import { useAuthHeal } from "@/hooks/useAuthHeal";
import UpdateNotice from "@/components/UpdateNotice";
import ExpiryNoticeBar from "@/components/ExpiryNoticeBar";
import StatusBar from "@/components/StatusBar";
import { LicenseProvider } from "@/components/novel/license/LicenseProvider";

export default function ClientShell({ children }: { children: React.ReactNode }) {
  useAuthHeal(); // 启动自愈登录态：后端会话有效则写回 localStorage

  useEffect(() => {
    const handler = (e: PromiseRejectionEvent) => {
      toast.error(e.reason?.message || String(e.reason));
    };
    window.addEventListener("unhandledrejection", handler);
    return () => window.removeEventListener("unhandledrejection", handler);
  }, []);

  // 权益上下文上移至壳层（c-account-control-center）：控制中心面板在全部已登录
  // 路由（含 /config）都有徽章数据。恒挂载（c-session-flip-stability）：登录态
  // 翻转只切换上下文值（未登录由 LicenseProvider 注 null 透传，不发 verify），
  // 壳层组件（更新/到期提示条、状态条）不再随翻转整树重挂、启动请求不重复触发。
  return (
    <LicenseProvider>
      <div className="app-shell">
        <UpdateNotice />
        <ExpiryNoticeBar />
        {children}
        <StatusBar />
        <Toaster />
      </div>
    </LicenseProvider>
  );
}
