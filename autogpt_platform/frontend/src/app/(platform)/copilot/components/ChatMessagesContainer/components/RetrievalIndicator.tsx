import { ScaleLoader } from "../../ScaleLoader/ScaleLoader";

interface Props {
  /** Whether the retrieval timeout has fired — switches copy + tone to error. */
  failed?: boolean;
}

/**
 * Replaces the generic "Thinking…" bubble when the user switches to a chat
 * whose backend stream is still active and the client is fetching the
 * replay. Distinct from the thinking state because the model isn't actually
 * deliberating; the wait is just network latency. After the retrieval
 * timeout expires the same slot flips to a destructive-toned inline
 * error directing the user to reload.
 */
export function RetrievalIndicator({ failed }: Props) {
  if (failed) {
    return (
      <span
        role="alert"
        className="inline-flex items-center gap-1.5 text-red-600"
      >
        <span>
          Failed to retrieve latest conversation. Please reload the page.
        </span>
      </span>
    );
  }
  return (
    <span
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-1.5 text-neutral-500"
    >
      <ScaleLoader size={16} />
      <span className="animate-pulse [animation-duration:1.5s]">
        Retrieving your conversation…
      </span>
    </span>
  );
}
