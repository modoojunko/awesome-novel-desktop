import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { isLoggedIn } from "../lib/auth";
import { BRAND } from "../lib/brand";
import AcctMenu from "../components/AcctMenu";
import BookPrefsModal from "../components/novel/BookPrefsModal";
import { Ico, P } from "../components/icons";

/** 顶栏（c-account-control-center）：动作区收敛为头像胶囊唯一入口。
 * 书架态：logo + 导航 + 触发钮；工作台态：logo + 返回 + 触发钮（本书偏好
 * 经面板「本书偏好」项打开，BookPrefsModal 仍挂本处）。 */
export default function Navbar() {
  const location = useLocation();
  const loggedIn = isLoggedIn();
  const [showBookPrefs, setShowBookPrefs] = useState(false);

  // 书工作台变体（book.html）：logo + 分隔线 + 返回我的小说 + 触发钮，无导航/登录。
  if (location.pathname.startsWith("/novel/")) {
    const m = location.pathname.match(/^\/novel\/([^/]+)/);
    const projectId = m?.[1] ?? "";
    return (
      <header className="appbar appbar-wb">
        <Link className="logo" to="/novels">
          <span className="logo-mark">{BRAND.mark}</span>{BRAND.name}
        </Link>
        <span className="sep" />
        <Link className="back" to="/novels">
          <Ico d={P.back} sw={1.8} />
          我的小说
        </Link>
        <span className="spacer" />
        {loggedIn && (
          <AcctMenu onBookPrefs={() => setShowBookPrefs(true)} />
        )}
        <BookPrefsModal
          open={showBookPrefs && !!projectId}
          onClose={() => setShowBookPrefs(false)}
          projectId={projectId}
        />
      </header>
    );
  }

  const on = (prefix: string) =>
    location.pathname === prefix || location.pathname.startsWith(prefix + "/") ? "on" : undefined;

  return (
    <header className="appbar">
      <Link className="logo" to="/novels">
        <span className="logo-mark">{BRAND.mark}</span>{BRAND.name}
      </Link>
      {loggedIn && (
        <nav className="nav">
          <Link to="/novels" className={on("/novels")} aria-current={on("/novels") ? "page" : undefined}>
            我的作品
          </Link>
          <Link to="/config" className={on("/config")}>
            模型配置
          </Link>
        </nav>
      )}
      <span className="spacer" />
      {!loggedIn && (
        <>
          {/* 未登录（静态首页/登录页口径）：不给导航与设置，只给入口 */}
          <Link className="btn btn-ghost btn-sm" to="/login">
            登录
          </Link>
          <Link className="btn btn-primary btn-sm" to="/login">
            免费开始
          </Link>
        </>
      )}
      {loggedIn && <AcctMenu />}
    </header>
  );
}
