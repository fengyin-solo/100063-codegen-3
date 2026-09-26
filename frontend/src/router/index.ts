import { createRouter, createWebHistory } from 'vue-router'

import Dashboard from '@/views/Dashboard.vue'
const Sample = () => import('@/views/sample/index.vue')
const Client = () => import('@/views/client/index.vue')
const Project = () => import('@/views/project/index.vue')
const Task = () => import('@/views/task/index.vue')
const Execute = () => import('@/views/execute/index.vue')
const Result = () => import('@/views/result/index.vue')
const Review = () => import('@/views/review/index.vue')
const Instrument = () => import('@/views/instrument/index.vue')
const Calibration = () => import('@/views/calibration/index.vue')
const Reagent = () => import('@/views/reagent/index.vue')
const Consume = () => import('@/views/consume/index.vue')
const Environment = () => import('@/views/environment/index.vue')
const Report = () => import('@/views/report/index.vue')
const Issue = () => import('@/views/issue/index.vue')
const Qc = () => import('@/views/qc/index.vue')
const Complaint = () => import('@/views/complaint/index.vue')
const Stockin = () => import('@/views/stockin/index.vue')
const Settlement = () => import('@/views/settlement/index.vue')
const Inspection = () => import('@/views/inspection/index.vue')
const Hazard = () => import('@/views/hazard/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/sample', name: 'sample', component: Sample },
    { path: '/client', name: 'client', component: Client },
    { path: '/project', name: 'project', component: Project },
    { path: '/task', name: 'task', component: Task },
    { path: '/execute', name: 'execute', component: Execute },
    { path: '/result', name: 'result', component: Result },
    { path: '/review', name: 'review', component: Review },
    { path: '/instrument', name: 'instrument', component: Instrument },
    { path: '/calibration', name: 'calibration', component: Calibration },
    { path: '/reagent', name: 'reagent', component: Reagent },
    { path: '/consume', name: 'consume', component: Consume },
    { path: '/environment', name: 'environment', component: Environment },
    { path: '/report', name: 'report', component: Report },
    { path: '/issue', name: 'issue', component: Issue },
    { path: '/qc', name: 'qc', component: Qc },
    { path: '/complaint', name: 'complaint', component: Complaint },
    { path: '/stockin', name: 'stockin', component: Stockin },
    { path: '/settlement', name: 'settlement', component: Settlement },
    { path: '/inspection', name: 'inspection', component: Inspection },
    { path: '/hazard', name: 'hazard', component: Hazard },
  ],
})

export default router
