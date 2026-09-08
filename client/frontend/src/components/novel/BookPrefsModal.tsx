// 本书偏好弹窗（book.html #modalPrefs 复刻，PR 5）：
// 字号/行距/归档 AI 摘要 per-book（pref.book.{pid}.*，全局偏好兜底）+ 账号行。
// 工作台 appbar「设置」入口专用（list.html 全局偏好弹窗仍走 PrefsModal）。
// 产品化（ADJUSTMENTS）：升级 PRO 按钮链升级弹窗（S端 门户），账号行 tier 用真实 /auth/verify。
import { useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import UpgradeModal from "@/components/novel/UpgradeModal";
import { api } from "@/lib/api";
import { isLoggedIn } from "@/lib/auth";
import { tierLabel as sharedTierLabel } from "@/lib/tier";
import { formatVersion, useClientVersion } from "@/lib/version";
import {
  getBookArchiveAiSummary,
  getBookFontSize,
  getBookLineHeight,
  setBookArchiveAiSummary,
  setBookFontSize,
  setBookLineHeight,
  type FontSizePref,
  type LineHeightPref,
} from "@/lib/prefs";

const FONT_SIZES: { v: FontSizePref; label: string }[] = [
  { v: "fs-s", label: "小" },
  { v: "fs-m", label: "中" },
  { v: "fs-l", label: "大" },
];
const LINE_HEIGHTS: { v: LineHeightPref; label: string }[] = [
  { v: "lh-tight", label: "紧凑" },
  { v: "lh-comfy", label: "舒适" },
  { v: "lh-loose", label: "宽松" },
];

function tierLabel(r: any): string {
  if (!isLoggedIn()) return "未登录 · 单机使用";
  // 文案单源 lib/tier.ts（c-account-control-center）：会员档统一「PRO 会员」
  return sharedTierLabel(r ?? {});
}

export default function BookPrefsModal({
  open,
  onClose,
  projectId,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
}) {
  const [fs, setFs] = useState<FontSizePref>("fs-m");
  const [lh, setLh] = useState<LineHeightPref>("lh-comfy");
  const [aiSummary, setAiSummary] = useState(true);
  const [tier, setTier] = useState<string>("");
  const [isMember, setIsMember] = useState(false);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const version = useClientVersion();

  useEffect(() => {
    if (!open) return;
    setFs(getBookFontSize(projectId));
    setLh(getBookLineHeight(projectId));
    setAiSummary(getBookArchiveAiSummary(projectId));
    api
      .post("/auth/verify")
      .then((r: any) => {
        setTier(tierLabel(r));
        setIsMember(!!r?.is_member && !r?.expired);
      })
      .catch(() => {
        setTier(tierLabel(null));
        setIsMember(false);
      });
  }, [open, projectId]);

  const save = () => {
    setBookFontSize(projectId, fs);
    setBookLineHeight(projectId, lh);
    setBookArchiveAiSummary(projectId, aiSummary);
    onClose();
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="设置 · 写作偏好"
        wbStyle
        footer={
          <>
            {/* 版本行（.note 走 wb-style 弹窗既有左置 muted 样式）：吃应用级缓存 */}
            <span className="note" data-od-id="pref-version">
              {formatVersion(version)}
            </span>
            <button className="btn btn-primary" onClick={save}>
              保存
            </button>
          </>
        }
      >
        <div className="pref-row">
          <div>
            <div className="pl">默认字号</div>
            <div className="pm">新建章节的正文排版</div>
          </div>
          <span className="seg" data-od-id="seg-fontsize">
            {FONT_SIZES.map((o) => (
              <button
                key={o.v}
                className={fs === o.v ? "on" : undefined}
                onClick={() => setFs(o.v)}
              >
                {o.label}
              </button>
            ))}
          </span>
        </div>
        <div className="pref-row">
          <div>
            <div className="pl">默认行距</div>
            <div className="pm">长时写作建议「舒适」</div>
          </div>
          <span className="seg" data-od-id="seg-lineheight">
            {LINE_HEIGHTS.map((o) => (
              <button
                key={o.v}
                className={lh === o.v ? "on" : undefined}
                onClick={() => setLh(o.v)}
              >
                {o.label}
              </button>
            ))}
          </span>
        </div>
        <div className="pref-row">
          <div>
            <div className="pl">归档时 AI 摘要</div>
            <div className="pm">归档时用 AI 生成章节摘要；关闭后截取正文开头作摘要</div>
          </div>
          <span className="seg" data-od-id="seg-archsum">
            <button className={aiSummary ? "on" : undefined} onClick={() => setAiSummary(true)}>
              开
            </button>
            <button className={!aiSummary ? "on" : undefined} onClick={() => setAiSummary(false)}>
              关
            </button>
          </span>
        </div>
        <div className="pref-row">
          <div>
            <div className="pl">账号</div>
            <div className="pm">{tier || "…"}</div>
          </div>
          {!isMember && (
            <button
              className="btn btn-secondary btn-sm"
              id="pref-upgrade"
              onClick={() => {
                // 原型链：关偏好弹窗 → 开升级弹窗
                onClose();
                setShowUpgrade(true);
              }}
            >
              升级 PRO
            </button>
          )}
        </div>
      </Modal>
      <UpgradeModal open={showUpgrade} onClose={() => setShowUpgrade(false)} />
    </>
  );
}
