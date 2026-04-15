/**
 * Unit tests for DecomposeGoal/helpers.tsx
 *
 * Covers: parseOutput / getDecomposeGoalOutput, type guards, getAnimationText
 */

import { describe, expect, it, vi } from "vitest";
import {
  computeRemainingSeconds,
  FALLBACK_COUNTDOWN_SECONDS,
  getAnimationText,
  getDecomposeGoalOutput,
  isDecompositionOutput,
  isErrorOutput,
  type DecomposeErrorOutput,
  type DecomposeGoalOutput,
  type TaskDecompositionOutput,
} from "../helpers";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DECOMPOSITION: TaskDecompositionOutput = {
  type: "task_decomposition",
  message: "Here's the plan (3 steps):",
  goal: "Build a news summarizer",
  steps: [
    {
      step_id: "step_1",
      description: "Add input block",
      action: "add_input",
      block_name: null,
      status: "pending",
    },
    {
      step_id: "step_2",
      description: "Add AI summarizer",
      action: "add_block",
      block_name: "AI Text Generator",
      status: "pending",
    },
    {
      step_id: "step_3",
      description: "Connect blocks",
      action: "connect_blocks",
      block_name: null,
      status: "pending",
    },
  ],
  step_count: 3,
  requires_approval: true,
};

const ERROR_OUTPUT: DecomposeErrorOutput = {
  type: "error",
  error: "missing_steps",
  message: "Please provide at least one step.",
};

// ---------------------------------------------------------------------------
// isDecompositionOutput
// ---------------------------------------------------------------------------

