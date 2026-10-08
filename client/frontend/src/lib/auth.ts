import { resetLicenseCache } from '@/lib/licenseCache';
import { resetPackProbeState } from '@/lib/packProbe';

const TOKEN_KEY = 'auth_token';
const USERNAME_KEY = 'auth_username';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string, username: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
}

export function getUsername(): string | null {
  return localStorage.getItem(USERNAME_KEY);
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

/** 手动退出（区别于会话过期）：清凭据并回首页。权益缓存同批清——
 *  换账号登录不得沿用上一账号的 verify 快照（c-silent-data-guards）。 */
export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  sessionStorage.setItem('manual_logout', '1');
  resetLicenseCache();
  resetPackProbeState(); // 写作能力探测缓存随登出清（换号不沿用，评审 P2-3）
  window.location.hash = '#/';
}
