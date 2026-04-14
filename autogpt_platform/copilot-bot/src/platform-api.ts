/**
 * Client for the AutoGPT Platform Linking & Chat APIs.
 *
 * Two independent linking flows:
 *   - SERVER: /resolve, /tokens, /tokens/{t}/status — claimed server context
 *   - USER:   /resolve-user, /user-tokens — 1:1 DM context
 *
 * Chat endpoints (/chat/session, /chat/stream) accept either context — pass
 * a serverId for server messages, omit for DMs.
 */

const DEFAULT_TIMEOUT_MS = 30_000;
// Idle timeout: abort only if no data arrives for this long. Backend sends
// `: keepalive\n\n` every 30s, so 90s gives 3 missed keepalives of headroom.
// CoPilot turns can legitimately take many minutes — a hard deadline would kill
// long-running tool calls mid-flight.
const SSE_IDLE_TIMEOUT_MS = 90_000;

export class PlatformAPIError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "PlatformAPIError";
  }
}

export interface ResolveResult {
  linked: boolean;
}

export interface LinkTokenResult {
  token: string;
  expires_at: string;
  link_url: string;
}

export interface LinkTokenStatus {
  status: "pending" | "linked" | "expired";
}

export class PlatformAPI {
  private readonly botApiKey: string;

  constructor(private readonly baseUrl: string) {
    const key = process.env.PLATFORM_BOT_API_KEY;
    if (!key) {
      throw new Error(
        "PLATFORM_BOT_API_KEY is required. Set it in your .env file.",
      );
    }
    this.botApiKey = key;
  }

  /** Check if a server has a PlatformLink (anyone in it can chat). */
  async resolveServer(
    platform: string,
    platformServerId: string,
  ): Promise<ResolveResult> {
    return this.postJson("/api/platform-linking/resolve", {
      platform: platform.toUpperCase(),
      platform_server_id: platformServerId,
    });
  }

  /** Check if an individual has a PlatformUserLink (their DMs are linked). */
  async resolveUser(
    platform: string,
    platformUserId: string,
  ): Promise<ResolveResult> {
    return this.postJson("/api/platform-linking/resolve-user", {
      platform: platform.toUpperCase(),
      platform_user_id: platformUserId,
    });
  }

  /**
   * Create a SERVER link token. platformUserId is the user claiming ownership.
   */
  async createLinkToken(params: {
    platform: string;
    platformServerId: string;
    platformUserId: string;
    platformUsername?: string;
    serverName?: string;
    channelId?: string;
  }): Promise<LinkTokenResult> {
    return this.postJson("/api/platform-linking/tokens", {
      platform: params.platform.toUpperCase(),
      platform_server_id: params.platformServerId,
      platform_user_id: params.platformUserId,
      platform_username: params.platformUsername,
      server_name: params.serverName,
      channel_id: params.channelId,
    });
  }

  /** Create a USER (DM) link token for an individual. */
  async createUserLinkToken(params: {
    platform: string;
    platformUserId: string;
    platformUsername?: string;
  }): Promise<LinkTokenResult> {
    return this.postJson("/api/platform-linking/user-tokens", {
      platform: params.platform.toUpperCase(),
      platform_user_id: params.platformUserId,
      platform_username: params.platformUsername,
    });
  }

  /** Check if a link token has been consumed. Works for both SERVER and USER tokens. */
  async getLinkTokenStatus(token: string): Promise<LinkTokenStatus> {
    const res = await fetch(
      `${this.baseUrl}/api/platform-linking/tokens/${encodeURIComponent(token)}/status`,
      {
        headers: this.headers(),
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      },
    );
    if (!res.ok) throw new PlatformAPIError(res.status, await res.text());
    return res.json();
  }

  /**
   * Create a new CoPilot session. Pass `platformServerId` for server context
   * (session owned by server owner); omit for DM context (owned by the user).
   */
  async createChatSession(params: {
    platform: string;
    platformUserId: string;
    platformServerId?: string;
  }): Promise<string> {
    const data = await this.postJson<{ session_id: string }>(
      "/api/platform-linking/chat/session",
      {
        platform: params.platform.toUpperCase(),
        platform_server_id: params.platformServerId,
        platform_user_id: params.platformUserId,
        message: "session_init",
      },
    );
    return data.session_id;
  }

  /**
   * Stream a chat message. Same context rules as createChatSession —
   * include platformServerId for server messages, omit for DMs.
   */
  async *streamChat(params: {
    platform: string;
    platformUserId: string;
    platformServerId?: string;
    message: string;
    sessionId?: string;
  }): AsyncGenerator<string> {
    const abort = new AbortController();
    let idleTimer: ReturnType<typeof setTimeout> | null = null;
    const resetIdleTimer = () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => abort.abort(), SSE_IDLE_TIMEOUT_MS);
    };
    resetIdleTimer();

    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}/api/platform-linking/chat/stream`, {
        method: "POST",
        headers: { ...this.headers(), Accept: "text/event-stream" },
        body: JSON.stringify({
          platform: params.platform.toUpperCase(),
          platform_server_id: params.platformServerId,
          platform_user_id: params.platformUserId,
          message: params.message,
          session_id: params.sessionId,
        }),
        signal: abort.signal,
      });
    } catch (err) {
      if (idleTimer) clearTimeout(idleTimer);
      throw err;
    }

    if (!res.ok) {
      if (idleTimer) clearTimeout(idleTimer);
      throw new PlatformAPIError(res.status, await res.text());
    }
    if (!res.body) {
      if (idleTimer) clearTimeout(idleTimer);
      throw new PlatformAPIError(0, "No response body for SSE stream");
    }

    const decoder = new TextDecoder();
    const reader = res.body.getReader();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        resetIdleTimer();
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") return;
          try {
            const parsed = JSON.parse(data) as Record<string, unknown>;
            if (parsed.type === "text-delta" && parsed.delta) {
              yield parsed.delta as string;
            } else if (parsed.type === "error" && parsed.content) {
              yield `Error: ${parsed.content as string}`;
            }
          } catch {
            // Non-JSON line — skip
          }
        }
      }
    } finally {
      if (idleTimer) clearTimeout(idleTimer);
      reader.releaseLock();
    }
  }

  private async postJson<T = unknown>(
    path: string,
    body: Record<string, unknown>,
  ): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    });
    if (!res.ok) throw new PlatformAPIError(res.status, await res.text());
    return res.json();
  }

  private headers(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      "X-Bot-API-Key": this.botApiKey,
    };
  }
}
