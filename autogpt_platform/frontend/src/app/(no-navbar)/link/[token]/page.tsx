"use client";

import { Button } from "@/components/atoms/Button/Button";
import { AuthCard } from "@/components/auth/AuthCard";
import { Text } from "@/components/atoms/Text/Text";
import { useSupabase } from "@/lib/supabase/hooks/useSupabase";
import { CheckCircle, LinkBreak, Spinner } from "@phosphor-icons/react";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

const PLATFORM_NAMES: Record<string, string> = {
  DISCORD: "Discord",
  TELEGRAM: "Telegram",
  SLACK: "Slack",
  TEAMS: "Teams",
  WHATSAPP: "WhatsApp",
  GITHUB: "GitHub",
  LINEAR: "Linear",
};

// Matches backend's Path validation on /tokens/{token}/... — URL-safe base64
// characters, bounded length. Keeps malformed params out of proxy fetches.
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

type LinkType = "SERVER" | "USER";

type LinkState =
  | { status: "loading" }
  | { status: "not-authenticated" }
  | {
      status: "ready";
      linkType: LinkType;
      serverName: string | null;
      platform: string | null;
    }
  | { status: "linking" }
  | {
      status: "success";
      linkType: LinkType;
      platform: string;
      serverName: string | null;
    }
  | { status: "error"; message: string };

export default function PlatformLinkPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const rawToken = params.token as string;
  // Defense-in-depth: backend validates with the same regex, but reject
  // obviously-malformed tokens early so we never construct a bad proxy URL.
  const token = TOKEN_PATTERN.test(rawToken) ? rawToken : null;
  const platformFromUrl =
    PLATFORM_NAMES[searchParams.get("platform")?.toUpperCase() ?? ""] ?? null;
  const { user, isUserLoading, logOut } = useSupabase();

  const [state, setState] = useState<LinkState>({ status: "loading" });

  useEffect(() => {
    if (!token) {
      setState({
        status: "error",
        message: "This setup link is malformed. Ask the bot for a new one.",
      });
      return;
    }
    if (isUserLoading) return;

    if (!user) {
      setState({ status: "not-authenticated" });
      return;
    }

    // Show immediately with a reasonable default (SERVER) while we fetch the
    // real token info — prevents UI flash. Old links without ?platform= just
    // show "chat platform" until the info call lands.
    setState({
      status: "ready",
      linkType: "SERVER",
      serverName: null,
      platform: platformFromUrl,
    });

    void fetchTokenInfo(token).then((info) => {
      if (!info) return;
      setState((prev) =>
        prev.status === "ready"
          ? {
              ...prev,
              linkType: info.linkType,
              platform: info.platform ?? prev.platform,
              serverName: info.serverName,
            }
          : prev,
      );
    });
  }, [token, user, isUserLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleLink() {
    if (state.status !== "ready") return;
    const { linkType, serverName } = state;
    const endpoint =
      linkType === "USER"
        ? `/api/proxy/api/platform-linking/user-tokens/${token}/confirm`
        : `/api/proxy/api/platform-linking/tokens/${token}/confirm`;

    setState({ status: "linking" });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        body: JSON.stringify({}),
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setState({
          status: "error",
          message:
            (data?.detail as string | undefined) ??
            "Failed to complete setup. The link may have expired.",
        });
        return;
      }

      const data = await res.json();
      setState({
        status: "success",
        linkType,
        platform:
          PLATFORM_NAMES[data.platform as string] ?? (data.platform as string),
        serverName: (data.server_name as string | null) ?? serverName,
      });
    } catch (err) {
      setState({
        status: "error",
        message:
          err instanceof DOMException && err.name === "AbortError"
            ? "Request timed out. Please go back to your chat and try again."
            : "Something went wrong. Please try again.",
      });
    } finally {
      clearTimeout(timeout);
    }
  }

  async function handleSwitchAccount() {
    await logOut();
    const loginUrl = `/login?next=${encodeURIComponent(`/link/${token}`)}`;
    window.location.href = loginUrl;
  }

  return (
    <div className="flex h-full min-h-[85vh] flex-col items-center justify-center py-10">
      {state.status === "loading" && <LoadingView />}
      {state.status === "not-authenticated" && token && (
        <NotAuthenticatedView token={token} />
      )}
      {state.status === "ready" && (
        <ReadyView
          onLink={handleLink}
          onSwitchAccount={handleSwitchAccount}
          linkType={state.linkType}
          serverName={state.serverName}
          platform={state.platform}
          userEmail={user?.email ?? null}
        />
      )}
      {state.status === "linking" && <LinkingView />}
      {state.status === "success" && (
        <SuccessView
          linkType={state.linkType}
          platform={state.platform}
          serverName={state.serverName}
        />
      )}
      {state.status === "error" && <ErrorView message={state.message} />}

      <div className="mt-8 text-center text-xs text-muted-foreground">
        <p>Powered by AutoGPT Platform</p>
      </div>
    </div>
  );
}

async function fetchTokenInfo(token: string): Promise<{
  platform: string | null;
  serverName: string | null;
  linkType: LinkType;
} | null> {
  try {
    const res = await fetch(
      `/api/proxy/api/platform-linking/tokens/${token}/info`,
      { signal: AbortSignal.timeout(5_000) },
    );
    if (!res.ok) return null;
    const data = await res.json();
    const platform =
      PLATFORM_NAMES[
        (data.platform as string | undefined)?.toUpperCase() ?? ""
      ] ?? null;
    const linkType: LinkType =
      (data.link_type as LinkType | undefined) === "USER" ? "USER" : "SERVER";
    return {
      platform,
      serverName: (data.server_name as string | null) ?? null,
      linkType,
    };
  } catch {
    return null;
  }
}

