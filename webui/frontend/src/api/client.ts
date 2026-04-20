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
    if (error?.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      const next = window.location.pathname;
      if (!/^\/(login|register)/.test(next)) {
        window.location.assign(`/login?next=${encodeURIComponent(next)}`);
      }
    }
    return Promise.reject(error);
  }
);
