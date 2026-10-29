import { useLayoutEffect, useRef } from 'react';

// A mounted generation owns one mutation. StrictMode cleanup and navigation invalidate it.
export function useRequestLifetime() {
  const lifetime = useRef({ alive: false, version: 0, busy: false });
  useLayoutEffect(() => {
    lifetime.current.alive = true; lifetime.current.version++; lifetime.current.busy = false;
    return () => { lifetime.current.alive = false; lifetime.current.version++; lifetime.current.busy = false; };
  }, []);
  return {
    begin() {
      const state = lifetime.current;
      if (!state.alive || state.busy) return null;
      state.busy = true;
      const version = state.version;
      const current = () => lifetime.current.alive && lifetime.current.version === version;
      return { current, finish: () => { if (current()) lifetime.current.busy = false; } };
    },
  };
}
