"use client";

import type { DecompositionStepModel } from "@/app/api/__generated__/models/decompositionStepModel";
import {
  CheckCircleIcon,
  CircleDashedIcon,
  ListChecksIcon,
  SpinnerGapIcon,
  WarningDiamondIcon,
  XCircleIcon,
} from "@phosphor-icons/react";
import type { ToolUIPart } from "ai";
import { ScaleLoader } from "../../components/ScaleLoader/ScaleLoader";

// Re-export generated step type for consumers that need it.
export type DecompositionStep = DecompositionStepModel;

// Hand-rolled because the tool output is parsed from opaque JSON (not through
// the generated API client), so the runtime shape differs from the generated
// TaskDecompositionResponse — notably ``created_at`` is an ISO 8601 string at
// runtime, whereas the generated type declares ``Date``. Keep fields in sync
// with backend ``TaskDecompositionResponse`` in tools/models.py.
export interface TaskDecompositionOutput {
  type: string;
  message: string;
  session_id?: string | null;
  goal: string;
  steps: DecompositionStep[];
  step_count: number;
  requires_approval: boolean;
  auto_approve_seconds?: number;
  created_at?: string;
}

export interface DecomposeErrorOutput {
  type: string;
  error?: string;
  message?: string;
}

export type DecomposeGoalOutput =
  | TaskDecompositionOutput
  | DecomposeErrorOutput;

// Fallback used only if the backend response omits auto_approve_seconds
// (older sessions). The authoritative value comes from the tool output.
export const FALLBACK_COUNTDOWN_SECONDS = 60;

/**
 * Compute remaining countdown seconds, deriving elapsed time from the
 * backend-stamped ``created_at`` so the timer reflects real elapsed time
 * when the user reopens the session — instead of restarting from full.
 *
 * Falls back to the full countdown when ``created_at`` is missing (older
 * sessions stored before this field existed) or unparseable. Clamps to
 * ``[0, total]`` to defend against client clock skew producing future
 * timestamps.
 */
export function computeRemainingSeconds(
  output: DecomposeGoalOutput | null,
  fallback: number,
): number {
  if (!output || !isDecompositionOutput(output)) return fallback;
  const total = output.auto_approve_seconds ?? fallback;
  if (!output.created_at) return total;
  const createdAtMs = new Date(output.created_at).getTime();
  if (Number.isNaN(createdAtMs)) return total;
  const elapsedSec = (Date.now() - createdAtMs) / 1000;
  return Math.max(0, Math.min(total, Math.round(total - elapsedSec)));
}

function parseOutput(output: unknown): DecomposeGoalOutput | null {
  if (!output) return null;
  if (typeof output === "string") {
    const trimmed = output.trim();
    if (!trimmed) return null;
    try {
      return parseOutput(JSON.parse(trimmed) as unknown);
    } catch {
      return null;
    }
  }
  if (typeof output === "object" && !Array.isArray(output)) {
    const obj = output as Record<string, unknown>;
    if (
      "steps" in obj &&
      "goal" in obj &&
      Array.isArray(obj.steps) &&
      typeof obj.goal === "string"
    ) {
      return obj as unknown as TaskDecompositionOutput;
    }
    if ("error" in obj && typeof obj.error === "string") {
      return obj as unknown as DecomposeErrorOutput;
    }
    // Message-only error payload (no 'error' key but also not a decomposition)
    if ("message" in obj && typeof obj.message === "string") {
      return obj as unknown as DecomposeErrorOutput;
    }
  }
  return null;
}

export function getDecomposeGoalOutput(
  part: unknown,
): DecomposeGoalOutput | null {
  if (!part || typeof part !== "object") return null;
  return parseOutput((part as { output?: unknown }).output);
}

export function isDecompositionOutput(
  output: DecomposeGoalOutput,
): output is TaskDecompositionOutput {
  return (
    "steps" in output &&
    Array.isArray((output as TaskDecompositionOutput).steps) &&
    "goal" in output
  );
}

export function isErrorOutput(
  output: DecomposeGoalOutput,
): output is DecomposeErrorOutput {
  return "error" in output;
}

export function getAnimationText(part: {
  state: ToolUIPart["state"];
  output?: unknown;
}): string {
  switch (part.state) {
    case "input-streaming":
    case "input-available":
      return "Analyzing your goal...";
    case "output-available": {
      const output = parseOutput(part.output);
      if (output && isDecompositionOutput(output))
        return `Plan ready (${output.step_count} steps)`;
      return "Analyzing your goal...";
    }
    case "output-error":
      return "Error analyzing goal";
    default:
      return "Analyzing your goal...";
  }
}

export function ToolIcon({
  isStreaming,
  isError,
}: {
  isStreaming?: boolean;
  isError?: boolean;
}) {
  if (isError) {
    return (
      <WarningDiamondIcon size={14} weight="regular" className="text-red-500" />
    );
  }
  if (isStreaming) {
    return <ScaleLoader size={14} />;
  }
  return (
    <ListChecksIcon size={14} weight="regular" className="text-neutral-400" />
  );
}

export function AccordionIcon() {
  return <ListChecksIcon size={32} weight="light" />;
}

export function StepStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return (
        <CheckCircleIcon
          size={18}
          weight="fill"
          className="text-emerald-500"
          aria-label="completed"
        />
      );
    case "in_progress":
      return (
        <SpinnerGapIcon
          size={18}
          weight="bold"
          className="animate-spin text-blue-500"
          aria-label="in progress"
        />
      );
    case "failed":
      return (
        <XCircleIcon
          size={18}
          weight="fill"
          className="text-red-500"
          aria-label="failed"
        />
      );
    default:
      return (
        <CircleDashedIcon
          size={18}
          weight="regular"
          className="text-neutral-400"
          aria-label="pending"
        />
      );
  }
}
