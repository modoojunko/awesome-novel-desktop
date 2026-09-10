import { useEffect } from "react";
import { request } from "@/lib/api";
import { setToken } from "@/lib/auth";

// 云托管 MinNum=0 缩容后首次请求触发冷启动（30-60s），期间 check-auth 返回
// code -1（S端不可达）或请求失败。失败请求本身已唤醒实例，间隔重试即可自愈。
const RETRY_DELAYS_MS = [20_000, 20_000, 20_000];

/**
 * 应用启动时静默自愈本地登录态：
 * 后端 OAuth 会话有效（GET /auth/check-auth 返回 token）即写回 localStorage，
 * 解决「后端 config.json token 有效、前端 localStorage 副本丢失/被清」导致的重复登录。
 * - code 0：会话有效，写回后结束
 * - code 1：后端明确未登录；若为结构化会话失效（account-deletion：账号已注销/
 *   会话作废）则清本地凭据回登录入口，并持久化提示（作品仅存本地，不受影响）
 * - code 2：注销撤销期（付费与套餐功能暂停），凭据保留（可撤销恢复），仅记录提示
 * - code -1 / 请求失败：S端 冷启动或后端未就绪，按 RETRY_DELAYS_MS 重试
 * 幂等：失败静默，不改动现有状态，不跳转（失效信号除外）。
 */
export function useAuthHeal() {
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        timer = setTimeout(resolve, ms);
      });

    (async () => {
      for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
        if (attempt > 0) await sleep(RETRY_DELAYS_MS[attempt - 1]);
        if (cancelled) return;
        try {
          const res = await request("/auth/check-auth");
          if (cancelled) return;
          if (res.code === 0) {
            if (res.data?.token && res.data.token !== "dev-token") {
              setToken(res.data.token, res.data.username ?? "");
            }
            return;
          }
          if (res.code === 1) {
            // 会话失效（account-deletion：账号已注销/服务端会话作废）：
            // 清本地凭据回登录入口，登录页展示失效提示（作品仅存本地，不受影响）
            if (res.data?.session_invalid) {
              localStorage.removeItem("auth_token");
              localStorage.removeItem("auth_username");
              if (res.data.message) sessionStorage.setItem("auth_notice", res.data.message);
              // 回**登录页**而不是营销落地页：失效提示的消费方是 LoginPage
              // （读后即焚，落 / 的话提示永远没人展示）。同时广播一次：若
              // LoginPage 已被 401 拦截器先送到 /login，它挂载时提示还没写入，
              // 不补读这条消息就丢了。
              window.location.hash = "#/login";
              window.dispatchEvent(new Event("auth-notice-updated"));
            }
            return;
          }
          if (res.code === 2) {
            // 注销撤销期：凭据保留（可撤销恢复），仅持久化提示（付费与套餐功能暂停）
            if (res.data?.message) sessionStorage.setItem("auth_notice", res.data.message);
            return;
          }
        } catch {
          // C端后端不可达：稍后重试
        }
        // code -1（S端 冷启动）或请求失败 → 继续下一轮
      }
    })();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);
}
