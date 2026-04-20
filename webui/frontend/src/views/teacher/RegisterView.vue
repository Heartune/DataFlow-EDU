<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();

const email = ref('');
const password = ref('');
const password2 = ref('');
const loading = ref(false);
const error = ref('');

async function submit() {
  if (!email.value || !password.value) {
    error.value = '请输入邮箱和密码';
    return;
  }
  if (password.value.length < 6) {
    error.value = '密码至少 6 位';
    return;
  }
  if (password.value !== password2.value) {
    error.value = '两次密码不一致';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    await auth.register(email.value.trim(), password.value);
    router.replace('/teacher/tasks');
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (code === 'email_taken') error.value = '该邮箱已被注册';
    else if (code === 'invalid_email') error.value = '邮箱格式不正确';
    else error.value = err?.message || '注册失败';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen grid place-items-center bg-slate-50">
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm w-full max-w-md p-8">
      <h1 class="text-xl font-bold text-slate-900 mb-1">注册教师账号</h1>
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
          <label class="block text-sm text-slate-600 mb-1">密码（≥ 6 位）</label>
          <input
            v-model="password"
            type="password"
            autocomplete="new-password"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
          />
        </div>
        <div>
          <label class="block text-sm text-slate-600 mb-1">再次输入密码</label>
          <input
            v-model="password2"
            type="password"
            autocomplete="new-password"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
          />
        </div>
        <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
        >
          {{ loading ? '注册中...' : '创建账号' }}
        </button>
      </form>
      <p class="mt-4 text-sm text-slate-500 text-center">
        已有账号？
        <router-link to="/login" class="text-slate-900 underline">直接登录</router-link>
      </p>
    </div>
  </div>
</template>
