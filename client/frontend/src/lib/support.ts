import { fetchPortalUrl, isSafeExternalUrl } from "./portal";

/** S端 客服页外跳地址单源（从 Navbar 抽取，c-s-entitlement-sync）：
 * portal_url 去尾斜杠拼 /support；取不到则返回空串（调用方不出死链）。 */
export async function supportUrl(): Promise<string> {
  const portal = (await fetchPortalUrl()).replace(/\/+$/, "");
  const url = portal ? `${portal}/support` : "";
  return isSafeExternalUrl(url) ? url : "";
}
