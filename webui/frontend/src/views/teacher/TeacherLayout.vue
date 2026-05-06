<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import OnboardingModal from '@/components/OnboardingModal.vue';

const auth = useAuthStore();
const router = useRouter();

const userInitial = computed(() =>
  (auth.user?.email || '?').slice(0, 1).toUpperCase()
);

const showHelp = ref(false);

function logout() {
  auth.logout();
  router.replace('/login');
}
</script>

<template>
  <div class="min-h-screen flex flex-col min-w-0">
    <header class="bg-white border-b border-slate-200">
      <div class="max-w-[90rem] mx-auto px-4 sm:px-6 min-h-14 py-2 flex items-center justify-between gap-3">
        <div class="flex items-center gap-2 sm:gap-3 min-w-0">
          <router-link to="/teacher/tasks" class="font-bold text-slate-900 text-lg shrink-0">
            DataFlow-EDU
          </router-link>
          <span class="hidden sm:inline text-slate-400">|</span>
          <span class="hidden md:inline text-slate-600 text-sm truncate">AI赋能·解放教师生产力</span>
          <span class="hidden sm:inline text-slate-400">|</span>
          <span class="text-slate-600 text-sm shrink-0">教师端</span>
        </div>
        <div class="flex items-center justify-end gap-2 sm:gap-3 text-sm min-w-0">
          <router-link
            v-if="auth.isAdmin"
            to="/admin"
            class="hidden sm:inline text-slate-600 hover:text-slate-900 shrink-0"
          >
            管理员看板
          </router-link>
          <!-- 使用指南入口 -->
          <button
            class="w-7 h-7 rounded-full border border-slate-300 text-slate-500 hover:border-slate-500 hover:text-slate-800 transition-colors grid place-items-center text-xs font-bold"
            title="使用指南"
            @click="showHelp = true"
          >
            ?
          </button>
          <div class="flex items-center gap-2 text-slate-600 min-w-0">
            <div class="w-7 h-7 rounded-full bg-slate-900 text-white grid place-items-center text-xs">
              {{ userInitial }}
            </div>
            <span class="hidden sm:inline truncate max-w-[14rem]">欢迎，{{ auth.user?.email }}</span>
          </div>
          <button
            class="text-slate-500 hover:text-rose-600 shrink-0"
            @click="logout"
          >
            退出
          </button>
        </div>
      </div>
    </header>
    <main class="flex-1 max-w-[90rem] mx-auto w-full min-w-0 px-4 sm:px-6 py-4 sm:py-6">
      <router-view />
    </main>
  </div>

  <OnboardingModal
    v-if="auth.user && (!auth.user.onboardingDone || showHelp)"
    @close="showHelp = false"
  />
</template>
