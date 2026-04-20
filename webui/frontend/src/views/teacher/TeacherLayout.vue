<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();

const userInitial = computed(() =>
  (auth.user?.email || '?').slice(0, 1).toUpperCase()
);

function logout() {
  auth.logout();
  router.replace('/login');
}
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header class="bg-white border-b border-slate-200">
      <div class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <router-link to="/teacher/tasks" class="font-bold text-slate-900 text-lg">
            DataFlow-EDU
          </router-link>
          <span class="text-slate-400">|</span>
          <span class="text-slate-600 text-sm">教师端</span>
        </div>
        <div class="flex items-center gap-3 text-sm">
          <router-link
            v-if="auth.isAdmin"
            to="/admin"
            class="text-slate-600 hover:text-slate-900"
          >
            管理员看板
          </router-link>
          <div class="flex items-center gap-2 text-slate-600">
            <div class="w-7 h-7 rounded-full bg-slate-900 text-white grid place-items-center text-xs">
              {{ userInitial }}
            </div>
            <span>{{ auth.user?.email }}</span>
          </div>
          <button
            class="text-slate-500 hover:text-rose-600"
            @click="logout"
          >
            退出
          </button>
        </div>
      </div>
    </header>
    <main class="flex-1 max-w-6xl mx-auto w-full px-6 py-6">
      <router-view />
    </main>
  </div>
</template>
