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
import LegacyMigrateModal from "@/components/LegacyMigrateModal";
import RestoreModal from "@/components/RestoreModal";
import { Ico, P } from "@/components/icons";
import { useLegacyDb } from "@/hooks/useLegacyDb";
import { useTier } from "@/hooks/useTier";
import { api, errMessage, type ApiError } from "@/lib/api";
import { getUsername, logout } from "@/lib/auth";
import { getLastProbe, openPackModal } from "@/lib/packProbe";
import { supportUrl } from "@/lib/support";
import { formatVersion, useClientVersion } from "@/lib/version";
import { queryClient } from "@/lib/queryClient";
import { queryKeys } from "@/lib/queryKeys";
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
  // db-generation：找回旧书（条件菜单项——有未抑制候选才显示；单点渲染弹窗）
  const [migrateOpen, setMigrateOpen] = useState(false);
  const legacyDb = useLegacyDb();
  const migrateCandidates = (legacyDb.status?.candidates ?? []).filter((c) => !c.suppressed);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // 空态按钮 CustomEvent → 打开同一弹窗（避免双实例双轮询）
  useEffect(() => {
    const on = () => setMigrateOpen(true);
    window.addEventListener("legacy-migrate:open", on);
    return () => window.removeEventListener("legacy-migrate:open", on);
  }, []);

  // c-db-per-version：空态第二出口「从备份包恢复」（换安装目录/换机用户的唯一出路）
  useEffect(() => {
    const on = () => setRestoreOpen(true);
    window.addEventListener("restore:open", on);
    return () => window.removeEventListener("restore:open", on);
  }, []);

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
    /* v8 ignore start -- 防御分支：position 只在 open 期的布局效果/滚动监听里调用，
       那时两个 ref 必已挂载，测试无法构造出 null 组合 */
    if (!t || !p) return;
    /* v8 ignore stop */
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
        /* v8 ignore start -- 防御分支：键盘监听只在 open 期注册，那时 panelRef 必已挂载 */
        ...(panelRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []),
        /* v8 ignore stop */
      ].filter((el) => !el.hasAttribute("hidden"));
      /* v8 ignore start -- 防御分支：面板展开时恒有 ≥4 个未 hidden 的 menuitem */
      if (!items.length) return;
      /* v8 ignore stop */
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

  /** 恢复弹窗：单点渲染在面板之外（它曾只挂在「面板展开」那支 return 里 → 点「恢复」
   *  先 close() 收起面板，组件随即走提前 return 分支，模态永远不在渲染树里，入口自
   *  #346 起一直打不开，09-18 覆盖专项发现）。单点渲染同时避免 open 翻转时元素换位重挂。 */
  const restoreModal = (
    <RestoreModal
      open={restoreOpen}
      onClose={() => setRestoreOpen(false)}
      onGoConfig={() => {
        setRestoreOpen(false);
        navigate("/config");
      }}
    />
  );

  // db-generation：找回旧书弹窗（单点渲染；完成后刷书架+跳转）
  const migrateModal = (
    <LegacyMigrateModal
      open={migrateOpen}
      candidates={migrateCandidates}
      quarantined={legacyDb.status?.quarantined ?? []}
      onClose={() => {
        // 弹窗关闭时如果迁移还在跑 → 启动后台守望（完成→toast+刷书架）
        setMigrateOpen(false);
        void legacyDb.refresh();
        void api.get("/backup/db-migration/status", { quiet: true }).then((res) => {
          if (res.data?.state === "running" && res.data?.kind === "migration") {
            startBgWatch();
          }
        }).catch(() => {});
      }}
      onDone={() => {
        navigate("/novels");
        queryClient.invalidateQueries({ queryKey: queryKeys.novels });
      }}
    />
  );

  // 后台迁移守望（弹窗关闭后：轮询到完成→toast＋书架刷新；>120s→超时提示）
  const bgWatchRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bgStartRef = useRef(0);

  useEffect(() => {
    return () => {
      if (bgWatchRef.current) clearInterval(bgWatchRef.current);
    };
  }, []);

  const startBgWatch = useCallback(() => {
    if (bgWatchRef.current) clearInterval(bgWatchRef.current);
    bgStartRef.current = Date.now();
    bgWatchRef.current = setInterval(async () => {
      try {
        const res = await api.get("/backup/db-migration/status", { quiet: true });
        const d = res.data;
        if (d?.state === "done") {
          clearInterval(bgWatchRef.current!);
          bgWatchRef.current = null;
          const rep = d.report;
          if (rep?.status === "ok") {
            import("@/lib/toast").then(({ toast }) => {
              toast.success(`已带回 ${rep.book_count_migrated ?? "?"} 本书`);
            });
          } else {
            import("@/lib/toast").then(({ toast }) => {
              toast.error("带回没有完成，可从菜单重新打开向导重试");
            });
          }
          queryClient.invalidateQueries({ queryKey: queryKeys.novels });
          void legacyDb.refresh();
        } else if (d?.state === "error" || d?.state === "idle") {
          clearInterval(bgWatchRef.current!);
          bgWatchRef.current = null;
          import("@/lib/toast").then(({ toast }) => {
            toast.info("带回已停止，可从菜单重新打开向导");
          });
          void legacyDb.refresh();
        } else if (Date.now() - bgStartRef.current > 120_000) {
          clearInterval(bgWatchRef.current!);
          bgWatchRef.current = null;
          import("@/lib/toast").then(({ toast }) => {
            toast.info("带回耗时较长，可从菜单「带回旧版作品」查看进度");
          });
        }
      } catch {
        /* 静默重试 */
      }
    }, 1000);
  }, [legacyDb]);

  // 备份：桌面壳选文件夹 → 本地后端直写导出（原全局设置弹窗流程原样迁移）
  const runBackup = async () => {
    close();
    const bridge = (window as any).pywebview?.api;
    let dir: string | null = null;
    if (bridge) {
      dir = await bridge.pick_folder();
    } else {
      // B/S 模式：无原生文件夹弹窗，路径输入兜底（后端直写，API 同一条）
      dir = prompt("备份保存到哪个文件夹？（输入完整路径，如 ~/Backups）", "");
    }
    if (!dir || !dir.trim()) return;
    dir = dir.trim();
    try {
      // 走 api 封装（自动带 Authorization；裸 fetch 曾致 401，与下载成稿同一缺陷）
      await api.post("/backup/export/start", {
        kind: "backup",
        target_dir: dir,
        include_config: true,
      });
      alert("备份已开始，完成后文件将保存在所选目录");
    } catch (e) {
      // 409 detail 结构化（job_runner running_kind）：api 封装已把 detail.message 映射进 message
      const err = e as ApiError;
      // api.ts 对 4xx 保证 message 恒非空（detail 为空串/对象无 message/响应体 null 都回落通用文案）
      /* v8 ignore start -- 防御分支：上一行不变量成立后，`||` 右臂不可达；空 detail 的实际文案由 api 测试钉住 */
      const conflictMsg = err.message || "已有任务在进行中";
      /* v8 ignore stop */
      if (err.status === 409) alert(conflictMsg);
      else alert("备份启动失败：" + errMessage(e, "请重试"));
    }
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
          className={"acct-trigger" + (open ? " open" : "")}
          data-od-id="acct-trigger"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => (open ? close() : setOpen(true))}
        >
          <span className="avatar" aria-hidden="true">
            {username ? username.slice(0, 1) : <Ico d={P.person} sw={1.7} />}
          </span>
          <Badge />
          <Ico className="caret" d={P.chevronDown} sw={1.7} />
        </button>
      </div>
        {open &&
          createPortal(
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
            <span className="am-hint">选择文件夹保存</span>
          </button>
          <button
            className="am-item"
            role="menuitem"
            data-od-id="acct-menu-restore"
            onClick={() => {
              close();
              setRestoreOpen(true);
            }}
          >
            <Ico d={P.restore} sw={1.7} />
            恢复
            <span className="am-hint">从备份文件导入</span>
          </button>
          {migrateCandidates.length > 0 && (
            <button
              className="am-item"
              role="menuitem"
              data-od-id="acct-menu-migrate"
              onClick={() => {
                close();
                setMigrateOpen(true);
              }}
            >
              <Ico d={P.doc} sw={1.7} />
              带回旧版作品
              <span className="am-hint">把上一版的作品带过来</span>
            </button>
          )}
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
          {/* 写作能力（c-prompt-pack-onboard-modal）：与「模型配置 · API Key」并行的
              数据组入口，点击开同一弹窗（手动检查更新）；foot 小字行随本批退役 */}
          <button
            className="am-item"
            role="menuitem"
            data-od-id="acct-menu-pack"
            data-testid="acct-menu-pack"
            onClick={() => {
              close();
              openPackModal({ mode: "manual" });
            }}
          >
            <Ico d={P.pack} sw={1.7} />
            写作能力
            <span className="am-hint" data-testid="acct-menu-pack-hint">
              {packHint()}
            </span>
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
      {restoreModal}
      {migrateModal}
    </>
  );

  /** 写作能力 hint 三态（design D6）：已就绪 vX／有新版本（最近探测缓存）／未就绪 */
  function packHint(): string {
    if (tier.pack?.phase === "ready") {
      return getLastProbe()?.update_available ? "有新版本" : `已就绪 v${tier.pack.version ?? "-"}`;
    }
    return "未就绪";
  }

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
