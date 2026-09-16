import { useLocation, Link } from "react-router-dom";
import { isLoggedIn } from "../lib/auth";
import { BRAND } from "../lib/brand";
import AcctMenu from "../components/AcctMenu";

/** 顶栏（c-account-control-center）：动作区收敛为头像胶囊唯一入口。
 * 书架/配置态：logo + 导航 + 触发钮。
 * 书内态（/novel/*）：本组件让位 —— 书内顶栏已行头归一（logo 即返回 + 书名 +
 * 题材 + 当前主线定位 + 账户胶囊，单行 48px，storyline.html 口径），
 * 由 NovelWorkspace 渲染（含 AcctMenu 与本书偏好弹窗）。 */
export default function Navbar() {
  const location = useLocation();
  const loggedIn = isLoggedIn();

  // 书内页顶栏由 NovelWorkspace 渲染，全局顶栏不重复出头条
  if (location.pathname.startsWith("/novel/")) return null;

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
