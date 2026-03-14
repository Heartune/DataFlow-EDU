import type { LoadedData } from '@/types/pipeline';

export async function loadData(book: string): Promise<LoadedData> {
  const res = await fetch(`/api/data/${encodeURIComponent(book)}`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || res.statusText || '加载失败');
  }
  return res.json();
}
