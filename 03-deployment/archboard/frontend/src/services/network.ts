/** Online/offline detection shared by the backend implementations. */

/** Source of online/offline events (the browser's by default). */
export interface NetworkMonitor {
  isOnline(): boolean;
  subscribe(listener: (online: boolean) => void): () => void;
}

export function browserNetworkMonitor(): NetworkMonitor {
  return {
    isOnline: () => (typeof navigator === 'undefined' ? true : navigator.onLine !== false),
    subscribe(listener) {
      if (typeof window === 'undefined') return () => {};
      const on = () => listener(true);
      const off = () => listener(false);
      window.addEventListener('online', on);
      window.addEventListener('offline', off);
      return () => {
        window.removeEventListener('online', on);
        window.removeEventListener('offline', off);
      };
    },
  };
}

export function controllableNetwork(initial = true): NetworkMonitor & { set(online: boolean): void } {
  let online = initial;
  const listeners = new Set<(o: boolean) => void>();
  return {
    isOnline: () => online,
    subscribe(l) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    set(next) {
      online = next;
      listeners.forEach((l) => l(next));
    },
  };
}
