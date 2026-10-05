import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from '@/stores/session'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/PublicLayout.vue'),
    children: [
      {
        path: '',
        name: 'landing',
        component: () => import('@/views/LandingPage.vue'),
      },
      {
        path: 'login',
        name: 'login',
        meta: { guestOnly: true },
        component: () => import('@/views/LoginPage.vue'),
      },
      {
        path: 'register',
        name: 'register',
        meta: { guestOnly: true },
        component: () => import('@/views/RegisterPage.vue'),
      },
      {
        path: 'support',
        name: 'support',
        // 客服页对未登录访客开放（要退款的用户可能已退出登录），不设 guestOnly
        component: () => import('@/views/SupportPage.vue'),
      },
      {
        path: 'plans',
        name: 'plans',
        // 套餐权益明细页：未登录访客开放（购买决策现场，评审 P0-2 漏斗断点）
        component: () => import('@/views/PlansPage.vue'),
      },
    ],
  },
  {
    path: '/auth',
    component: () => import('@/layouts/AuthLayout.vue'),
    children: [
      { path: '', name: 'auth', component: () => import('@/views/AuthPage.vue') },
    ],
  },
  {
    // 购买流程页——无控制台外壳，独立布局；未登录先登录后回跳
    path: '/pay',
    name: 'pay-cashier',
    meta: { requiresAuth: true },
    component: () => import('@/views/pay/CashierPage.vue'),
  },
  {
    path: '/dashboard',
    component: () => import('@/layouts/DashboardLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/dashboard/DashboardHome.vue'),
      },
      {
        // 域对象是 License（s-pay-license-naming）：真身页占用 license 路径，
        // 老激活码书签（8.3 拆除）语义连续直接落到本页；membership 旧路径接住上线前书签
        path: 'license',
        name: 'license',
        component: () => import('@/views/dashboard/LicensePage.vue'),
      },
      {
        path: 'membership',
        redirect: { name: 'license' },
      },
      {
        path: 'orders',
        name: 'orders',
        component: () => import('@/views/pay/OrdersPage.vue'),
      },
      {
        path: 'orders/:orderNo',
        name: 'order-detail',
        component: () => import('@/views/pay/OrderDetailPage.vue'),
      },
      {
        path: 'orders/:orderNo/refund',
        name: 'order-refund',
        component: () => import('@/views/pay/RefundPage.vue'),
      },
      {
        path: 'devices',
        name: 'devices',
        component: () => import('@/views/dashboard/DevicesPage.vue'),
      },
      {
        path: 'account',
        name: 'account',
        component: () => import('@/views/dashboard/AccountPage.vue'),
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundPage.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  // 锚点导航（mkt-nav 的 /#features 等 router-link）依赖此行为滚动；
  // 同页点锚点（/ → /#pricing）与跨页（/login → /#features）都要滚
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})

// ── 双向导航守卫 ──
router.beforeEach((to, from, next) => {
  const session = useSessionStore()

  // 正向守卫：未登录 → 跳登录
  if (to.meta.requiresAuth && !session.isLoggedIn) {
    next({ name: 'login', query: { redirect: to.fullPath } })
    return
  }

  // 反向守卫：已登录访客页 → 静默跳控制台
  if (to.meta.guestOnly && session.isLoggedIn) {
    next({ name: 'dashboard' })
    return
  }

  next()
})

export default router
