/**
 * 版本可视性单源（c-version-account-visibility ＋ c-version-build-info）：
 * - formatVersion：状态条/两弹窗版本行/UpdateNotice rider 共用的文案口径
 *   （正式版 v{X.Y.Z} / dev 构建＋构建信息「{分支}@{commit前5位}」/ 构建信息缺失
 *   降级「开发版 dev」（不渲染「vdev」）/ 失败「版本未知」）。裸 string 入参兼容
 *   UpdateNotice（只拿得到 state.current）——视为无构建信息。
 *   c-version-build-info 两道防御：commit 统一截前 5 位（后端宽容 5~40 位，
 *   展示口径在这里钉死）；branch/commit 任一为空视为构建信息不可用走降级。
 * - useClientVersion：应用级版本缓存（c-query-cache-layer：并入 React Query）。
 *   语义与原手写缓存逐条对应：
 *   · 成功缓存整会话共享（staleTime Infinity）——弹窗打开不发新请求，状态条同源；
 *   · 失败/缺失 current 视同错误不缓存——后续消费方挂载自动重试，防启动瞬间
 *     本地后端未就绪把整会话锁死在「版本未知」；
 *   · 后挂载方重试成功经缓存广播拉起先挂载方（状态条不滞后于弹窗）。
 *   数据源 = GET /update-check 的 {current, build}（版本自报单一来源）。
 */
import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";

export interface ClientBuildInfo {
  branch: string;
  commit: string;
}

export interface ClientVersionInfo {
  current: string;
  build: ClientBuildInfo | null;
}

function normalizeBuild(raw: unknown): ClientBuildInfo | null {
  if (!raw || typeof raw !== "object") return null;
  const branch = (raw as { branch?: unknown }).branch;
  const commit = (raw as { commit?: unknown }).commit;
  if (typeof branch === "string" && branch && typeof commit === "string" && commit) {
    return { branch, commit };
  }
  return null;
}

export function formatVersion(info: ClientVersionInfo | string | null | undefined): string {
  const current = info == null ? null : typeof info === "string" ? info : info.current;
  if (!current) return "版本未知";
  if (current === "dev") {
    const build = typeof info === "string" ? null : info?.build;
    if (build?.branch && build?.commit) return `${build.branch}@${build.commit.slice(0, 5)}`;
    return "开发版 dev";
  }
  return `v${current}`;
}

const CLIENT_VERSION_KEY = ["client-version"] as const;

async function fetchVersion(): Promise<ClientVersionInfo> {
  const r = (await request("/update-check", { quiet: true })) as {
    current?: string;
    build?: unknown;
  };
  // 缺失 current 视同失败（throw → 不缓存，下次挂载自动重试）
  if (!r?.current) throw new Error("version unavailable");
  return { current: r.current, build: normalizeBuild(r.build) };
}

export function useClientVersion(): ClientVersionInfo | null {
  const { data } = useQuery<ClientVersionInfo>({
    queryKey: CLIENT_VERSION_KEY,
    queryFn: fetchVersion,
    retry: false, // 失败不原地重试：留待下次挂载重试（原「失败不缓存」语义）
    staleTime: Infinity, // 成功即整会话共享
    refetchOnWindowFocus: false,
  });
  return data ?? null;
}
