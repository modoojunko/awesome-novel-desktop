/**
 * 窗口底部状态条（c-version-account-visibility，V3 落点已批）：
 * 左版权、右版本，固定窗口底常驻——报障时用户能直接报出版本（文本可选中复制）。
 * 三态（登录/未登录/工作台）全覆盖；唯一豁免：免登录营销落地页 `/`（自带品牌
 * 页脚已含版本行，营销页非应用态）。样式 .statusbar 落 index.css 业务层段
 * （与原型 list/book/model-config 逐字同值，ADJUSTMENTS 2026-09-07 条目），
 * 不新增 base.css 共享类。书架 © 页脚（Footer/.pagefoot）已并入本条。
 */
import { useLocation } from "react-router-dom";
import { formatVersion, useClientVersion } from "@/lib/version";
import { copyrightLine } from "@/lib/brand";

export default function StatusBar() {
  const { pathname } = useLocation();
  const version = useClientVersion();

  if (pathname === "/") return null;

  return (
    <>
      {/* 固定条不占文档流，垫 26px 防页面底部内容被遮挡（与原型 body padding 同口径） */}
      <div className="statusbar-spacer" aria-hidden="true" />
      <footer className="statusbar" data-od-id="app-status-bar">
        <span data-od-id="app-credits">{copyrightLine}</span>
        <span className="sb-ver" data-od-id="status-version">
          {formatVersion(version)}
        </span>
      </footer>
    </>
  );
}
