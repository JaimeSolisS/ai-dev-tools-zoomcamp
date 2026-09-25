import { createInProcessBus } from '../services/mock/bus';
import { controllableNetwork, createMockBackend, type MockBackend } from '../services/mock/mockBackend';
import { createMemoryStorage, type KeyValueStorage } from '../services/mock/storage';
import type { User } from '../services/types';

/**
 * A simulated deployment: one mock "server" (shared storage + bus) and any
 * number of clients (browsers/tabs) talking to it.
 */
export function createWorld(opts: { now?: () => Date } = {}) {
  const serverStorage = createMemoryStorage();
  const bus = createInProcessBus();

  function client(browser: { storage?: KeyValueStorage } = {}) {
    const network = controllableNetwork(true);
    const browserStorage = browser.storage ?? createMemoryStorage();
    const backend = createMockBackend({
      serverStorage,
      browserStorage,
      tabStorage: createMemoryStorage(),
      bus,
      network,
      latencyMs: 0,
      now: opts.now,
      seedExamples: false,
    });
    return Object.assign(backend, { network, browserStorage });
  }

  return { serverStorage, bus, client };
}

export async function signIn(backend: MockBackend, email = 'ada@example.com'): Promise<User> {
  const { devToken } = await backend.auth.requestMagicLink(email);
  return backend.auth.verifyMagicLink(devToken!);
}
