<script setup lang="ts">
/**
 * C端客户端下载弹窗（cn-download-modal 规格的共享化）：
 * 打开时实时解析线上 latest.json，所见版本即所下版本；
 * 请求失败降级为兜底版本（warn pill）。落地页与控制台首页共用。
 */
import { ref, watch } from 'vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppModal from '@/components/ui/AppModal.vue'
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'
import {
  fetchLatestRelease,
  windowsInstallerUrl,
  macosInstallerUrl,
  RELEASES_PAGE_URL,
  type LatestRelease,
} from '@/constants/client-release'
import { brand } from '@/constants/brand'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const latest = ref<LatestRelease | null>(null)

watch(() => props.open, (open) => {
  if (!open) return
  latest.value = null
  void fetchLatestRelease().then((r) => { latest.value = r })
})
</script>

<template>
  <AppModal :open="open" :title="`下载${brand.name}`" @update:open="emit('update:open', $event)">
    <template v-if="!latest">
      <p class="dl-sub">正在获取最新版本…</p>
      <div class="mt-4 space-y-2.5">
        <div class="sk h-4 w-3/4"></div>
        <div class="sk h-4 w-1/2"></div>
        <div class="sk h-4 w-2/5"></div>
      </div>
    </template>
    <template v-else>
      <span class="dl-pill" :class="latest.degraded ? 'warn' : 'info'">
        {{ latest.degraded ? `未能获取最新版，当前 v${latest.version}` : `最新版 v${latest.version}` }}
      </span>
      <p class="dl-sub">选择你的系统，安装后注册即送 7 天全功能试用</p>
      <div class="mt-4 flex flex-col gap-2">
        <AppButton
          :href="windowsInstallerUrl(latest.version)"
          variant="primary"
          size="lg"
          block
        >
          <Ico :d="P.download" />
          下载 Windows 版
        </AppButton>
        <div class="dl-note"><span>Windows 安装包</span><span>.exe</span></div>
        <AppButton
          :href="macosInstallerUrl(latest.version)"
          variant="secondary"
          size="lg"
          block
        >
          <Ico :d="P.download" />
          下载 macOS 版
        </AppButton>
        <div class="dl-note"><span>macOS 磁盘镜像</span><span>.dmg</span></div>
      </div>
      <p class="dl-hint">macOS 首次打开若提示无法验证开发者：先点「完成」关掉提示（勿点「移到废纸篓」），再到 系统设置 → 隐私与安全性 点「仍要打开」</p>
      <p class="dl-hint" style="text-align: center; margin-top: 12px">
        <a :href="RELEASES_PAGE_URL" target="_blank" rel="noopener" class="lnk">查看其他版本 →</a>
      </p>
    </template>
  </AppModal>
</template>

<style scoped>
.dl-sub { margin: 10px 0 0; color: var(--muted); font-size: 13px; }
.dl-pill { display: inline-flex; align-items: center; height: 24px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 500; }
.dl-pill.info { background: var(--accent-soft); color: var(--accent); }
.dl-pill.warn { background: var(--warn-soft); color: var(--warn); }
.dl-note { display: flex; justify-content: space-between; margin-top: -4px; font-size: 12px; color: var(--muted); }
.dl-hint { margin: 14px 0 0; font-size: 12.5px; color: var(--muted); line-height: 1.6; }
</style>
