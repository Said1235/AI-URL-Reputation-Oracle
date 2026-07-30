/**
 * Example React hook for a wallet UI: shows a loading state while a new
 * link is being analyzed (can take several seconds the first time, since
 * it triggers an on-chain transaction), then exposes the decision
 * (open/warn/block) so the component can render it.
 *
 * This file is illustrative (.example.tsx suffix) — copy it into your own
 * React/Next.js project and adjust imports to match your structure.
 */
import { useCallback, useState } from "react";
import { guardExternalLink, LinkGuardDecision } from "./linkGuard";

type GuardState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "done"; decision: LinkGuardDecision }
  | { status: "error"; message: string };

export function useLinkGuard() {
  const [state, setState] = useState<GuardState>({ status: "idle" });

  const check = useCallback(async (url: string) => {
    setState({ status: "checking" });
    try {
      const decision = await guardExternalLink(url);
      setState({ status: "done", decision });
      return decision;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setState({ status: "error", message });
      throw err;
    }
  }, []);

  return { state, check };
}

/** Example component that uses the hook above. */
export function ExternalLinkButton({ url, label }: { url: string; label: string }) {
  const { state, check } = useLinkGuard();

  const handleClick = async () => {
    const decision = await check(url);
    if (decision.action === "open") {
      window.open(url, "_blank", "noopener,noreferrer");
    } else if (decision.action === "warn") {
      const proceed = window.confirm(
        `This site is flagged "${decision.report.risk_tier}" ` +
          `(trust score ${decision.report.trust_score}/100, for reference only). ` +
          `Open ${url} anyway?`,
      );
      if (proceed) window.open(url, "_blank", "noopener,noreferrer");
    } else {
      window.alert(`Blocked: ${decision.report.reason}`);
    }
  };

  return (
    <button onClick={handleClick} disabled={state.status === "checking"}>
      {state.status === "checking" ? "Analyzing link..." : label}
    </button>
  );
}
