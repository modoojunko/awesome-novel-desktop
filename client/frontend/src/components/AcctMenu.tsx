/**
 * 控制中心面板（c-account-control-center）：顶栏头像胶囊触发 + 右对齐 popover。
 * - 文案/徽章单源 lib/tier.ts：面板头完整档、触发钮短档四态（免费版含过期合并）。
 * - S端失联（LicenseProvider 同步刷新失败信号）：文案保持既有档位、仅转 warn，恢复自动回常规色。
 * - 交互口径：Esc 回焦触发钮、外点关闭（白名单含触发钮防 toggle 双触发）、
 *   方向键在菜单项间循环、Tab 不逃逸；流程项关面板进入对应流程。
 * - 工作台语境（/novel/*）增挂「本书偏好」项（onBookPrefs 由调用方注入，承接原「设置」按钮）。
 * - 退出登录轻确认：面板内联二步，不弹模态。
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import RestoreModal from "@/components/RestoreModal";
import { Ico, P } from "@/components/icons";
import { useTier } from "@/hooks/useTier";
import { getUsername, logout } from "@/lib/auth";
import { supportUrl } from "@/lib/support";
import { formatVersion, useClientVersion } from "@/lib/version";
import { tierLabel, tierShort } from "@/lib/tier";

type Tone = "accent" | "muted" | "warn";
const BADGE_CLASS: Record<Tone, string> = {
  accent: "badge badge-accent",
  muted: "badge badge-muted",
  warn: "badge badge-warn",
};

export default function AcctMenu({
  onBookPrefs,
}: {
  /** 工作台语境注入：面板「本书偏好」项回调（打开本书偏好弹窗） */
  onBookPrefs?: () => void;
}) {
  const navigate = useNavigate();
  const tier = useTier();
  const version = useClientVersion();
  const username = getUsername();

  const [open, setOpen] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);
  const [support, setSupport] = useState("");
  const [restoreOpen, setRestoreOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    supportUrl().then(setSupport);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    setConfirmLogout(false);
    triggerRef.current?.focus();
  }, []);

  // 打开时定位：触发钮正下方右对齐；窗口尺寸变化跟随
  const position = useCallback(() => {
    const t = triggerRef.current;
    const p = panelRef.current;
    if (!t || !p) return;
    const r = t.getBoundingClientRect();
    p.style.top = `${r.bottom + 4}px`;
    p.style.right = `${window.innerWidth - r.right}px`;
  }, []);
  useLayoutEffect(() => {
    if (!open) return;
    position();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
  }, [open, position]);

  // 外点关闭：白名单含触发钮（防 toggle 双触发）
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panelRef.current?.contains(t) && !triggerRef.current?.contains(t)) {
        setOpen(false);
        setConfirmLogout(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
        return;
      }
      // 方向键在菜单项间循环；Tab 圈不出面板
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Tab") return;
      const items = [
        ...(panelRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []),
      ].filter((el) => !el.hasAttribute("hidden"));
      if (!items.length) return;
      const idx = items.indexOf(document.activeElement as HTMLElement);
      if (e.key === "Tab") {
        e.preventDefault();
        items[e.shiftKey ? (idx <= 0 ? items.length - 1 : idx - 1) : (idx + 1) % items.length]?.focus();
        return;
      }
      e.preventDefault();
      if (idx === -1) {
        items[0]?.focus();
      } else if (e.key === "ArrowDown") {
        items[(idx + 1) % items.length]?.focus();
      } else {
        items[(idx - 1 + items.length) % items.length]?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  if (!open) {
    return (
      <div className="acct">
        <button
          ref={triggerRef}
          className="acct-trigger"
          data-od-id="acct-trigger"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <span className="avatar" aria-hidden="true">
            {username ? (
              username.slice(0, 1)
            ) : (
              <Ico d={P.person} sw={1.7} />
            )}
          </span>
          <Badge />
          <Ico className="caret" d={P.chevronDown} sw={1.7} />
        </button>
      </div>
    );
  }

  // 备份：桌面壳选文件夹 → 本地后端直写导出（原全局设置弹窗流程原样迁移）
  const runBackup = async () => {
    close();
    const bridge = (window as any).pywebview?.api;
    if (!bridge) {
      alert("备份功能需要桌面版应用");
      return;
    }
    const dir = await bridge.pick_folder();
    if (!dir) return;
    const res = await fetch("/api/backup/export/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "backup", target_dir: dir, include_config: true }),
    });
    if (res.ok) alert("备份已开始，完成后文件将保存在所选目录");
    else alert("备份启动失败：" + (await res.text()));
  };

  const judgment = {
    tier: tier.tier,
    is_member: tier.isMember,
    expired: tier.expired,
    trial_remaining_days: tier.trialRemainingDays,
  };

  return (
    <>
      <div className="acct">
        <button
          ref={triggerRef}
          className="acct-trigger open"
          data-od-id="acct-trigger"
          aria-haspopup="menu"
          aria-expanded="true"
          onClick={() => close()}
        >
          <span className="avatar" aria-hidden="true">
            {username ? username.slice(0, 1) : <Ico d={P.person} sw={1.7} />}
          </span>
          <Badge />
          <Ico className="caret" d={P.chevronDown} sw={1.7} />
        </button>
      </div>
      {createPortal(
        <div
          ref={panelRef}
          className="acct-menu"
          data-od-id="acct-menu"
          role="menu"
          aria-label="账号与设置"
        >
          <div className="am-head" data-od-id="acct-menu-head">
            <span className="avatar" aria-hidden="true">
              {username ? username.slice(0, 1) : <Ico d={P.person} sw={1.7} />}
            </span>
            <span
              className="am-name"
              title={username ?? undefined}
              style={username ? undefined : { color: "var(--muted)" }}
            >
              {username ?? "未登录"}
            </span>
            <Badge full />
          </div>

          {onBookPrefs && (
            <button
              className="am-item"
              role="menuitem"
              data-od-id="acct-menu-bookprefs"
              onClick={() => {
                close();
                onBookPrefs();
              }}
            >
              <Ico d={P.tune} sw={1.7} />
              本书偏好
              <span className="am-hint">字号 · 行距 · 归档</span>
            </button>
          )}

          <div className="am-group">数据</div>
          <button className="am-item" role="menuitem" data-od-id="acct-menu-backup" onClick={runBackup}>
            <Ico d={P.backup} sw={1.7} />
            备份
            <span className="am-hint">选择文件夹导出</span>
          </button>
          <button
            className="am-item"
            role="menuitem"
            data-od-id="acct-menu-restore"
            onClick={() => {
              close();
              const bridge = (window as any).pywebview?.api;
              if (!bridge) {
                alert("恢复功能需要桌面版应用");
                return;
              }
              setRestoreOpen(true);
            }}
          >
            <Ico d={P.restore} sw={1.7} />
            恢复
            <span className="am-hint">从备份文件导入</span>
          </button>
          <button
            className="am-item"
            role="menuitem"
            data-od-id="acct-menu-config"
            onClick={() => {
              close();
              navigate("/config");
            }}
          >
            <Ico d={P.tune} sw={1.7} />
            模型配置 · API Key
            <span className="am-hint">去配置</span>
          </button>

          <div className="am-group">支持</div>
          {support && (
            <a
              className="am-item"
              role="menuitem"
              data-od-id="acct-menu-support"
              href={support}
              target="_blank"
              rel="noreferrer"
              onClick={() => close()}
            >
              <Ico d={P.chat} sw={1.7} />
              联系客服
              <span className="am-hint">新窗口打开</span>
            </a>
          )}

          <div className="am-foot">
            <button
              className="am-item danger"
              role="menuitem"
              data-od-id="acct-menu-logout"
              onClick={() => {
                // 轻确认：内联二步，Esc/外点复位
                if (!confirmLogout) {
                  setConfirmLogout(true);
                  return;
                }
                logout();
              }}
            >
              <Ico d={P.logout} sw={1.7} />
              {confirmLogout ? "确认退出？" : "退出登录"}
            </button>
            <span className="am-version" data-od-id="acct-menu-version">
              {formatVersion(version)}
            </span>
          </div>
        </div>,
        document.body,
      )}
      <RestoreModal
        open={restoreOpen}
        onClose={() => setRestoreOpen(false)}
        onGoConfig={() => {
          setRestoreOpen(false);
          navigate("/config");
        }}
      />
    </>
  );

  /** 徽章：触发钮短档 / 面板头完整档；失联（syncFailed）文案不变仅转 warn */
  function Badge({ full }: { full?: boolean }) {
    const judgment = {
      tier: tier.tier,
      is_member: tier.isMember,
      expired: tier.expired,
      trial_remaining_days: tier.trialRemainingDays,
    };
    if (full) {
      return (
        <span className="badge badge-muted" data-od-id="acct-menu-tier">
          {tierLabel(judgment)}
        </span>
      );
    }
    if (tier.loading) {
      return (
        <span className="badge badge-muted" data-od-id="acct-badge">
          …
        </span>
      );
    }
    const short = tierShort(judgment);
    if (!short) return null;
    const tone: Tone = tier.syncFailed ? "warn" : short.tone;
    return (
      <span className={BADGE_CLASS[tone]} data-od-id="acct-badge">
        {short.text}
      </span>
    );
  }
}
