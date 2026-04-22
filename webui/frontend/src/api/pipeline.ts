import { api } from '@/api/client';
import type { LoadedData } from '@/types/pipeline';

export async function loadData(book: string): Promise<LoadedData> {
  try {
    const { data } = await api.get(`/admin/data/${encodeURIComponent(book)}`);
    return data;
  } catch (err: any) {
    const msg = err?.response?.data?.error || err?.message || '加载失败';
    throw new Error(msg);
  }
}