describe("isDecompositionOutput", () => {
  it("returns true for a full decomposition output", () => {
    expect(isDecompositionOutput(DECOMPOSITION)).toBe(true);
  });

  it("returns false for an error output", () => {
    expect(
      isDecompositionOutput(ERROR_OUTPUT as unknown as DecomposeGoalOutput),
    ).toBe(false);
  });

  it("returns false when steps is not an array (type guard tightness)", () => {
    const malformed = {
      steps: "not-an-array",
      goal: "test",
    } as unknown as DecomposeGoalOutput;
    expect(isDecompositionOutput(malformed)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isErrorOutput
// ---------------------------------------------------------------------------

describe("isErrorOutput", () => {
  it("returns true for error output", () => {
    expect(isErrorOutput(ERROR_OUTPUT as unknown as DecomposeGoalOutput)).toBe(
      true,
    );
  });

  it("returns false for decomposition output", () => {
    expect(isErrorOutput(DECOMPOSITION)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// getDecomposeGoalOutput — output parsing
// ---------------------------------------------------------------------------

describe("getDecomposeGoalOutput", () => {
  it("parses a direct object output", () => {
    const part = { output: DECOMPOSITION };
    const result = getDecomposeGoalOutput(part);
    expect(result).not.toBeNull();
    expect(isDecompositionOutput(result!)).toBe(true);
  });

  it("parses a JSON-encoded string output", () => {
    const part = { output: JSON.stringify(DECOMPOSITION) };
    const result = getDecomposeGoalOutput(part);
    expect(result).not.toBeNull();
    expect(isDecompositionOutput(result!)).toBe(true);
    expect((result as TaskDecompositionOutput).goal).toBe(
      "Build a news summarizer",
    );
  });

  it("parses an error output object", () => {
    const part = { output: ERROR_OUTPUT };
    const result = getDecomposeGoalOutput(part);
    expect(result).not.toBeNull();
    expect(isErrorOutput(result!)).toBe(true);
  });

  it("returns null for falsy output", () => {
    expect(getDecomposeGoalOutput({ output: null })).toBeNull();
    expect(getDecomposeGoalOutput({ output: undefined })).toBeNull();
    expect(getDecomposeGoalOutput({ output: "" })).toBeNull();
  });

  it("returns null for a plain non-JSON string", () => {
    expect(getDecomposeGoalOutput({ output: "just text" })).toBeNull();
  });

  it("returns null for a non-object part", () => {
    expect(getDecomposeGoalOutput(null)).toBeNull();
    expect(getDecomposeGoalOutput("string")).toBeNull();
    expect(getDecomposeGoalOutput(42)).toBeNull();
  });

  it("returns null for an array-type output (not a valid shape)", () => {
    expect(
      getDecomposeGoalOutput({ output: ["not", "an", "object"] }),
    ).toBeNull();
  });

  it("classifies 'steps+goal' before 'error' when object has all three keys", () => {
    // Verify type discrimination precedence: steps+goal wins
    const mixed = { ...DECOMPOSITION, error: "some_error" };
    const part = { output: mixed };
    const result = getDecomposeGoalOutput(part);
    expect(result).not.toBeNull();
    expect(isDecompositionOutput(result!)).toBe(true);
  });

  it("returns message-only error when no error key but has message", () => {
    const messageOnly = { type: "error", message: "Something failed" };
    const result = getDecomposeGoalOutput({ output: messageOnly });
    expect(result).not.toBeNull();
    // isErrorOutput requires 'error' key, so this falls through to message-only branch
    expect((result as DecomposeErrorOutput).message).toBe("Something failed");
  });
});

// ---------------------------------------------------------------------------
// getAnimationText
// ---------------------------------------------------------------------------

describe("getAnimationText", () => {
  it("shows analyzing text during input-streaming", () => {
    const text = getAnimationText({ state: "input-streaming" });
    expect(text.toLowerCase()).toContain("analyzing");
  });

  it("shows analyzing text during input-available", () => {
    const text = getAnimationText({ state: "input-available" });
    expect(text.toLowerCase()).toContain("analyzing");
  });

  it("shows plan ready with step count on output-available with decomposition", () => {
    const text = getAnimationText({
      state: "output-available",
      output: DECOMPOSITION,
    });
    expect(text).toContain("3 steps");
  });

  it("shows analyzing when output-available but output is not a decomposition", () => {
    const text = getAnimationText({
      state: "output-available",
      output: null,
    });
    expect(text.toLowerCase()).toContain("analyzing");
  });

  it("shows error text on output-error state", () => {
    const text = getAnimationText({ state: "output-error" });
    expect(text.toLowerCase()).toContain("error");
  });

  it("falls back to analyzing for unknown state", () => {
    const text = getAnimationText({ state: "result" as never });
    expect(text.toLowerCase()).toContain("analyzing");
  });
});

// ---------------------------------------------------------------------------
// computeRemainingSeconds
// ---------------------------------------------------------------------------

const DECOMPOSITION_BASE: TaskDecompositionOutput = {
  type: "task_decomposition",
  message: "Plan",
  goal: "Build agent",
  steps: [{ step_id: "s1", description: "Step 1", action: "add_block" }],
  step_count: 1,
  requires_approval: true,
  auto_approve_seconds: 60,
  created_at: new Date().toISOString(),
};

describe("computeRemainingSeconds", () => {
  it("returns fallback when output is null", () => {
    expect(computeRemainingSeconds(null, 60)).toBe(60);
  });

  it("returns fallback when output is an error", () => {
    const err: DecomposeErrorOutput = { type: "error", error: "oops" };
    expect(computeRemainingSeconds(err, 60)).toBe(60);
  });

  it("returns auto_approve_seconds when created_at is missing", () => {
    const noTimestamp = { ...DECOMPOSITION_BASE, created_at: undefined };
    expect(computeRemainingSeconds(noTimestamp, 99)).toBe(60);
  });

  it("returns auto_approve_seconds when created_at is unparseable", () => {
    const badTimestamp = { ...DECOMPOSITION_BASE, created_at: "not-a-date" };
    expect(computeRemainingSeconds(badTimestamp, 99)).toBe(60);
  });

  it("returns correct remaining seconds for a recent timestamp", () => {
    vi.useFakeTimers();
    const now = new Date("2026-01-01T00:00:30Z");
    vi.setSystemTime(now);
    const output = {
      ...DECOMPOSITION_BASE,
      created_at: "2026-01-01T00:00:00Z",
    };
    // 30s elapsed → 60 - 30 = 30
    expect(computeRemainingSeconds(output, 60)).toBe(30);
    vi.useRealTimers();
  });

  it("clamps to 0 when deadline has passed", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:02:00Z"));
    const output = {
      ...DECOMPOSITION_BASE,
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(computeRemainingSeconds(output, 60)).toBe(0);
    vi.useRealTimers();
  });

  it("clamps to total when client clock is ahead (future timestamp)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    const output = {
      ...DECOMPOSITION_BASE,
      created_at: "2026-01-01T00:00:10Z",
    };
    // elapsed = -10 → total - (-10) = 70, clamped to 60
    expect(computeRemainingSeconds(output, 60)).toBe(60);
    vi.useRealTimers();
  });

  it("uses fallback when auto_approve_seconds is missing", () => {
    const noAutoApprove = {
      ...DECOMPOSITION_BASE,
      auto_approve_seconds: undefined,
      created_at: undefined,
    };
    expect(computeRemainingSeconds(noAutoApprove, 42)).toBe(42);
  });

  it("exports FALLBACK_COUNTDOWN_SECONDS as 60", () => {
    expect(FALLBACK_COUNTDOWN_SECONDS).toBe(60);
  });
});
