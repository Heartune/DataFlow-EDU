import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/teacher/tasks' },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/teacher/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/teacher/RegisterView.vue'),
    meta: { public: true },
  },
  {
    path: '/teacher',
    component: () => import('@/views/teacher/TeacherLayout.vue'),
    redirect: '/teacher/tasks',
    children: [
      {
        path: 'tasks',
        name: 'teacher-tasks',
        component: () => import('@/views/teacher/TaskListView.vue'),
      },
      {
        path: 'tasks/new',
        name: 'teacher-tasks-new',
        component: () => import('@/views/teacher/UploadView.vue'),
      },
      {
        path: 'tasks/:id',
        component: () => import('@/views/teacher/TaskShellView.vue'),
        props: true,
        children: [
          {
            path: '',
            name: 'teacher-task-progress',
            component: () => import('@/views/teacher/ProgressView.vue'),
            props: true,
          },
          {
            path: 'stats',
            name: 'teacher-task-stats',
            component: () => import('@/views/teacher/StatsView.vue'),
            props: true,
          },
          {
            path: 'wizard',
            name: 'teacher-task-wizard',
            component: () => import('@/views/teacher/ConfigView.vue'),
            props: true,
          },
          {
            path: 'edit',
            name: 'teacher-task-edit',
            component: () => import('@/views/teacher/EditView.vue'),
            props: true,
          },
          {
            path: 'export',
            name: 'teacher-task-export',
            component: () => import('@/views/teacher/ExportView.vue'),
            props: true,
          },
        ],
      },
    ],
  },
  {
    path: '/admin',
    meta: { adminOnly: true },
    children: [
      { path: '', name: 'admin', component: () => import('@/views/admin/AdminLayout.vue') },
      { path: 'users', name: 'admin-users', component: () => import('@/views/admin/UserManagementView.vue') },
    ],
  },
  {
    path: '/share/:token',
    name: 'share',
    component: () => import('@/views/teacher/ShareView.vue'),
    props: true,
    meta: { public: true },
  },
  { path: '/:pathMatch(.*)*', redirect: '/teacher/tasks' },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.initialized) {
    await auth.fetchMe();
  }
  if (to.meta.public) return true;
  if (!auth.isAuthed) {
    return { path: '/login', query: { next: to.fullPath } };
  }
  if (to.meta.adminOnly && !auth.isAdmin) {
    return { path: '/teacher/tasks' };
  }
  return true;
});
