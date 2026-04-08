/**
 * Discord webhook handler.
 * Vercel route: POST /api/webhooks/discord
 *
 * Handles Discord HTTP interactions (slash commands, button clicks, pings).
 * Regular messages arrive via the Gateway cron (api/gateway/discord.ts).
 */

import { getBotInstance } from "../_bot.js";

export async function POST(request: Request): Promise<Response> {
  const bot = await getBotInstance();
  return bot.webhooks.discord(request);
}
