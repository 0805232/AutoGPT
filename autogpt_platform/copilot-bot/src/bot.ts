/**
 * CoPilot Bot — core message handling using the Chat SDK.
 *
 * Two independent linking flows:
 * - SERVER: the first person to run /setup in a group/guild claims it as
 *   owner. Everyone in the server can mention the bot; all conversations
 *   are billed to the owner's AutoGPT account.
 * - USER (DM): an individual links their own DMs with the bot via a token.
 *   Those conversations are billed to that user's own AutoGPT account.
 *
 * Server links and user links are fully independent — a user who owns a
 * linked server still has to link their DMs separately.
 */

import { Chat } from "chat";
import type { Adapter, StateAdapter, Thread, Message } from "chat";
import { PlatformAPI, PlatformAPIError } from "./platform-api.js";
import type { Config } from "./config.js";

/** Thread state persisted across messages in a conversation. */
export interface BotThreadState {
  /** CoPilot session ID for this conversation. */
  sessionId?: string;
  /** Pending setup token (sent while waiting for user to complete link). */
  pendingLinkToken?: string;
}

type BotThread = Thread<BotThreadState>;

export async function createBot(config: Config, stateAdapter: StateAdapter) {
  const api = new PlatformAPI(config.autogptApiUrl);

  const adapters: Record<string, Adapter> = {};

  if (config.discord) {
    const { createDiscordAdapter } = await import("@chat-adapter/discord");
    adapters.discord = createDiscordAdapter();
  }
  if (config.telegram) {
    const { createTelegramAdapter } = await import("@chat-adapter/telegram");
    adapters.telegram = createTelegramAdapter();
  }
  if (config.slack) {
    const { createSlackAdapter } = await import("@chat-adapter/slack");
    adapters.slack = createSlackAdapter();
  }

  if (Object.keys(adapters).length === 0) {
    throw new Error(
      "No adapters configured. Set at least one of: " +
        "DISCORD_BOT_TOKEN, TELEGRAM_BOT_TOKEN, SLACK_BOT_TOKEN",
    );
  }

  const bot = new Chat<typeof adapters, BotThreadState>({
    userName: "copilot",
    adapters,
    state: stateAdapter,
  });

  // ── New mention (first message in a thread) ──────────────────────────

  bot.onNewMention(async (thread, message) => {
    const ctx = resolveContext(thread.id, message.author.userId);
    console.log(`[bot] Mention ${ctx.describe()}`);

    if (isHelpCommand(message.text)) {
      await thread.post(helpText());
      return;
    }

    if (await ensureLinked(thread, message, ctx, api)) {
      if (!ctx.isDM) await thread.subscribe();
      await handleCoPilotMessage(thread, message, ctx, api);
    }
  });

  // ── Follow-up messages in a subscribed thread ────────────────────────

  bot.onSubscribedMessage(async (thread, message) => {
    const ctx = resolveContext(thread.id, message.author.userId);
    console.log(`[bot] Follow-up ${ctx.describe()}`);

    if (isHelpCommand(message.text)) {
      await thread.post(helpText());
      return;
    }

    // Re-check linking — the owner may have just completed /setup.
    if (await ensureLinked(thread, message, ctx, api)) {
      await handleCoPilotMessage(thread, message, ctx, api);
    }
  });

  // /setup and /help slash commands are dispatched by src/discord/handlers.ts
  // via the Gateway interaction interceptor.

  return bot;
}

// ── Context detection ────────────────────────────────────────────────────────

/**
 * Where a message is coming from. Server and DM contexts route to totally
 * different link tables, so we want one clear discriminator at the top.
 */
interface MessageContext {
  platform: string;
  isDM: boolean;
  /** For SERVER context: guild / group ID. For DM: always undefined. */
  serverId?: string;
  /** Platform user ID of the sender (always set). */
  platformUserId: string;
  describe(): string;
}

function resolveContext(threadId: string, platformUserId: string): MessageContext {
  const platform = threadId.split(":")[0] ?? "unknown";
  const segment = threadId.split(":")[1] ?? threadId;
  const dm = isDMSegment(platform, segment, platformUserId);
  return {
    platform,
    isDM: dm,
    serverId: dm ? undefined : segment,
    platformUserId,
    describe() {
      return dm
        ? `in ${platform} DM with user ${platformUserId}`
        : `in ${platform} server ${segment} from user ${platformUserId}`;
    },
  };
}

/**
 * Whether this thread ID segment represents a DM, not a group/server.
 * - Telegram: DMs have positive chat IDs (groups are negative).
 * - Discord: DMs use guild ID "@me".
 * - Fallback: the segment equals the user's ID.
 */
function isDMSegment(
  platform: string,
  segment: string,
  platformUserId: string,
): boolean {
  if (platform === "telegram") return !segment.startsWith("-");
  if (platform === "discord") return segment === "@me";
  return segment === platformUserId;
}

// ── Link resolution ──────────────────────────────────────────────────────────

/**
 * Ensure this context has an active link. If linked, returns true and the
 * caller proceeds. If unlinked, posts a setup prompt/link and returns false.
 */
