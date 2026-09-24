/**
 * S 端门户地址（购买 / 续费 / 开通试用入口）。
 * 公开营销地址（非密钥）；运行时以后端 /auth/config 的 portal_url 为准
 * （config.json 可覆盖），此处为未登录页（Landing 等）的兜底值。
 */
import { api } from "./api";
import { queryClient } from "./queryClient";

export const PORTAL_URL =
  (import.meta.env.VITE_PORTAL_URL as string | undefined) ||
  "https://novel-s-web-ai-novel-test-d1ghsr86ra814c12c.webapps.tcloudbase.com";

const PORTAL_URL_KEY = ["portal-url"] as const;

/** 测试钩子：重置门户地址缓存。 */
export function resetPortalUrlCache() {
  queryClient.removeQueries({ queryKey: PORTAL_URL_KEY });
}

/** 拉取（并缓存）S 端门户地址；失败降级空串。MemberBlockPrompt 与 UpgradeModal 同源取用。
 * c-query-cache-layer：缓存并入应用级 QueryClient（fetchQuery，staleTime Infinity
 * ＝原模块级缓存「取一次整会话用」语义）。 */
export function fetchPortalUrl(): Promise<string> {
  return queryClient.fetchQuery({
    queryKey: PORTAL_URL_KEY,
    staleTime: Infinity,
    queryFn: async () => {
      try {
        const cfg = await api.get("/auth/config");
        return cfg?.portal_url || "";
      } catch {
        return "";
      }
    },
  });
}

/** 外跳地址安全校验：仅 http/https，拒绝 localhost/环回/私有/保留地址。 */
export function isSafeExternalUrl(url: string): boolean {
  if (!url) return false;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return false;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  const h = u.hostname.toLowerCase();
  if (h === "localhost" || h.endsWith(".localhost")) return false;
  if (h === "0.0.0.0" || h === "::1" || h === "[::1]") return false;
  if (h === "127" || h.startsWith("127.") || h.startsWith("10.")) return false;
  if (h.startsWith("192.168.") || h.startsWith("169.254.") || h.startsWith("172.")) {
    // 172.16.0.0–172.31.255.255 为私有段；其余 172.x 放行
    const m = h.match(/^172\.(\d+)\./);
    if (!m || (parseInt(m[1], 10) >= 16 && parseInt(m[1], 10) <= 31)) return false;
  }
  return true;
}
