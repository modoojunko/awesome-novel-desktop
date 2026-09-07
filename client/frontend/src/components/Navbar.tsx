import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { isLoggedIn } from "../lib/auth";
import { supportUrl } from "../lib/support";
import { BRAND } from "../lib/brand";
import PrefsModal from "../components/PrefsModal";
import BookPrefsModal from "../components/novel/BookPrefsModal";
import { Ico, P } from "../components/icons";

/** 客服外跳按钮（list.html/book.html appbar 原样）：锚点 target=_blank，
 * pywebview cocoa 只认锚点不认编程式 window.open。 */
function SupportLink({ url }: { url: string }) {
  return (
    <a className="btn btn-ghost btn-sm" href={url} target="_blank" rel="noreferrer">
      联系客服
    </a>
  );
}

/** 顶栏（list.html appbar 原样）：logo + 导航 + spacer + 联系客服 + 设置。 */
export default function Navbar() {
  const location = useLocation();
  const loggedIn = isLoggedIn();
  const [showPrefs, setShowPrefs] = useState(false);
  const [support, setSupport] = useState("");

  useEffect(() => {
    if (!loggedIn) return;
    supportUrl().then(setSupport);
  }, [loggedIn]);

  // 书工作台变体（book.html）：logo + 分隔线 + 返回我的小说 + 联系客服 + 设置，无导航/登录。
  // PR 5：设置 = 本书偏好（字号/行距 per-book + 归档 AI 摘要），全局偏好仍在书架态。
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
        {support && <SupportLink url={support} />}
        <button className="btn btn-ghost btn-sm" onClick={() => setShowPrefs(true)}>
          设置
        </button>
        <BookPrefsModal
          open={showPrefs && !!projectId}
          onClose={() => setShowPrefs(false)}
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
      {loggedIn && (
        <>
          {support && <SupportLink url={support} />}
          <button className="btn btn-ghost btn-sm" onClick={() => setShowPrefs(true)}>
            设置
          </button>
          <PrefsModal open={showPrefs} onClose={() => setShowPrefs(false)} />
        </>
      )}
    </header>
  );
}
