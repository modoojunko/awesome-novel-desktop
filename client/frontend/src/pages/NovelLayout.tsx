import { Outlet } from "react-router-dom";
import { ProjectShell } from "@/components/novel/license/ProjectShell";

// AuthGuard/LicenseProvider 已上移至 App 认证后路由根壳（c-s-entitlement-sync：
// 书列表与工作台共享权益上下文），本层只保留项目上下文。
export default function NovelLayout() {
  return (
    <ProjectShell>
      <Outlet />
    </ProjectShell>
  );
}
