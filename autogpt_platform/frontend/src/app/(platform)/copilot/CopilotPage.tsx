"use client";

import { SidebarProvider } from "@/components/ui/sidebar";
import { Flag, useGetFlag } from "@/services/feature-flags/use-get-flag";
import { Flask } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import { useState } from "react";
import { ChatContainer } from "./components/ChatContainer/ChatContainer";
import { ChatSidebar } from "./components/ChatSidebar/ChatSidebar";
import { FileDropZone } from "./components/FileDropZone/FileDropZone";
import { MobileDrawer } from "./components/MobileDrawer/MobileDrawer";
import { MobileHeader } from "./components/MobileHeader/MobileHeader";
import { NotificationBanner } from "./components/NotificationBanner/NotificationBanner";
import { NotificationDialog } from "./components/NotificationDialog/NotificationDialog";
import { RateLimitGate } from "./components/RateLimitResetDialog/RateLimitGate";
import { ScaleLoader } from "./components/ScaleLoader/ScaleLoader";
import { useCopilotPage } from "./useCopilotPage";
import { useIsMobile } from "./useIsMobile";

const ArtifactPanel = dynamic(
  () =>
    import("./components/ArtifactPanel/ArtifactPanel").then(
      (m) => m.ArtifactPanel,
    ),
  { ssr: false },
);

export function CopilotPage() {
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
  const isMobile = useIsMobile();
  const isArtifactsEnabled = useGetFlag(Flag.ARTIFACTS);

  const {
    sessionId,
    messages,
    status,
    error,
    stop,
    isReconnecting,
    isSyncing,
    isRetrievingStream,
    streamRetrievalFailed,
    createSession,
    onSend,
    onEnqueue,
    queuedMessages,
    isLoadingSession,
    isSessionError,
    isCreatingSession,
    isUploadingFiles,
    isUserLoading,
    isLoggedIn,
    hasMoreMessages,
    isLoadingMore,
    loadMore,
    historicalDurations,
    rateLimitMessage,
    dismissRateLimit,
    sessionDryRun,
  } = useCopilotPage();

  if (isUserLoading || !isLoggedIn) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#f8f8f9]">
        <ScaleLoader className="text-neutral-400" />
      </div>
    );
  }

  return (
    <SidebarProvider
      defaultOpen={true}
      className="h-[calc(100vh-72px)] min-h-0"
    >
      {!isMobile && <ChatSidebar />}
      <div className="flex h-full w-full flex-row overflow-hidden">
        <FileDropZone
          className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-[#f8f8f9] px-0"
          onFilesDropped={setDroppedFiles}
        >
          {isMobile && <MobileHeader />}
          <NotificationBanner />
          {/* Only shown when the CURRENT session is confirmed dry_run via its
              immutable metadata. Never based on the global isDryRun preference
              (which only predicts future sessions) — users browsing non-dry-run
              sessions while the toggle is on would otherwise see a misleading
              banner. The DryRunToggleButton on new chats communicates the
              preference. */}
          {sessionId && sessionDryRun && (
            <div className="flex items-center justify-center gap-1.5 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800">
              <Flask size={13} weight="bold" />
              Test mode — this session runs agents as simulation
            </div>
          )}
          <div className="flex-1 overflow-hidden">
            <ChatContainer
              messages={messages}
              status={status}
              error={error}
              sessionId={sessionId}
              isLoadingSession={isLoadingSession}
              isSessionError={isSessionError}
              isCreatingSession={isCreatingSession}
              isReconnecting={isReconnecting}
              isSyncing={isSyncing}
              isRetrievingStream={isRetrievingStream}
              streamRetrievalFailed={streamRetrievalFailed}
              onCreateSession={createSession}
              onSend={onSend}
              onStop={stop}
              onEnqueue={onEnqueue}
              queuedMessages={queuedMessages}
              isUploadingFiles={isUploadingFiles}
              hasMoreMessages={hasMoreMessages}
              isLoadingMore={isLoadingMore}
              onLoadMore={loadMore}
              droppedFiles={droppedFiles}
              onDroppedFilesConsumed={() => setDroppedFiles([])}
              historicalDurations={historicalDurations}
            />
          </div>
        </FileDropZone>
        {!isMobile && isArtifactsEnabled && <ArtifactPanel />}
      </div>
      {isMobile && isArtifactsEnabled && <ArtifactPanel mobile />}
      {isMobile && <MobileDrawer />}
      <NotificationDialog />
      <RateLimitGate
        rateLimitMessage={rateLimitMessage}
        onDismiss={dismissRateLimit}
      />
    </SidebarProvider>
  );
}
