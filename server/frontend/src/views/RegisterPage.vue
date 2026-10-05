<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import AppInput from '@/components/ui/AppInput.vue'
import { SECURITY_QUESTIONS } from "@/constants/security-questions"
import AppButton from '@/components/ui/AppButton.vue'
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'

const router = useRouter()
const route = useRoute()
const session = useSessionStore()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const securityQuestion = ref('')
const securityAnswer = ref('')
const agreeTerms = ref(false)
const agreePrivacy = ref(false)
const errorMsg = ref('')

const passwordError = computed(() => {
  if (password.value && password.value.length < 6) return '密码至少 6 位'
  return ''
})

const confirmError = computed(() => {
  if (!confirmPassword.value) return ''
  if (confirmPassword.value !== password.value) return '两次密码不一致'
  return ''
})

const canSubmit = computed(() => {
  return username.value
    && password.value.length >= 6
    && confirmPassword.value === password.value
    && securityQuestion.value
    && securityAnswer.value
    && agreeTerms.value
    && agreePrivacy.value
    && !session.isLoading
})

const questionOptions = SECURITY_QUESTIONS

const showCustomInput = ref(false)

function onQuestionChange(e: Event) {
  const val = (e.target as HTMLSelectElement).value
  securityQuestion.value = val
  showCustomInput.value = val === '__custom__'
}

const customQuestion = ref('')

async function handleRegister() {
  if (!canSubmit.value) return
  errorMsg.value = ''

  const question = showCustomInput.value ? customQuestion.value : securityQuestion.value
  const result = await session.register(username.value, password.value, question, securityAnswer.value)
  if (result.ok) {
    // 设备授权流进来的注册：带原 query 回 /auth 完成绑定，不丢授权上下文
    if (route.query.pc_hash) {
      router.push({ path: '/auth', query: route.query })
    } else {
      router.push('/dashboard')
    }
  } else {
    errorMsg.value = result.msg || '注册失败'
  }
}
</script>

<template>
  <div class="auth-card wide">
    <div class="head-row">
      <h1>注册</h1>
      <span class="pill pill-tag pill-accent">注册另送 7 天 PRO 级试用</span>
    </div>
    <p class="sub">几分钟完成，马上开始写作</p>

    <p v-if="errorMsg" class="notice err">
      <Ico :d="P.alert" />{{ errorMsg }}
    </p>

    <div class="form-area">
      <!-- 组 1：必填账号信息 -->
      <p class="grp-t serif">账号信息</p>
      <AppInput v-model="username" label="用户名" autocomplete="username" hint="3–32 位字母、数字、下划线或连字符" />
      <AppInput
        v-model="password"
        type="password"
        label="密码"
        autocomplete="new-password"
        :error="passwordError"
        hint="至少 6 位"
      />
      <AppInput
        v-model="confirmPassword"
        type="password"
        label="确认密码"
        :error="confirmError"
      />

      <!-- 组 2：密保设置 -->
      <p class="grp-t serif">密保设置 <span class="grp-sub">· 用于找回密码</span></p>
      <div class="field">
        <select
          class="input"
          :value="securityQuestion"
          @change="onQuestionChange"
        >
          <option
            v-for="opt in questionOptions"
            :key="opt.value"
            :value="opt.value"
            :disabled="opt.disabled"
          >
            {{ opt.label }}
          </option>
        </select>
      </div>

      <AppInput
        v-if="showCustomInput"
        v-model="customQuestion"
        label="自定义问题"
        placeholder="输入你的密保问题"
      />

      <AppInput
        v-model="securityAnswer"
        label="密保答案"
        placeholder="请输入答案"
      />

      <!-- 法律文件双勾选（legal-four-docs）：注册即同意，未勾选不可提交 -->
      <div class="legal-checks">
        <label class="agr-chk">
          <input v-model="agreeTerms" type="checkbox" />
          <span>我已阅读并同意
            <a href="/legal/user-agreement.html" target="_blank" class="lnk">《用户服务协议》</a>、
            <a href="/legal/payment-notice.html" target="_blank" class="lnk">《付费须知》</a>、
            <a href="/legal/refund-policy.html" target="_blank" class="lnk">《退款政策》</a>
          </span>
        </label>
        <label class="agr-chk">
          <input v-model="agreePrivacy" type="checkbox" />
          <span>我已阅读并同意
            <a href="/legal/privacy-policy.html" target="_blank" class="lnk">《隐私政策》</a>
          </span>
        </label>
      </div>

      <AppButton
        variant="primary"
        size="lg"
        block
        :loading="session.isLoading"
        :disabled="!canSubmit"
        @click="handleRegister"
      >
        注册
      </AppButton>
    </div>

    <p class="foot-lnk">
      已有账号？<router-link to="/login" class="lnk">登录</router-link>
    </p>
  </div>
</template>

<style scoped>
/* 品牌行已删——营销壳 mkt-nav 已有 logo，同屏不重复 */
.auth-card.wide { max-width: 420px; text-align: center; }
.head-row { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 18px; }
h1 { font-family: var(--font-display); font-size: 28px; font-weight: 600; margin: 0; }
.sub { font-size: 13.5px; color: var(--muted); margin: 4px 0 22px; }
.form-area { text-align: left; }
.grp-t { font-size: 15px; font-weight: 600; margin: 6px 0 10px; }
.grp-t:first-child { margin-top: 0; }
.grp-sub { font-family: var(--font-body); font-size: 12.5px; font-weight: 400; color: var(--muted); }
.form-area .btn { margin-top: 8px; }
.foot-lnk { font-size: 13px; color: var(--muted); margin: 16px 0 0; }
.legal-checks { text-align: left; margin: 14px 0 4px; display: flex; flex-direction: column; gap: 8px; }
.agr-chk { display: flex; gap: 8px; align-items: flex-start; font-size: 12.5px; line-height: 1.55; cursor: pointer; }
.agr-chk input { margin-top: 2px; accent-color: var(--accent); width: 14px; height: 14px; flex: none; }
.agr-chk a { color: var(--accent); }
</style>
