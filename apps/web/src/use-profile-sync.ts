import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ProfileSync, ACCOUNT_MARKER, accountKey } from './profile-sync';
import { browserStorage, type Settings } from './storage';

export function useProfileSync(enabled: boolean, guest: Settings | null) {
  const latestGuest = useRef(guest);
  latestGuest.current = guest;
  const [controller] = useState(
    () =>
      new ProfileSync(
        enabled
          ? browserStorage()
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} },
        () => latestGuest.current,
      ),
  );
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  useEffect(() => {
    if (!enabled) return;
    const online = () => controller.setOnline(navigator.onLine);
    const foreground = () => {
      if (document.visibilityState === 'visible' && navigator.onLine) void controller.refresh();
    };
    const storage = (event: StorageEvent) => {
      const owner = controller.getSnapshot().identity?.id;
      if (
        event.key === null ||
        event.key === ACCOUNT_MARKER ||
        (owner && event.key === accountKey(owner))
      )
        controller.storageChanged();
    };
    const unload = (event: BeforeUnloadEvent) => {
      const current = controller.getSnapshot();
      if (current.pending && current.cacheIssue) event.preventDefault();
    };
    online();
    const timer = window.setInterval(foreground, 60000);
    window.addEventListener('online', online);
    window.addEventListener('offline', online);
    window.addEventListener('focus', foreground);
    window.addEventListener('storage', storage);
    window.addEventListener('beforeunload', unload);
    document.addEventListener('visibilitychange', foreground);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('online', online);
      window.removeEventListener('offline', online);
      window.removeEventListener('focus', foreground);
      window.removeEventListener('storage', storage);
      window.removeEventListener('beforeunload', unload);
      document.removeEventListener('visibilitychange', foreground);
    };
  }, [controller, enabled]);
  return {
    controller,
    state,
    settings: state.selected ? (state.pending?.profile ?? state.snapshot?.profile ?? null) : null,
  };
}
