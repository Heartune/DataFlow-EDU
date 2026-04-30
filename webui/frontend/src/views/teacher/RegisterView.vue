<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import zxcvbn from 'zxcvbn';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();

const email = ref('');
const password = ref('');
const password2 = ref('');
const inviteCode = ref('');
const loading = ref(false);
const error = ref('');
const pendingApproval = ref(false);

// zxcvbn 实时强度评分（0–4），密码为空时为 null
const strengthResult = computed(() => {
  if (!password.value) return null;
  return zxcvbn(password.value);
});

const strengthScore = computed(() => strengthResult.value?.score ?? -1);

const strengthLabel = computed(() => {
  switch (strengthScore.value) {
    case 0: return '极弱';
    case 1: return '弱';
    case 2: return '中等';
    case 3: return '强';
    case 4: return '非常强';
    default: return '';
  }
});

const strengthColor = computed(() => {
  switch (strengthScore.value) {
    case 0:
    case 1: return 'bg-rose-500';
    case 2: return 'bg-amber-400';
    case 3: return 'bg-emerald-400';
    case 4: return 'bg-emerald-600';
    default: return 'bg-slate-200';
  }
});

// 评分 < 2 时阻止提交
const passwordTooWeak = computed(() => password.value.length > 0 && strengthScore.value < 2);

// 将 zxcvbn 英文 suggestions 映射为中文（仅常见条目）
const strengthSuggestion = computed(() => {
  if (!strengthResult.value) return '';
  const w = strengthResult.value.feedback.warning;
  const s = strengthResult.value.feedback.suggestions[0];
  const raw = w || s || '';
  const map: Record<string, string> = {
    'Use a few words, avoid common phrases': '建议使用多个不相关的词组，避免常见短语',
    'No need for symbols, digits, or uppercase letters': '不必过度依赖符号，增加词汇量更有效',
    "Add another word or two. Uncommon words are better.": '再加一两个词，不常见的词更好',
    'Straight rows of keys are easy to guess': '键盘连续字母（如 qwerty）容易被猜到',
    'Short keyboard patterns are easy to guess': '键盘规律组合太短，容易被猜到',
    'Use a longer keyboard pattern with more turns': '使用更长且方向变化更多的键盘输入方式',
    'Repeats like "aaa" are easy to guess': '重复字符（如 aaa）容易被猜到',
    'Repeats like "abcabc" are only slightly harder to guess than "abc"': '重复模式仅略难于原始序列',
    'Sequences like abc or 6543 are easy to guess': '连续字母或数字（如 abc、6543）容易被猜到',
    'Recent years are easy to guess': '近年份容易被猜到',
    'Dates are often easy to guess': '日期类密码容易被猜到',
    'This is a top-10 common password': '这是最常见密码之一，请更换',
    'This is a top-100 common password': '这是常见密码，请更换',
    'This is a very common password': '这是非常常见的密码，请更换',
    'This is similar to a commonly used password': '与常见密码过于相似',
    "A word by itself is easy to guess": '单个词语容易被猜到，请加入数字或其他词',
    'Names and surnames by themselves are easy to guess': '单独的姓名容易被猜到',
    'Common names and surnames are easy to guess': '常见姓名容易被猜到',
  };
  return map[raw] || raw;
});

async function submit() {
  if (!email.value || !password.value) {
    error.value = '请输入邮箱和密码';
    return;
  }
  if (password.value.length < 8) {
    error.value = '密码至少 8 位';
    return;
  }
  if (passwordTooWeak.value) {
    error.value = '密码强度不足，请参考下方提示';
    return;
  }
  if (password.value !== password2.value) {
    error.value = '两次密码不一致';
    return;
  }
  loading.value = true;
  error.value = '';
    pendingApproval.value = false;
    try {
      const result = await auth.register(email.value.trim(), password.value, inviteCode.value.trim());
      if ('status' in result && result.status === 'pending_approval') {
        pendingApproval.value = true;
      } else {
        router.replace('/teacher/tasks');
    }
  } catch (err: any) {
    const code = err?.response?.data?.error;
    if (code === 'email_taken') error.value = '该邮箱已被注册';
    else if (code === 'invalid_email') error.value = '邮箱格式不正确';
    else if (code === 'password_too_short') error.value = '密码至少 8 位';
    else if (code === 'password_too_weak') {
      const suggestion = err?.response?.data?.warning || err?.response?.data?.suggestions?.[0] || '';
      error.value = `密码强度不足${suggestion ? '：' + suggestion : ''}`;
    } else if (code === 'invalid_invite_code') error.value = '邀请码无效';
    else if (code === 'invite_code_used') error.value = '邀请码已被使用';
    else if (code === 'invite_code_expired') error.value = '邀请码已过期';
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

      <!-- 待审批提示 -->
      <div v-if="pendingApproval" class="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
        <p class="font-medium mb-1">注册成功，等待审批</p>
        <p>
          您的账号已创建，管理员审批通过后即可登录。<br />
          在注册前联系管理员获取邀请码可跳过此步骤。
        </p>
        <router-link to="/login" class="mt-3 inline-block text-amber-700 underline text-xs">前往登录页</router-link>
      </div>

      <form v-else @submit.prevent="submit" class="space-y-4">
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
          <label class="block text-sm text-slate-600 mb-1">密码（≥ 8 位）</label>
          <input
            v-model="password"
            type="password"
            autocomplete="new-password"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
          />
          <!-- 强度条 -->
          <div v-if="password" class="mt-2 space-y-1">
            <div class="flex gap-1">
              <div
                v-for="i in 4"
                :key="i"
                class="h-1.5 flex-1 rounded-full transition-colors duration-200"
                :class="i - 1 < strengthScore ? strengthColor : 'bg-slate-200'"
              ></div>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-xs text-slate-500">强度：{{ strengthLabel }}</span>
              <span v-if="passwordTooWeak && strengthSuggestion" class="text-xs text-amber-600 text-right max-w-[70%]">
                {{ strengthSuggestion }}
              </span>
            </div>
          </div>
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
        <div>
          <label class="block text-sm text-slate-600 mb-1">邀请码（可选，有码立即激活）</label>
          <input
            v-model="inviteCode"
            type="text"
            autocomplete="off"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900"
          />
        </div>
        <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
        <button
          type="submit"
          :disabled="loading || passwordTooWeak"
          class="w-full py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
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
