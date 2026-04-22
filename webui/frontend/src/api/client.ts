import axios, { type InternalAxiosRequestConfig } from 'axios';

export const TOKEN_KEY = 'edu_jwt';
export const LLM_KEY_KEY = 'edu_llm_key';

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }
  const llmKey = localStorage.getItem(LLM_KEY_KEY);
  if (llmKey) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>)['X-LLM-Key'] = llmKey;
  }
  return config;
});

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      const next = window.location.pathname;
      if (!/^\/(login|register)/.test(next)) {
        window.location.assign(`/login?next=${encodeURIComponent(next)}`);
      }
    } else if (status === 403) {
      // admin-only 接口被普通用户命中：交给上层 catch 显示，避免静默失败
      const url = String(error?.config?.url || '');
      if (/^\/admin\//.test(url)) {
        // 全局轻提示一次，组件层仍可继续处理
        try {
          // 动态引入 toast store，避免 client 模块循环依赖
          import('@/stores/toast').then(({ useToastStore }) => {
            useToastStore().show('该接口仅管理员可访问', 'warning');
          });
        } catch {
          /* ignore */
        }
      }
    }
    return Promise.reject(error);
  }
);
