import fs from "fs";

import type { Page } from "@playwright/test";

export const BASE_URL = "http://localhost:8000";

export function url(hashPath: string) {
  return `${BASE_URL}/#${hashPath}`;
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
