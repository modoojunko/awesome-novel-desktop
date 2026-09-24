/**
 * 版本可视性单源（c-version-account-visibility）：
 * - formatVersion：状态条/两弹窗版本行/UpdateNotice rider 三处共用的文案口径
 *   （正式版 v{X.Y.Z} / dev 构建显「开发版 dev」不渲染「vdev」/ 失败「版本未知」）。
 * - useClientVersion：应用级版本缓存（c-query-cache-layer：并入 React Query，
 *   外部接口不变）。语义与原手写缓存逐条对应：
 *   · 成功缓存整会话共享（staleTime Infinity）——弹窗打开不发新请求，状态条同源；
 *   · 失败/缺失 current 视同错误不缓存——后续消费方挂载自动重试，防启动瞬间
 *     本地后端未就绪把整会话锁死在「版本未知」；
 *   · 后挂载方重试成功经缓存广播拉起先挂载方（状态条不滞后于弹窗）。
 *   数据源 = GET /update-check 的 current（版本自报单一来源）。
 */
import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";

export function formatVersion(current: string | null | undefined): string {
  if (!current) return "版本未知";
  if (current === "dev") return "开发版 dev";
  return `v${current}`;
}

const CLIENT_VERSION_KEY = ["client-version"] as const;

async function fetchVersion(): Promise<string> {
  const r = (await request("/update-check", { quiet: true })) as {
    current?: string;
  };
  // 缺失 current 视同失败（throw → 不缓存，下次挂载自动重试）
  if (!r?.current) throw new Error("version unavailable");
  return r.current;
}

export function useClientVersion(): string | null {
  const { data } = useQuery<string>({
    queryKey: CLIENT_VERSION_KEY,
    queryFn: fetchVersion,
    retry: false, // 失败不原地重试：留待下次挂载重试（原「失败不缓存」语义）
    staleTime: Infinity, // 成功即整会话共享
    refetchOnWindowFocus: false,
  });
  return data ?? null;
}
