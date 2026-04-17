import type { UIMessage } from "ai";
import { create } from "zustand";

/**
 * Per-session coordination state for the streaming pipeline.
 *
 * Keyed by sessionId so that async callbacks bound to an old session
 * (onFinish, onError, reconnect timers) read the right session's state
 * instead of whatever session is currently active. Before this, a stale
 * callback firing after a session switch could mutate the new session's
 * flags — hence the wholesale `.clear()` / `=false` resets on every switch.
 */
export interface SessionCoord {
  /** True once resumeStream has been called for this session. */
  hasResumed: boolean;
  /** True once REST hydration has run for this session. */
  hydrateCompleted: boolean;
  /** Queued resume fn, set when resume fires before hydration completes. */
  pendingResume: (() => void) | null;
  /**
   * Snapshot of the trailing assistant message stripped before resume.
   * Restored if the replay never produces chunks (e.g. 204 Not Found
   * because the stream completed between REST fetch and resume GET).
   * Cleared once the replay has started producing chunks.
   */
  stripSnapshot: UIMessage | null;
  /** Number of consecutive reconnect attempts for this session. */
  reconnectAttempts: number;
  /** True while a reconnect timer is armed. */
  reconnectScheduled: boolean;
  /** Wall-clock time when the current reconnect cycle started. */
  reconnectStartedAt: number | null;
  /** True once the "Connection lost" toast has been shown this cycle. */
  hasShownDisconnectToast: boolean;
  /** Text of the last user message sent; blocks duplicate POST on resume. */
  lastSubmittedMessageText: string | null;
}

const defaultCoord: SessionCoord = {
  hasResumed: false,
  hydrateCompleted: false,
  pendingResume: null,
  stripSnapshot: null,
  reconnectAttempts: 0,
  reconnectScheduled: false,
  reconnectStartedAt: null,
  hasShownDisconnectToast: false,
  lastSubmittedMessageText: null,
};

interface CopilotStreamStore {
  sessions: Record<string, SessionCoord>;
  /** The session the user is currently viewing — used by stale callbacks
   *  to verify they still belong to the active session. */
  activeSessionId: string | null;

  getCoord: (sessionId: string) => SessionCoord;
  updateCoord: (sessionId: string, patch: Partial<SessionCoord>) => void;
  clearCoord: (sessionId: string) => void;
  setActiveSession: (sessionId: string | null) => void;
  /** Test-only: wipe all per-session state and the active session pointer. */
  resetAll: () => void;
}

export const useCopilotStreamStore = create<CopilotStreamStore>((set, get) => ({
  sessions: {},
  activeSessionId: null,

  getCoord(sessionId) {
    return get().sessions[sessionId] ?? defaultCoord;
  },
  updateCoord(sessionId, patch) {
    set((state) => ({
      sessions: {
        ...state.sessions,
        [sessionId]: {
          ...(state.sessions[sessionId] ?? defaultCoord),
          ...patch,
        },
      },
    }));
  },
  clearCoord(sessionId) {
    set((state) => {
      if (!(sessionId in state.sessions)) return state;
      const next = { ...state.sessions };
      delete next[sessionId];
      return { sessions: next };
    });
  },
  setActiveSession(sessionId) {
    set({ activeSessionId: sessionId });
  },
  resetAll() {
    set({ sessions: {}, activeSessionId: null });
  },
}));

export const DEFAULT_SESSION_COORD = defaultCoord;
