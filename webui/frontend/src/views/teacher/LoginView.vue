<script setup lang="ts">
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const email = ref('');
const password = ref('');
const loading = ref(false);
const error = ref('');

async function submit() {
  if (!email.value || !password.value) {
    error.value = '请输入邮箱和密码';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    await auth.login(email.value.trim(), password.value);
    const next = (route.query.next as string) || '/teacher/tasks';
    router.replace(next);
  } catch (err: any) {
    const msg = err?.response?.data?.error;
    if (msg === 'invalid_credentials') error.value = '邮箱或密码错误';
    else if (msg === 'pending_approval') error.value = '账号正在等待管理员审批，请稍后再试';
    else error.value = err?.message || '登录失败';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen grid place-items-center bg-slate-50">
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm w-full max-w-md p-8">
      <h1 class="text-xl font-bold text-slate-900 mb-1">教师端登录</h1>
      <p class="text-sm text-slate-500 mb-6">DataFlow-EDU · 一份教材，自动生成结构化题库</p>
      <form @submit.prevent="submit" class="space-y-4">
        <div>
          <label class="block text-sm text-slate-600 mb-1">邮箱</label>
          <input
            v-model="email"
            type="email"
            autocomplete="email"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
            placeholder="teacher@school.edu.cn"
          />
        </div>
        <div>
          <label class="block text-sm text-slate-600 mb-1">密码</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
            placeholder="••••••"
          />
        </div>
        <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
        >
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
      <p class="mt-4 text-sm text-slate-500 text-center">
        还没有账号？
        <router-link to="/register" class="text-slate-900 underline">立即注册</router-link>
      </p>
    </div>
  </div>
</template>
