import request from './request'
import type { ApiResponse } from './request'

export function apiAuthorize(
  username: string,
  password: string,
  pc_hash: string,
  pc_name?: string,
  device_profile?: string,
  challenge?: string,
): Promise<ApiResponse<{ message: string; tier: string; expires_at: string }>> {
  // challenge = 桌面端本机配对密钥的 SHA-256（s-security-hardening）：后端落库，
  // 此后令牌只经 /api/pair/exchange 发给持有本机密钥者
  return request.post('/authorize', { username, password, pc_hash, pc_name, device_profile, challenge }).then(r => r.data)
}

export function apiResetPassword(
  username: string,
  security_answer: string,
  new_password: string,
): Promise<ApiResponse> {
  return request.post('/reset_password', { username, security_answer, new_password }).then(r => r.data)
}
