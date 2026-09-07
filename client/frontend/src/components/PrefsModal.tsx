/**
 * 全局偏好弹窗（list.html modalPrefs 的产品化）：
 * 默认字号/行距 seg（localStorage 即存即生效）+ 模型配置入口 + 账号行。
 * 原型「打开示例书」按钮在产品里是账号操作（登录/退出）。
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Modal from "@/components/design/Modal";
import RestoreModal from "@/components/RestoreModal";
import { api } from "@/lib/api";
import { getUsername, isLoggedIn, logout } from "@/lib/auth";
import { formatVersion, useClientVersion } from "@/lib/version";
import {
  getArchiveAiSummaryEnabled,
  getDefaultFontSize,
  getDefaultLineHeight,
  setArchiveAiSummaryEnabled,
  setDefaultFontSize,
  setDefaultLineHeight,
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
  if (r?.expired) return "套餐已过期 · 免费待遇";
  if (r?.tier === "trial")
    return r?.trial_remaining_days > 0 ? `试用中 · 剩 ${r.trial_remaining_days} 天` : "试用中";
  if (r?.is_member) return "PRO 会员";
  // 免费态文案对齐原型 modalPrefs（「免费版 · 单机使用」）——PR5 弹窗 parity 口径
  return "免费版 · 单机使用";
}

export default function PrefsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [fs, setFs] = useState<FontSizePref>("fs-m");
  const [lh, setLh] = useState<LineHeightPref>("lh-comfy");
  const [aiSummary, setAiSummary] = useState(true);
  const [tier, setTier] = useState<string>("");
  const [restoreOpen, setRestoreOpen] = useState(false);
  const version = useClientVersion();
  const username = getUsername();

  useEffect(() => {
    if (!open) return;
    setFs(getDefaultFontSize());
    setLh(getDefaultLineHeight());
    setAiSummary(getArchiveAiSummaryEnabled());
    api
      .post("/auth/verify")
      .then((r: any) => setTier(tierLabel(r)))
      .catch(() => setTier(tierLabel(null)));
  }, [open]);

  function save() {
    setDefaultFontSize(fs);
    setDefaultLineHeight(lh);
    setArchiveAiSummaryEnabled(aiSummary);
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="设置 · 写作偏好"
      footer={
        <>
          {/* 版本行（报障终点，与账号同屏）：吃应用级缓存，打开不发新请求 */}
          <span
            data-od-id="pref-version"
            style={{ marginRight: "auto", fontSize: 12, color: "var(--muted)" }}
          >
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
        <span className="seg">
          {FONT_SIZES.map((o) => (
            <button key={o.v} className={fs === o.v ? "on" : ""} onClick={() => setFs(o.v)}>
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
        <span className="seg">
          {LINE_HEIGHTS.map((o) => (
            <button key={o.v} className={lh === o.v ? "on" : ""} onClick={() => setLh(o.v)}>
              {o.label}
            </button>
          ))}
        </span>
      </div>
      <div className="pref-row">
        <div>
          <div className="pl">归档 AI 摘要</div>
          <div className="pm">归档时用 AI 生成章节摘要（消耗额度）；关闭后截取正文开头</div>
        </div>
        <span className="seg">
          <button className={aiSummary ? "on" : ""} onClick={() => setAiSummary(true)}>
            开
          </button>
          <button className={!aiSummary ? "on" : ""} onClick={() => setAiSummary(false)}>
            关
          </button>
        </span>
      </div>
      <div className="pref-row">
        <div>
          <div className="pl">备份与恢复</div>
          <div className="pm">全部作品的备份与恢复——升级新版前，先在这里导出备份</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-secondary btn-sm"
            data-od-id="pref-backup"
            onClick={async () => {
              const bridge = (window as any).pywebview?.api;
              if (!bridge) { alert("备份功能需要桌面版应用"); return; }
              const dir = await bridge.pick_folder();
              if (!dir) return;
              const res = await fetch("/api/backup/export/start", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ kind: "backup", target_dir: dir, include_config: true }),
              });
              if (res.ok) alert("备份已开始，完成后文件将保存在所选目录");
              else alert("备份启动失败：" + (await res.text()));
            }}
          >
            备份
          </button>
          <button
            className="btn btn-secondary btn-sm"
            data-od-id="pref-restore"
            onClick={() => {
              const bridge = (window as any).pywebview?.api;
              if (!bridge) { alert("恢复功能需要桌面版应用"); return; }
              setRestoreOpen(true);
            }}
          >
            恢复
          </button>
        </div>
      </div>
      <RestoreModal
        open={restoreOpen}
        onClose={() => setRestoreOpen(false)}
        onGoConfig={() => {
          setRestoreOpen(false);
          onClose();
          navigate("/config");
        }}
      />
      <div className="pref-row">
        <div>
          <div className="pl">模型配置 · API Key</div>
          <div className="pm">管理 AI 服务密钥与供应商</div>
        </div>
        <Link className="btn btn-secondary btn-sm" to="/config" onClick={onClose}>
          去配置
        </Link>
      </div>
      <div className="pref-row">
        <div style={{ minWidth: 0 }}>
          <div className="pl">账号</div>
          {/* 「用户名 · 套餐」可辨当前账号；超长截断、悬停见全文；无用户名不硬造 */}
          <div
            className="pm"
            data-od-id="pref-account"
            title={username ?? undefined}
            style={
              username ? { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } : undefined
            }
          >
            {username ? `${username} · ${tier || "…"}` : tier || "…"}
          </div>
        </div>
        {isLoggedIn() ? (
          <button className="btn btn-secondary btn-sm" onClick={logout}>
            退出登录
          </button>
        ) : (
          <Link className="btn btn-secondary btn-sm" to="/login" onClick={onClose}>
            登录
          </Link>
        )}
      </div>
    </Modal>
  );
}
