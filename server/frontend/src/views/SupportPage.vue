<script setup lang="ts">
import { computed, ref } from 'vue'
import AppButton from '@/components/ui/AppButton.vue'
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'
import {
  SUPPORT_EMAIL,
  SUPPORT_REPLY_HOURS,
  PRIVACY_RESPONSE_WORKDAYS,
  ACCOUNT_DELETION_WORKDAYS,
  INVOICE_WORKDAYS,
} from '@/constants/support'
import { brand } from '@/constants/brand'

const mailtoHref = computed(() => `mailto:${SUPPORT_EMAIL}`)

/** 场景卡"就此写邮件"链接：mailto 预填主题，省一步手填 */
function mailtoFor(subject: string) {
  return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(`${brand.name}·${subject}`)}`
}

const copied = ref(false)
async function copyEmail() {
  try {
    await navigator.clipboard.writeText(SUPPORT_EMAIL)
  } catch {
    // 非 https/权限被拒时降级选区复制
    const ta = document.createElement('textarea')
    ta.value = SUPPORT_EMAIL
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}

const topics = [
  {
    title: '退款与订单问题',
    desc: '对订单或退款有疑问，请写明以下信息：',
    items: ['订单号（可在订单详情页复制）', '付款时间与付款方式', '您的具体诉求'],
    sla: `我们会在 ${SUPPORT_REPLY_HOURS} 小时内答复`,
    subject: '退款咨询',
  },
  {
    title: '发票申请',
    desc: '需要开具电子普通发票，请提供：',
    items: ['订单号', '发票抬头（个人或企业名称）', '企业抬头需附税号'],
    sla: `发票一般在 ${INVOICE_WORKDAYS} 个工作日内开具`,
    subject: '发票申请',
  },
  {
    title: '注销账号',
    desc: '申请注销账号，请在邮件中：',
    items: ['写明您的账号（用户名或注册邮箱）', '明确表达"申请注销账号"'],
    sla: `${ACCOUNT_DELETION_WORKDAYS} 个工作日内完成处理；未消耗套餐按《退款政策》办理`,
    subject: '申请注销账号',
  },
  {
    title: '账号安全',
    desc: '发现账号被盗用或有安全风险，请尽快告诉我们：',
    items: ['出现了什么异常现象', '最近一次正常使用的大致时间'],
    sla: '安全类问题优先处理',
    subject: '账号安全',
  },
  {
    title: '个人信息权利',
    desc: '查询、更正、删除您的个人信息，或撤回授权同意：',
    items: ['您的账号（用户名或注册邮箱）', '希望行使的权利与涉及的信息范围'],
    sla: `${PRIVACY_RESPONSE_WORKDAYS} 个工作日内响应`,
    subject: '个人信息请求',
  },
  {
    title: '一般使用问题',
    desc: '使用中遇到 bug 或异常，附上这些信息能更快定位：',
    items: ['客户端版本号（设置中可查看）', '操作系统与版本', '问题截图或录屏', '复现步骤'],
    sla: `一般问题 ${SUPPORT_REPLY_HOURS} 小时内回复`,
    subject: '使用问题反馈',
  },
]
</script>

<template>
  <div class="support-page">
    <div class="support-in">
      <h1>联系客服</h1>
      <p class="sub">写一封邮件告诉我们您遇到的问题，附上对应信息能更快得到处理</p>

      <div class="mail-hero">
        <p class="mail-label">客服邮箱</p>
        <p class="mail-addr serif">{{ SUPPORT_EMAIL }}</p>
        <div class="mail-actions">
          <AppButton :href="mailtoHref" size="lg">发邮件给我们</AppButton>
          <AppButton variant="secondary" size="lg" @click="copyEmail">
            {{ copied ? '已复制' : '复制邮箱' }}
          </AppButton>
        </div>
      </div>

      <p class="notice info">
        <Ico :d="P.info" />一般问题我们会在 {{ SUPPORT_REPLY_HOURS }} 小时内回复；个人信息相关请求在
        {{ PRIVACY_RESPONSE_WORKDAYS }} 个工作日内响应。
      </p>

      <section v-for="t in topics" :key="t.title" class="panel compact topic">
        <h2>{{ t.title }}</h2>
        <p class="t-desc">{{ t.desc }}</p>
        <ul>
          <li v-for="i in t.items" :key="i">{{ i }}</li>
        </ul>
        <div class="t-foot">
          <span class="t-sla">{{ t.sla }}</span>
          <a class="lnk" :href="mailtoFor(t.subject)">就此写邮件</a>
        </div>
      </section>

      <p class="foot-hint">
        没有收到回复？请先检查邮箱的垃圾邮件文件夹；若邮件被退回，请核对收件地址后
        <a class="lnk" :href="mailtoHref">重新发送</a>。
      </p>
    </div>
  </div>
</template>

<style scoped>
.support-page {
  display: grid;
  place-items: safe center;
  padding: 40px 24px 56px;
}
.support-in {
  width: 100%;
  max-width: 620px;
  text-align: center;
}
.support-in h1 {
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 600;
  margin: 0;
}
.support-in .sub {
  font-size: 13.5px;
  color: var(--muted);
  margin: 0 0 22px;
}

.mail-hero {
  background: var(--accent-soft);
  border: 1px solid color-mix(in oklch, var(--accent) 30%, transparent);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  margin-bottom: 16px;
}
.mail-label {
  font-size: 12.5px;
  color: var(--muted);
  margin: 0 0 6px;
}
.mail-addr {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin: 0 0 16px;
}
.mail-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.support-in :deep(.notice) {
  text-align: left;
}

.topic {
  text-align: left;
  margin-bottom: 12px;
}
.topic h2 {
  font-family: var(--font-display);
  font-size: 15.5px;
  font-weight: 600;
  margin: 0 0 4px;
}
.t-desc {
  font-size: 13px;
  color: var(--muted);
  margin: 0 0 8px;
}
.topic ul {
  margin: 0;
  padding-left: 18px;
  font-size: 13.5px;
  line-height: 1.8;
}
.t-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}
.t-sla {
  font-size: 12.5px;
  color: var(--muted);
}
.t-foot .lnk {
  font-size: 13px;
  flex: none;
}

.foot-hint {
  font-size: 12.5px;
  color: var(--muted);
  margin: 20px 0 0;
  line-height: 1.7;
}
</style>
