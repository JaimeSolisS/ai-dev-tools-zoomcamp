/**
 * Transport for the mock real-time server. Messages published on a bus reach
 * every subscriber — in this tab and, with the BroadcastChannel bus, in every
 * other tab of the same origin. This lets several browser tabs act as
 * different participants of one interview without any backend.
 */
export interface BusMessage {
  sessionId: string;
  /** Connection that produced the message; it is not echoed back to it. */
  origin: string | null;
  payload: unknown;
}

export interface MessageBus {
  publish(message: BusMessage): void;
  subscribe(listener: (message: BusMessage) => void): () => void;
}

export function createInProcessBus(): MessageBus {
  const listeners = new Set<(m: BusMessage) => void>();
  return {
    publish(message) {
      // Clone to mimic serialization across a network boundary.
      const copy = structuredClone(message);
      queueMicrotask(() => listeners.forEach((l) => l(copy)));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export function createBroadcastBus(channelName = 'archboard-mock-bus'): MessageBus {
  if (typeof BroadcastChannel === 'undefined') return createInProcessBus();
  const local = createInProcessBus();
  const channel = new BroadcastChannel(channelName);
  const listeners = new Set<(m: BusMessage) => void>();
  channel.onmessage = (event: MessageEvent<BusMessage>) => listeners.forEach((l) => l(event.data));
  return {
    publish(message) {
      local.publish(message);
      channel.postMessage(message);
    },
    subscribe(listener) {
      listeners.add(listener);
      const off = local.subscribe(listener);
      return () => {
        listeners.delete(listener);
        off();
      };
    },
  };
}
