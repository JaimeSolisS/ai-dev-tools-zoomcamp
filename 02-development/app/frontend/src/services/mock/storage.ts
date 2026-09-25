/** Minimal subset of the Web Storage API used by the mock backend. */
export type KeyValueStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function createMemoryStorage(): KeyValueStorage & { clear(): void; keys(): string[] } {
  const data = new Map<string, string>();
  return {
    getItem: (k) => (data.has(k) ? data.get(k)! : null),
    setItem: (k, v) => void data.set(k, String(v)),
    removeItem: (k) => void data.delete(k),
    clear: () => data.clear(),
    keys: () => [...data.keys()],
  };
}

export function readJson<T>(storage: KeyValueStorage, key: string, fallback: T): T {
  const raw = storage.getItem(key);
  if (raw == null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJson(storage: KeyValueStorage, key: string, value: unknown): void {
  storage.setItem(key, JSON.stringify(value));
}
