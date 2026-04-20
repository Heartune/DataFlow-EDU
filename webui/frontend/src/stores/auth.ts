import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api, TOKEN_KEY } from '@/api/client';

export interface AuthUser {
  id: string;
  email: string;
  role: 'admin' | 'user';
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
  const user = ref<AuthUser | null>(null);
  const initialized = ref(false);

  const isAuthed = computed(() => !!token.value);
  const isAdmin = computed(() => user.value?.role === 'admin');

  function setSession(t: string, u: AuthUser) {
    token.value = t;
    user.value = u;
    localStorage.setItem(TOKEN_KEY, t);
  }

  async function login(email: string, password: string) {
    const { data } = await api.post('/auth/login', { email, password });
    setSession(data.token, data.user);
    return data.user as AuthUser;
  }

  async function register(email: string, password: string) {
    const { data } = await api.post('/auth/register', { email, password });
    setSession(data.token, data.user);
    return data.user as AuthUser;
  }

  async function fetchMe() {
    if (!token.value) {
      user.value = null;
      initialized.value = true;
      return null;
    }
    try {
      const { data } = await api.get('/auth/me');
      user.value = data.user;
    } catch {
      logout();
    } finally {
      initialized.value = true;
    }
    return user.value;
  }

  function logout() {
    token.value = null;
    user.value = null;
    localStorage.removeItem(TOKEN_KEY);
  }

  return { token, user, initialized, isAuthed, isAdmin, login, register, fetchMe, logout };
});
