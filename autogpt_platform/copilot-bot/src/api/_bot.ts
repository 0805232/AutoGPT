/**
 * Singleton bot instance for serverless environments.
 *
 * In serverless (Vercel), each request may hit a cold or warm function instance.
 * We create the bot once per instance using a module-level promise to prevent
 * concurrent cold-start races from creating duplicate instances.
 */

import { loadConfig } from "../config.js";
import { createBot } from "../bot.js";

type BotInstance = Awaited<ReturnType<typeof createBot>>;

let _instance: BotInstance | null = null;
let _initializing: Promise<BotInstance> | null = null;

export async function getBotInstance(): Promise<BotInstance> {
  if (_instance) return _instance;

  // If already initializing, wait for that promise instead of starting another
  if (_initializing) return _initializing;

  _initializing = (async () => {
    const config = loadConfig();

    let stateAdapter;
    if (config.redisUrl) {
      const { createRedisState } = await import("@chat-adapter/state-redis");
      stateAdapter = createRedisState({ url: config.redisUrl });
    } else {
      const { createMemoryState } = await import("@chat-adapter/state-memory");
      stateAdapter = createMemoryState();
    }

    const bot = await createBot(config, stateAdapter);
    _instance = bot;
    console.log("[bot] Instance initialised (serverless)");
    return bot;
  })();

  try {
    return await _initializing;
  } finally {
    _initializing = null;
  }
}
