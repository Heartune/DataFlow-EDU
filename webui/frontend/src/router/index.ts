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
        component: () => import('@/views/teacher/NewTaskView.vue'),
      },
      {
        path: 'tasks/:id',
        name: 'teacher-task-detail',
        component: () => import('@/views/teacher/TaskDetailView.vue'),
        props: true,
      },
    ],
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/admin/AdminLayout.vue'),
    meta: { adminOnly: true },
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
