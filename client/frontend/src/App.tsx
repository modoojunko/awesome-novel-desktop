import { Routes, Route, Navigate, useLocation, useParams } from "react-router-dom";
import ClientShell from "@/components/ClientShell";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import LandingPage from "@/pages/LandingPage";
import LoginPage from "@/pages/LoginPage";
import ApiKeyConfigPage from "@/pages/ApiKeyConfigPage";
import NovelListPage from "@/pages/NovelListPage";
import NovelLayout from "@/pages/NovelLayout";
import NovelWorkspace from "@/components/novel/NovelWorkspace";
import MemberBlockPrompt from "@/components/novel/license/MemberBlockPrompt";
import AuthGuard from "@/components/auth/AuthGuard";
import { LicenseProvider } from "@/components/novel/license/LicenseProvider";
import { isLoggedIn } from "@/lib/auth";

/** 301 过渡：旧路由 /project/:id → /novel/:id */
function RedirectToNovel() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={"/novel/" + id} replace />;
}

/** 认证后路由根壳（c-s-entitlement-sync）：AuthGuard 最外，LicenseProvider
 * 上移至此——书列表与工作台全部认证路由共享权益上下文（degraded 提示条、
 * 路由切换两跳刷新都依赖此挂载点）。 */
function Authed({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <LicenseProvider>{children}</LicenseProvider>
    </AuthGuard>
  );
}

/** `/` 分流：静态首页只服务未登录；已登录直落书架，不再看入口卡。 */
function HomeGate() {
  return isLoggedIn() ? <Navigate to="/novels" replace /> : <LandingPage />;
}

export default function App() {
  const location = useLocation();

  return (
    <ClientShell>
      <Navbar />
      <div className="flex-1 flex flex-col page-enter" key={location.pathname}>
        <Routes>
          <Route path="/" element={<HomeGate />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/config" element={<ApiKeyConfigPage />} />
          {/* 301 过渡（一个版本期后删除） */}
          <Route path="/books" element={<Navigate to="/novels" replace />} />
          <Route path="/project/:id" element={<RedirectToNovel />} />
          {/* 新路由 */}
          <Route
            path="/novels"
            element={
              <Authed>
                <NovelListPage />
              </Authed>
            }
          />
          <Route
            path="/novel/:id"
            element={
              <Authed>
                <NovelLayout />
              </Authed>
            }
          >
            <Route index element={<NovelWorkspace />} />
          </Route>
          {/* 兜底：未知地址落书架，不白屏 */}
          <Route path="*" element={<Navigate to="/novels" replace />} />
        </Routes>
      </div>
      <Footer />
      {/* AI 会员拦截全局升级引导（监听 api.request 的 member-block 事件） */}
      <MemberBlockPrompt />
    </ClientShell>
  );
}