async function ensureLinked(
  thread: BotThread,
  message: Message,
  ctx: MessageContext,
  api: PlatformAPI,
): Promise<boolean> {
  if (ctx.isDM) {
    const resolved = await api.resolveUser(ctx.platform, ctx.platformUserId);
    if (resolved.linked) return true;
    await promptUserLink(thread, message, ctx, api);
    return false;
  }

  if (!ctx.serverId) return false;
  const resolved = await api.resolveServer(ctx.platform, ctx.serverId);
  if (resolved.linked) return true;
  await promptServerLink(thread);
  return false;
}

/**
 * Unlinked server: point the user at /setup. The link URL itself is never
 * posted in the channel — /setup responds ephemerally with it.
 */
async function promptServerLink(thread: BotThread): Promise<void> {
  await thread.post(
    "This server isn't linked to an AutoGPT account yet. Run `/setup` to connect it — you'll get a private setup link only you can see.",
  );
}

/**
 * Unlinked DM: create a USER token and post the link directly. DMs are
 * already private so posting in-thread is fine.
 */
async function promptUserLink(
  thread: BotThread,
  message: Message,
  ctx: MessageContext,
  api: PlatformAPI,
): Promise<void> {
  try {
    const link = await api.createUserLinkToken({
      platform: ctx.platform,
      platformUserId: ctx.platformUserId,
      platformUsername: message.author.userName ?? message.author.fullName,
    });
    await thread.post(
      `To use AutoPilot here, link your ${displayPlatform(ctx.platform)} account to AutoGPT:\n\n${link.link_url}\n\nThis link expires in 30 minutes.`,
    );
    await thread.setState({ pendingLinkToken: link.token });
  } catch (err) {
    // 409 → someone just linked between resolve and token-create. Re-check.
    if (err instanceof PlatformAPIError && err.status === 409) {
      const resolved = await api.resolveUser(ctx.platform, ctx.platformUserId);
      if (resolved.linked) {
        await handleCoPilotMessage(thread, message, ctx, api);
        return;
      }
    }
    console.error("[bot] Failed to create user link token:", err);
    await thread.post(
      "Sorry, I couldn't set up account linking right now. Please try again later.",
    );
  }
}

// ── CoPilot streaming ────────────────────────────────────────────────────────

async function handleCoPilotMessage(
  thread: BotThread,
  message: Message,
  ctx: MessageContext,
  api: PlatformAPI,
): Promise<void> {
  const username = message.author.userName ?? message.author.fullName;
  const text = withUserIdentity(
    message.text,
    ctx.platform,
    ctx.platformUserId,
    username,
  );

  const state = await thread.state;
  let sessionId = state?.sessionId;

  // Discord's typing indicator clears after ~10s. Re-fire it on a loop so the
  // user sees "bot is typing" the whole time CoPilot is working.
  await thread.startTyping();
  const typingInterval = setInterval(() => {
    void thread.startTyping().catch(() => {});
  }, 8_000);

  try {
    if (!sessionId) {
      sessionId = await api.createChatSession({
        platform: ctx.platform,
        platformUserId: ctx.platformUserId,
        platformServerId: ctx.serverId,
      });
      await thread.setState({ ...state, sessionId });
      console.log(`[bot] Created session ${sessionId} ${ctx.describe()}`);
    }

    const stream = api.streamChat({
      platform: ctx.platform,
      platformUserId: ctx.platformUserId,
      platformServerId: ctx.serverId,
      message: text,
      sessionId,
    });

    let response = "";
    for await (const chunk of stream) response += chunk;

    if (response.trim()) {
      await thread.post(response);
    } else {
      await thread.post(
        "I processed your message but didn't generate a response. Please try again.",
      );
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[bot] CoPilot error ${ctx.describe()}: ${msg}`);
    await thread.post(
      "Sorry, I ran into an issue processing your message. Please try again.",
    );
  } finally {
    clearInterval(typingInterval);
  }
}

// ── Misc helpers ─────────────────────────────────────────────────────────────

function isHelpCommand(text: string): boolean {
  return text.trim().toLowerCase().startsWith("/help");
}

function displayPlatform(platform: string): string {
  return (
    { discord: "Discord", telegram: "Telegram", slack: "Slack" }[platform] ??
    platform
  );
}

/**
 * Prefix the user's message with a platform identity block so the LLM knows
 * who is speaking. Without this, CoPilot would treat every user in a linked
 * server as the server owner.
 *
 * Deliberately no "@" prefix on the username — the LLM copies that format
 * into its replies as "<@username>" which Discord won't render as a real
 * mention (mentions require the numeric ID).
 */
function withUserIdentity(
  text: string,
  platform: string,
  platformUserId: string,
  username: string | undefined,
): string {
  const display = displayPlatform(platform);
  const who = username
    ? `${username} (${display} user ID: ${platformUserId})`
    : `${display} user ID: ${platformUserId}`;
  return `[Message sent by ${who}]\n${text}`;
}

function helpText(): string {
  return (
    "**AutoPilot** — Your AutoGPT assistant\n\n" +
    "**Getting started:**\n" +
    "• In a server: run `/setup` once to link it. Everyone can chat after that — all usage bills to the person who ran /setup.\n" +
    "• In DMs: message me and I'll send you a private link to connect your own account.\n\n" +
    "**Commands:**\n" +
    "• `/setup` — link the current server\n" +
    "• `/unlink` — manage linked servers\n" +
    "• `/help` — show this message"
  );
}
