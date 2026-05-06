type UnauthorizedListener = (message: string) => void;

const unauthorizedListeners = new Set<UnauthorizedListener>();

export function subscribeToUnauthorized(listener: UnauthorizedListener) {
  unauthorizedListeners.add(listener);

  return () => {
    unauthorizedListeners.delete(listener);
  };
}

export function emitUnauthorized(message: string) {
  unauthorizedListeners.forEach((listener) => {
    listener(message);
  });
}
