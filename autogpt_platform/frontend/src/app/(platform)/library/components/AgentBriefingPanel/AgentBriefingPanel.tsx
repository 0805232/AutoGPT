"use client";

import { Text } from "@/components/atoms/Text/Text";
import type { LibraryAgent } from "@/app/api/__generated__/models/libraryAgent";
import { useState } from "react";
import type { FleetSummary, AgentStatusFilter } from "../../types";
import { BriefingTabContent } from "./BriefingTabContent";
import { StatsGrid } from "./StatsGrid";
import styles from "./AgentBriefingPanel.module.css";

interface Props {
  summary: FleetSummary;
  agents: LibraryAgent[];
}

export function AgentBriefingPanel({ summary, agents }: Props) {
  const defaultTab: AgentStatusFilter = summary.running > 0 ? "running" : "all";
  const [activeTab, setActiveTab] = useState<AgentStatusFilter>(defaultTab);

  return (
    <div className={`${styles.glassPanel} min-h-[14.75rem] rounded-large bg-gradient-to-br from-indigo-50/60 via-white/80 to-purple-50/50 px-5 pb-5 pt-2 shadow-sm backdrop-blur-md`}>
      <Text variant="h5">Agent Briefing</Text>
      <div className="mt-4 space-y-5">
        <StatsGrid
          summary={summary}
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />
        <BriefingTabContent activeTab={activeTab} agents={agents} />
      </div>
    </div>
  );
}
