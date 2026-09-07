/**
 * 版本可视性单源（c-version-account-visibility）：
 * - formatVersion：状态条/两弹窗版本行/UpdateNotice rider 三处共用的文案口径
 *   （正式版 v{X.Y.Z} / dev 构建显「开发版 dev」不渲染「vdev」/ 失败「版本未知」）。
 * - useClientVersion：应用级版本缓存（模块级，仅缓存成功结果——失败不缓存，后续
 *   消费方挂载自动重试，防启动瞬间本地后端未就绪把整会话锁死在「版本未知」）。
 *   成功时广播给全部已挂载消费方：状态条根部挂载不重挂，若首取失败、后开的
 *   弹窗重试成功须把状态条一并拉起，避免「版本未知 / v0.15.1」同屏不一致。
 *   弹窗打开不发新请求，直接吃缓存。数据源 = GET /update-check 的 current（版本自报单一来源）。
 */
import { useEffect, useState } from "react";
import { request } from "@/lib/api";

export function formatVersion(current: string | null | undefined): string {
  if (!current) return "版本未知";
  if (current === "dev") return "开发版 dev";
  return `v${current}`;
}

let cachedVersion: string | null = null;
let inflight: Promise<string | null> | null = null;
const listeners = new Set<(v: string | null) => void>();

function fetchVersion(): Promise<string | null> {
  if (cachedVersion) return Promise.resolve(cachedVersion);
  if (!inflight) {
    inflight = request("/update-check", { quiet: true })
      .then((r: any) => {
        if (r?.current) {
          cachedVersion = r.current;
          listeners.forEach((notify) => notify(cachedVersion));
        }
        return r?.current ?? null;
      })
      .catch(() => null)
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

export function useClientVersion(): string | null {
  const [version, setVersion] = useState<string | null>(cachedVersion);

  useEffect(() => {
    if (version) return;
    listeners.add(setVersion);
    fetchVersion();
    return () => {
      listeners.delete(setVersion);
    };
  }, []);

  return version;
}
