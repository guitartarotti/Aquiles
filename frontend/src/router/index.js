import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import { hasAuthSession } from '../auth/session'

const LoginView = () => import('../views/LoginView.vue')
const Process = () => import('../views/MainView.vue')
const SimulationView = () => import('../views/SimulationView.vue')
const SimulationRunView = () => import('../views/SimulationRunView.vue')
const ReportView = () => import('../views/ReportView.vue')
const InteractionView = () => import('../views/InteractionView.vue')
const OptionsDashboardView = () => import('../views/OptionsDashboardView.vue')
const MacroHeatmapView = () => import('../features/macro-heatmap/components/MacroHeatmapView.vue')
const ChartView = () => import('../views/ChartView.vue')
const DiscoveryView = () => import('../views/DiscoveryView.vue')

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: { public: true }
  },
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: ReportView,
    props: true
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: InteractionView,
    props: true
  },
  {
    path: '/options',
    name: 'OptionsDashboard',
    component: OptionsDashboardView
  },
  {
    path: '/heatmap',
    name: 'MacroHeatmap',
    component: MacroHeatmapView
  },
  {
    path: '/chart',
    name: 'Chart',
    component: ChartView
  },
  {
    path: '/discovery',
    name: 'Discovery',
    component: DiscoveryView
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(to => {
  if (to.meta.public) {
    return to.name === 'Login' && hasAuthSession() ? { path: '/' } : true
  }
  if (!hasAuthSession()) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
