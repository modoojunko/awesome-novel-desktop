// 静态首页（玄墨三段式；原型 prototypes/home.html 变体 a 已转正）。
// 未登录入口卡：品牌 lockup → slogan → 行动路径；已登录由 App.tsx 的 HomeGate
// 直接跳书架，不会看到此页。
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "@/lib/api";
import { BRAND } from "@/lib/brand";

// 教程页未建：暂指 GitHub 使用说明，站内引导流立项后替换
const TUTORIAL_URL = "https://github.com/modoojunko/ai-novel#readme";

/** 版本胶囊：读后端烘包版本（release.json → /update-check，quiet 静默）；dev 构建不展示。 */
function useBakedVersion(): string {
  const [ver, setVer] = useState("");
  useEffect(() => {
    let alive = true;
    request("/update-check", { quiet: true })
      .then((s: { current?: string } | null) => {
        const v = s?.current ?? "";
        if (alive && v && v !== "dev") setVer(v);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return ver;
}

export default function LandingPage() {
  const ver = useBakedVersion();
  return (
    <section className="welcome">
      <div className="ink-glow" />
      <div className="brand-lockup fx fx-1">
        <div className="brand-en">AWESOME-NOVEL</div>
        <div className="brand-cn">
          {BRAND.name}
          {ver && <span className="brand-ver">v{ver}</span>}
        </div>
      </div>
      <h1 className="fx fx-2">
        人铸灵魂
        <br />
        <span className="ai">AI 行笔墨</span>
      </h1>
      <p className="lead fx fx-2">故事已经在脑子里了，现在给它第一行字。</p>
      <div className="exit-block fx fx-3">
        <div className="paths">
          <Link to="/login" className="path pri" data-od-id="btn-free-start">
            <b>直接开写</b>
            <span>落笔即存，想到哪写到哪</span>
          </Link>
          <a
            href={TUTORIAL_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="path"
            data-od-id="btn-tutorial"
          >
            <b>新手教程</b>
            <span>5 分钟看懂从建书到成稿</span>
          </a>
        </div>
        <p className="signin">
          已有账号？
          <Link to="/login">直接登录</Link>
        </p>
        <p className="note">
          免费版可创建 <span className="num">1</span> 部作品 · 无需绑卡
        </p>
      </div>
    </section>
  );
}
