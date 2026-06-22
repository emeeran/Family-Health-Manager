import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { streamRequest } from "@/lib/api-client";
import type { GeneratedInsight, InsightMode } from "@/lib/api/members";

/**
 * Streaming insight generation, shared by {@link InsightCard} (inline generate)
 * and the full-screen {@link InsightReport} viewer (Regenerate button).
 *
 * Streams from `POST /members/:id/generate-insights/stream?mode=…` and exposes
 * the live stage/tokens so callers can render a progress preview, plus the
 * final {@link GeneratedInsight} via `onComplete`.
 */
export interface UseInsightStreamOptions {
  /** Called once when the server signals completion with the assembled insight. */
  onComplete?: (insight: GeneratedInsight) => void;
}

export interface UseInsightStreamResult {
  loading: boolean;
  /** Full text accumulated so far (empty until the first token). */
  streamText: string;
  /** Human-readable stage label ("Preparing…", "Generating via …", …). */
  streamStage: string;
  error: string | null;
  /** Begin streaming. `mode` defaults to the last value chosen in the UI
   *  (localStorage `insightMode`), so the report viewer honors it without the
   *  mode state having to be lifted into every caller. */
  generate: (mode?: InsightMode) => Promise<void>;
  /** Abort an in-flight stream. */
  cancel: () => void;
}

function storedMode(): InsightMode {
  try {
    return (localStorage.getItem("insightMode") as InsightMode) || "comprehensive";
  } catch {
    return "comprehensive";
  }
}

/* -------------------------------------------------------------------------- */
/* Pure event reducer — exported for unit testing (no React needed).           */
/* -------------------------------------------------------------------------- */

export interface StreamState {
  fullText: string;
}

export type StreamEventUpdate =
  | { type: "idle" }
  | { type: "stage"; stage: string }
  | { type: "token"; fullText: string }
  | { type: "complete"; insight: GeneratedInsight }
  | { type: "error"; message: string };

/**
 * Map one server-sent event to a state update, given the text accumulated so
 * far. Pure and deterministic (the completion timestamp is taken from `now`),
 * so it can be exercised directly by `use-insight-stream.test.ts`.
 */
export function applyStreamEvent(
  event: Record<string, unknown>,
  prev: StreamState,
  now: Date
): StreamEventUpdate {
  const stage = (event.stage as string) ?? "";
  switch (stage) {
    case "context":
      return { type: "stage", stage: (event.message as string) || "Preparing..." };
    case "provider":
      return { type: "stage", stage: `Generating via ${event.provider}...` };
    case "token": {
      const fullText = prev.fullText + ((event.content as string) ?? "");
      return { type: "token", fullText };
    }
    case "complete":
      return {
        type: "complete",
        insight: {
          id: (event.insight_id as string) ?? "",
          response: prev.fullText,
          provider_used: (event.provider as string) ?? "",
          generated_at: now.toISOString(),
          verification: null,
          sections: (event.sections as GeneratedInsight["sections"]) ?? null,
        },
      };
    case "error":
      return { type: "error", message: (event.message as string) || "Generation failed" };
    default:
      return { type: "idle" };
  }
}

/* -------------------------------------------------------------------------- */
/* Hook                                                                        */
/* -------------------------------------------------------------------------- */

export function useInsightStream(
  memberId: string,
  opts?: UseInsightStreamOptions
): UseInsightStreamResult {
  const [loading, setLoading] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamStage, setStreamStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  // Keep the latest onComplete without forcing `generate` to change identity.
  const onCompleteRef = useRef(opts?.onComplete);
  onCompleteRef.current = opts?.onComplete;

  const generate = useCallback(
    async (mode?: InsightMode) => {
      const useMode = mode ?? storedMode();
      setLoading(true);
      setError(null);
      setStreamText("");
      setStreamStage("Starting...");
      let fullText = "";
      try {
        const { promise, cancel } = streamRequest(
          `/members/${memberId}/generate-insights/stream?mode=${useMode}`,
          {
            onEvent: (event) => {
              const update = applyStreamEvent(event, { fullText }, new Date());
              switch (update.type) {
                case "stage":
                  setStreamStage(update.stage);
                  break;
                case "token":
                  fullText = update.fullText;
                  setStreamText(fullText);
                  break;
                case "complete":
                  setStreamStage("");
                  onCompleteRef.current?.(update.insight);
                  break;
                case "error":
                  toast.error(update.message);
                  break;
              }
            },
          }
        );
        cancelRef.current = cancel;
        await promise;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to generate insights");
      } finally {
        setLoading(false);
        setStreamStage("");
        cancelRef.current = null;
      }
    },
    [memberId]
  );

  const cancel = useCallback(() => {
    cancelRef.current?.();
  }, []);

  return { loading, streamText, streamStage, error, generate, cancel };
}
