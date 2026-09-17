import fs from "fs";

import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";

// 隔离栈错峰端口：E2E_CLIENT_API_URL 覆盖（默认仍是主栈 8000）
export const BASE_URL = process.env.E2E_CLIENT_API_URL || "http://localhost:8000";

export function url(hashPath: string) {
  return `${BASE_URL}/#${hashPath}`;
}

/**
 * 页面收敛（e2e-speedup-infra）：网络空闲 + 有限动画播完，替代赌动画时长的固定 sleep。
 * infinite 动画（跑马灯等）不等待；networkidle 超时视为已收敛（长轮询页面照常往下走）。
 */
export async function pageSettled(page: Page, timeout = 8000) {
  await page.waitForLoadState("networkidle", { timeout }).catch(() => {});
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter((a) => a.playState !== "infinite")
        .map((a) => a.finished.catch(() => {})),
    );
  });
}

/**
 * 后端直查轮询（e2e-speedup-infra）：等防抖 PATCH 真落库再断言，替代「赌 1.2s」。
 * until 返回真即返回查询结果；超时抛错（防抖丢失时快速红，而非静默假绿）。
 */
export async function pollBackend<T>(
  query: () => Promise<T>,
  until: (v: T) => boolean,
  timeout = 8000,
): Promise<T> {
  await expect.poll(async () => {
    try {
      return until(await query());
    } catch {
      return false; // 网络抖动继续轮询
    }
  }, { timeout }).toBe(true);
  return query();
}

/**
 * 稳定点击（e2e-speedup-infra 保险）：元素被重挂打断时自动重试，上限内点中为止。
 * 常规场景一次命中零额外等待；重挂风暴若复发，此处兜底而非 30s 超时假死
 * （风暴本身由书架请求预算守卫用例钉死）。
 */
export async function stableClick(loc: Locator, timeout = 10000) {
  await expect(async () => {
    await loc.click({ timeout: 2000 });
  }).toPass({ timeout });
}


/**
 * 更新提示条打桩（client-update-notify）。
 * "update" 载荷与原型 list.html / book.html 字面量一致（ADJUSTMENTS #15 parity 口径）；
 * "none" = 检测成功无更新；"fail" = 端点异常（应用侧必须静默不渲染）。
 * current 覆盖默认版本号（c-version-account-visibility：状态条/版本行断言用）。
 */
export function stubUpdateNotice(
  page: Page,
  mode: "update" | "none" | "fail",
  current?: string,
) {
  return page.route("**/api/update-check", (r) => {
    if (mode === "fail") {
      return r.fulfill({ status: 500, json: { detail: "boom" } });
    }
    if (mode === "none") {
      return r.fulfill({
        json: {
          current: current ?? "0.13",
          latest: "0.13",
          has_update: false,
          notes: "",
          notes_url: "",
          download_url: "",
        },
      });
    }
    return r.fulfill({
      json: {
        current: current ?? "0.11",
        latest: "0.13",
        has_update: true,
        notes: "提升章纲 AI 起草的稳定性，修复若干问题",
        notes_url: "https://www.awesomenovel.com/download/v0.13/notes.html",
        download_url: "https://www.awesomenovel.com",
      },
    });
  });
}

/** 原子写本地会话 config.json（e2e 注入用）。
 *
 * 直接 writeFileSync 会让宿主与容器内的读方撞车：半截 JSON → 后端 500
 * （`json.decoder.JSONDecodeError`），共享挂载下还可能触发 `disk I/O error`。
 * 先写临时文件再 rename，读方永远只看到完整内容。
 */
export function writeConfigAtomic(configPath: string, content: string) {
  const tmp = `${configPath}.tmp`;
  fs.writeFileSync(tmp, content);
  fs.renameSync(tmp, configPath);
}

// ── 测试自建书的 teardown（2026-09-10 用户拍板「要加」）────────────────────
// 背景：e2e 每个用例都建一本新书、从不删除 → 跑一次全量往书架塞 80+ 本，
// 本地库曾累积到 858 本（清理脚本扫掉 856 本）。
//
// 口径：**会话名下全清**。每个用例的会话都是当场新注册的 S端 用户（见各 spec 的
// sRegisterAndLogin），它名下的书**全部**是本次测试产物 → 用例结束逐本走产品删除路径：
//   · 只删自己名下的书（DELETE 校验归属，碰不到用户的书）
//   · 产品删除是**软删除**（status='deleted'），书架列表按 status 过滤 → 立刻看不见
//   · 不依赖「建书处逐个登记」——用例内联建书（没走辅助）也一并能清
//   · 失败静默：清理不该让用例变红（清不掉顶多留一本，不影响可见书架）

/** 测试书命名（e2e 一贯约定）：「短词 + 1~8 位数字」或 e2e-/probe- 前缀。
 *
 * 白名单式守卫——即使某次会话意外解析到用户自己的本地账号，也**不会**删掉
 * 《我在夜晚打吸血鬼》这类真书名（本地库 858 本测试书全部满足该模式）。
 */
export function isTestBookName(name: string | null | undefined): boolean {
  const n = name || "";
  return /[0-9]{1,8}$/.test(n) || /^(e2e|probe)[-_]/.test(n);
}

/** teardown：删除本会话名下、**名字符合测试书约定**的书（产品软删除路径）。
 *
 * 返回删除成功本数（便于断言/排查）。只删自己名下（DELETE 校验归属）+ 只删测试名，
 * 双保险确保碰不到用户的书。
 */
export async function cleanupSessionNovels(origin: string, token: string): Promise<number> {
  const auth = { Authorization: `Bearer ${token}` };
  let ok = 0;
  try {
    const r = await fetch(`${origin}/api/novels`, { headers: auth });
    if (!r.ok) return 0;
    const list = (await r.json()) as Array<{ id: string; name?: string }>;
    for (const n of list) {
      if (!isTestBookName(n.name)) continue; // 真书名一律不碰
      try {
        const d = await fetch(`${origin}/api/novels/${n.id}`, { method: "DELETE", headers: auth });
        if (d.ok) ok += 1;
      } catch {
        /* 单本失败不影响其余 */
      }
    }
  } catch {
    /* 网络异常不阻断用例收尾 */
  }
  return ok;
}