function LoadingView() {
  return (
    <AuthCard title="Setting up AutoPilot">
      <div className="flex flex-col items-center gap-4">
        <Spinner size={48} className="animate-spin text-primary" />
        <Text variant="body-medium" className="text-muted-foreground">
          Loading...
        </Text>
      </div>
    </AuthCard>
  );
}

function NotAuthenticatedView({ token }: { token: string }) {
  const loginUrl = `/login?next=${encodeURIComponent(`/link/${token}`)}`;

  return (
    <AuthCard title="Sign in to continue">
      <div className="flex w-full flex-col items-center gap-6">
        <Text
          variant="body-medium"
          className="text-center text-muted-foreground"
        >
          Sign in to your AutoGPT account to finish setting up AutoPilot.
        </Text>
        <Button as="NextLink" href={loginUrl} className="w-full">
          Sign in
        </Button>
        <AuthCard.BottomText
          text="Don't have an account?"
          link={{ text: "Sign up", href: `/signup?next=/link/${token}` }}
        />
      </div>
    </AuthCard>
  );
}

function ReadyView({
  onLink,
  onSwitchAccount,
  linkType,
  serverName,
  platform,
  userEmail,
}: {
  onLink: () => void;
  onSwitchAccount: () => void;
  linkType: LinkType;
  serverName: string | null;
  platform: string | null;
  userEmail: string | null;
}) {
  const platformLabel = platform ?? "chat platform";
  const isUserLink = linkType === "USER";

  const title = isUserLink
    ? `Link your ${platformLabel} DMs`
    : serverName
      ? `Set up AutoPilot for ${serverName}`
      : `Set up AutoPilot for this ${platformLabel} server`;

  const contextLabel = isUserLink
    ? `your ${platformLabel} DMs`
    : (serverName ?? `this ${platformLabel} server`);

  return (
    <AuthCard title={title}>
      <div className="flex w-full flex-col items-center gap-6">
        <div className="w-full rounded-xl bg-slate-50 p-5 text-left">
          <Text variant="body-medium" className="font-medium">
            What happens when you confirm:
          </Text>
          {isUserLink ? (
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              <li>{contextLabel} will be linked to your AutoGPT account</li>
              <li>DMs with the bot run as your personal AutoPilot</li>
              <li>All usage from those DMs is billed to your account</li>
            </ul>
          ) : (
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              <li>{contextLabel} will be connected to your AutoGPT account</li>
              <li>Everyone in the server can chat with AutoPilot</li>
              <li>Each person gets their own private conversation</li>
              <li>
                All usage from the server is billed to your AutoGPT account
              </li>
            </ul>
          )}
        </div>

        <div className="w-full rounded-xl border border-slate-200 bg-slate-50 p-4">
          <Text variant="small" className="text-muted-foreground">
            Usage from {contextLabel} will be billed to your AutoGPT account.
            You can unlink at any time from your account settings.
          </Text>
        </div>

        <Button onClick={onLink} className="w-full">
          {isUserLink
            ? `Connect my ${platformLabel} DMs`
            : `Connect ${platformLabel} to AutoGPT`}
        </Button>

        {userEmail && (
          <div className="flex w-full items-center justify-between">
            <Text variant="small" className="text-muted-foreground">
              Signed in as {userEmail}
            </Text>
            <button
              onClick={onSwitchAccount}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Not you? Sign out
            </button>
          </div>
        )}
      </div>
    </AuthCard>
  );
}

function LinkingView() {
  return (
    <AuthCard title="Connecting...">
      <div className="flex flex-col items-center gap-4">
        <Spinner size={48} className="animate-spin text-primary" />
        <Text variant="body-medium" className="text-muted-foreground">
          Setting up AutoPilot...
        </Text>
      </div>
    </AuthCard>
  );
}

function SuccessView({
  linkType,
  platform,
  serverName,
}: {
  linkType: LinkType;
  platform: string;
  serverName: string | null;
}) {
  const isUserLink = linkType === "USER";
  const label =
    isUserLink || !serverName ? `your ${platform} account` : serverName;
  const detail = isUserLink
    ? `You can now chat with AutoPilot in your ${platform} DMs.`
    : `Everyone in the server can start using AutoPilot right away.`;

  return (
    <AuthCard title="AutoPilot is ready!">
      <div className="flex w-full flex-col items-center gap-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
          <CheckCircle size={40} weight="fill" className="text-green-600" />
        </div>
        <Text
          variant="body-medium"
          className="text-center text-muted-foreground"
        >
          <strong>{label}</strong> is now connected to your AutoGPT account.
          <br />
          {detail}
        </Text>
        <Text variant="small" className="text-center text-muted-foreground">
          You can close this page and go back to your chat.
        </Text>
      </div>
    </AuthCard>
  );
}

function ErrorView({ message }: { message: string }) {
  return (
    <AuthCard title="Setup failed">
      <div className="flex w-full flex-col items-center gap-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
          <LinkBreak size={40} weight="bold" className="text-red-600" />
        </div>
        <Text
          variant="body-medium"
          className="text-center text-muted-foreground"
        >
          {message}
        </Text>
        <Text variant="small" className="text-center text-muted-foreground">
          Go back to your chat and ask the bot for a new setup link.
        </Text>
      </div>
    </AuthCard>
  );
}
