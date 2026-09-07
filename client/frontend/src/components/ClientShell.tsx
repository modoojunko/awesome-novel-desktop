import { useEffect } from "react";
import { Toaster, toast } from "@/lib/toast";
import { useAuthHeal } from "@/hooks/useAuthHeal";
import UpdateNotice from "@/components/UpdateNotice";
import ExpiryNoticeBar from "@/components/ExpiryNoticeBar";
import StatusBar from "@/components/StatusBar";

export default function ClientShell({ children }: { children: React.ReactNode }) {
  useAuthHeal(); // 启动自愈登录态：后端会话有效则写回 localStorage

  useEffect(() => {
    const handler = (e: PromiseRejectionEvent) => {
      toast.error(e.reason?.message || String(e.reason));
    };
    window.addEventListener("unhandledrejection", handler);
    return () => window.removeEventListener("unhandledrejection", handler);
  }, []);

  return (
    <div className="app-shell">
      <UpdateNotice />
      <ExpiryNoticeBar />
      {children}
      <StatusBar />
      <Toaster />
    </div>
  );
}
