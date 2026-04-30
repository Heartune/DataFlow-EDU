import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api, TOKEN_KEY } from '@/api/client';

export interface AuthUser {
  id: string;
  email: string;
  role: 'admin' | 'user';
  onboardingDone: boolean;
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
  const user = ref<AuthUser | null>(null);
  const initialized = ref(false);

  const isAuthed = computed(() => !!token.value);
  const isAdmin = computed(() => user.value?.role === 'admin');

  function setSession(t: string, raw: Record<string, unknown>) {
    token.value = t;
    user.value = {
      id: raw.id as string,
      email: raw.email as string,
      role: raw.role as 'admin' | 'user',
      onboardingDone: !!(raw.onboarding_done ?? raw.onboardingDone),
    };
    localStorage.setItem(TOKEN_KEY, t);
  }

  async function login(email: string, password: string) {
    const { data } = await api.post('/auth/login', { email, password });
    setSession(data.token, data.user);
    return user.value as AuthUser;
  }

  async function register(email: string, password: string, invite_code?: string) {
    const payload: Record<string, string> = { email, password };
    if (invite_code) payload.invite_code = invite_code;
    const { data } = await api.post('/auth/register', payload);
    if (data.status === 'pending_approval') {
      return { status: 'pending_approval' as const };
    }
    setSession(data.token, data.user);
    return user.value as AuthUser;
  }

  async function fetchMe() {
    if (!token.value) {
      user.value = null;
      initialized.value = true;
      return null;
    }
    try {
      const { data } = await api.get('/auth/me');
      user.value = {
        id: data.user.id,
        email: data.user.email,
        role: data.user.role,
        onboardingDone: !!(data.user.onboarding_done ?? data.user.onboardingDone),
      };
    } catch {
      logout();
    } finally {
      initialized.value = true;
    }
    return user.value;
  }

  async function markOnboardingDone() {
    if (!user.value) return;
    try {
      await api.post('/auth/me/onboarding-done');
    } catch {
      // 不阻塞流程
    }
    user.value = { ...user.value, onboardingDone: true };
  }

  function logout() {
    token.value = null;
    user.value = null;
    localStorage.removeItem(TOKEN_KEY);
  }

  return { token, user, initialized, isAuthed, isAdmin, login, register, fetchMe, markOnboardingDone, logout };
});
