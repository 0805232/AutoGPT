-- CreateEnum
CREATE TYPE "PlatformType" AS ENUM ('DISCORD', 'TELEGRAM', 'SLACK', 'TEAMS', 'WHATSAPP', 'GITHUB', 'LINEAR');

-- CreateEnum
-- Server links (group chats / guilds) and user links (personal DMs) are
-- fully independent — a user who owns a linked server still has to link
-- their DMs separately.
CREATE TYPE "PlatformLinkType" AS ENUM ('SERVER', 'USER');

-- CreateTable
-- PlatformLink maps a platform server (Discord guild, Telegram group, etc.) to an AutoGPT
-- owner account. The first user to authenticate becomes the owner — all usage from that
-- server is billed to their account. Each user within the server gets their own CoPilot
-- session, all visible in the owner's AutoGPT account.
CREATE TABLE "PlatformLink" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "platform" "PlatformType" NOT NULL,
    "platformServerId" TEXT NOT NULL,
    "ownerPlatformUserId" TEXT NOT NULL,
    "serverName" TEXT,
    "linkedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PlatformLink_pkey" PRIMARY KEY ("id")
);

-- CreateTable
-- PlatformUserLink maps an individual platform user identity to an AutoGPT
-- account for 1:1 DMs with the bot. Independent from PlatformLink.
CREATE TABLE "PlatformUserLink" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "platform" "PlatformType" NOT NULL,
    "platformUserId" TEXT NOT NULL,
    "platformUsername" TEXT,
    "linkedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PlatformUserLink_pkey" PRIMARY KEY ("id")
);

-- CreateTable
-- PlatformLinkToken is a one-time token for either a SERVER or USER link.
-- SERVER tokens carry platformServerId + serverName; USER tokens leave those
-- null and use platformUserId as the target.
CREATE TABLE "PlatformLinkToken" (
    "id" TEXT NOT NULL,
    "token" TEXT NOT NULL,
    "platform" "PlatformType" NOT NULL,
    "linkType" "PlatformLinkType" NOT NULL DEFAULT 'SERVER',
    "platformServerId" TEXT,
    "platformUserId" TEXT NOT NULL,
    "platformUsername" TEXT,
    "serverName" TEXT,
    "channelId" TEXT,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "usedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PlatformLinkToken_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "PlatformLink_platform_platformServerId_key" ON "PlatformLink"("platform", "platformServerId");

-- CreateIndex
CREATE INDEX "PlatformLink_userId_idx" ON "PlatformLink"("userId");

-- CreateIndex
CREATE UNIQUE INDEX "PlatformUserLink_platform_platformUserId_key" ON "PlatformUserLink"("platform", "platformUserId");

-- CreateIndex
CREATE INDEX "PlatformUserLink_userId_idx" ON "PlatformUserLink"("userId");

-- CreateIndex
CREATE UNIQUE INDEX "PlatformLinkToken_token_key" ON "PlatformLinkToken"("token");

-- CreateIndex
CREATE INDEX "PlatformLinkToken_platform_platformServerId_idx" ON "PlatformLinkToken"("platform", "platformServerId");

-- CreateIndex
CREATE INDEX "PlatformLinkToken_platform_platformUserId_idx" ON "PlatformLinkToken"("platform", "platformUserId");

-- CreateIndex
CREATE INDEX "PlatformLinkToken_expiresAt_idx" ON "PlatformLinkToken"("expiresAt");

-- AddForeignKey
ALTER TABLE "PlatformLink" ADD CONSTRAINT "PlatformLink_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PlatformUserLink" ADD CONSTRAINT "PlatformUserLink_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
