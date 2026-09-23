import { useState, useCallback } from 'react';
import { getToken } from '../lib/auth';
import { request } from '../lib/api';
import { toast } from '../lib/toast';

interface DeviceStatus {
  enrolled: boolean;
  device_name?: string;
  activated: boolean;
  reason?: { code: string; message: string } | null;
  device_count: number;
  active_limit: number;
}

export function useDeviceActivation() {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<DeviceStatus | null>(null);

  const refreshStatus = useCallback(async () => {
    const token = getToken();
    if (!token) return null;

    setLoading(true);
    try {
      // 探测类（quiet）：失败/401 一律静默回 null（原口径），不触发全局副作用
      const data = await request<DeviceStatus>('/auth/devices/current', { quiet: true });
      setStatus(data);
      return data;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const showToast = useCallback((status: DeviceStatus) => {
    if (status.enrolled && status.activated) {
      toast.success('新设备已激活，可使用全部功能');
    } else if (status.enrolled && !status.activated) {
      toast.info('新设备已注册，当前为免费模式');
    } else if (!status.enrolled && !status.activated) {
      toast.info('当前设备为免费模式');
    }
    // enrolled=false + activated=true → 不提示
  }, []);

  return { loading, status, refreshStatus, showToast };
}
