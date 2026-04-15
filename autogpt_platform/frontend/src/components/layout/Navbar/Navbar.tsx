"use client";

import { useGetV2GetUserProfile } from "@/app/api/__generated__/endpoints/store/store";
import { okData } from "@/app/api/helpers";
import { IconType } from "@/components/__legacy__/ui/icons";
import { PreviewBanner } from "@/components/layout/Navbar/components/PreviewBanner/PreviewBanner";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { isLogoutInProgress } from "@/lib/autogpt-server-api/helpers";
import { useBreakpoint } from "@/lib/hooks/useBreakpoint";
import { useSupabase } from "@/lib/supabase/hooks/useSupabase";
import { environment } from "@/services/environment";
import { Flag, useGetFlag } from "@/services/feature-flags/use-get-flag";
import { List } from "@phosphor-icons/react";
import { AccountMenu } from "./components/AccountMenu/AccountMenu";
import { LoginButton } from "./components/LoginButton";
import { MobileNavBar } from "./components/MobileNavbar/MobileNavBar";
import { Wallet } from "./components/Wallet/Wallet";
import { getAccountMenuItems, loggedInLinks } from "./helpers";

export function Navbar() {
  const { user, isLoggedIn, isUserLoading } = useSupabase();
  const breakpoint = useBreakpoint();
  const isSmallScreen = breakpoint === "sm" || breakpoint === "base";
  const dynamicMenuItems = getAccountMenuItems(user?.role);
  const previewBranchName = environment.getPreviewStealingDev();
  const logoutInProgress = isLogoutInProgress();
  const isNewSidebar = useGetFlag(Flag.NEW_SIDEBAR);

  const { data: profile, isLoading: isProfileLoading } = useGetV2GetUserProfile(
    {
      query: {
        select: okData,
        enabled: isLoggedIn && !!user && !logoutInProgress,
        queryKey: ["/api/store/profile", user?.id],
      },
    },
  );

  const isLoadingProfile = isProfileLoading || isUserLoading;
  const shouldShowPreviewBanner = Boolean(isLoggedIn && previewBranchName);

  const actualLoggedInLinks = [
    { name: "Home", href: "/copilot" },
    { name: "Agents", href: "/library" },
    ...loggedInLinks,
  ];

  if (isUserLoading) {
    return null;
  }

  return (
    <>
      {shouldShowPreviewBanner && previewBranchName ? (
        <div className="sticky top-0 z-40 w-full">
          <PreviewBanner branchName={previewBranchName} />
        </div>
      ) : null}

      {!isLoggedIn ? (
        <div className="flex w-full justify-end p-3">
          <LoginButton />
        </div>
      ) : null}

      {/* Desktop top-right: profile + feedback */}
      {isLoggedIn && !isSmallScreen ? (
        <div className="flex items-center justify-end gap-3 px-4 py-3">
          {profile && <Wallet key={profile.username} />}
          <AccountMenu
            userName={profile?.username}
            userEmail={profile?.name}
            avatarSrc={profile?.avatar_url ?? ""}
            menuItemGroups={dynamicMenuItems}
            isLoading={isLoadingProfile}
          />
        </div>
      ) : null}

      {/* Mobile top bar: new sidebar trigger + wallet (new) or MobileNavBar (old) */}
      {isLoggedIn && isSmallScreen && isNewSidebar ? (
        <div className="fixed right-0 top-0 z-50 flex items-center gap-2 px-3 py-2">
          <SidebarTrigger className="flex size-10 items-center justify-center rounded-full border border-zinc-200 bg-white [&>svg]:!size-5">
            <List className="!size-5" weight="bold" />
          </SidebarTrigger>
          <Wallet />
        </div>
      ) : null}

      {isLoggedIn && isSmallScreen && !isNewSidebar ? (
        <div className="fixed right-0 top-2 z-50 flex items-center gap-0">
          <Wallet />
          <MobileNavBar
            userName={profile?.username}
            menuItemGroups={[
              {
                groupName: "Navigation",
                items: actualLoggedInLinks
                  .map((link) => {
                    return {
                      icon:
                        link.href === "/marketplace"
                          ? IconType.Marketplace
                          : link.href === "/build"
                            ? IconType.Builder
                            : link.href === "/copilot"
                              ? IconType.Chat
                              : link.href === "/library"
                                ? IconType.Library
                                : link.href === "/monitor"
                                  ? IconType.Library
                                  : IconType.LayoutDashboard,
                      text: link.name,
                      href: link.href,
                    };
                  })
                  .filter((item) => item !== null) as Array<{
                  icon: IconType;
                  text: string;
                  href: string;
                }>,
              },
              ...dynamicMenuItems,
            ]}
            userEmail={profile?.name}
            avatarSrc={profile?.avatar_url ?? ""}
          />
        </div>
      ) : null}
    </>
  );
}
