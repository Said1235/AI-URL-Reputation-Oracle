/**
 * Use case: BLOCKCHAIN EXPLORERS
 * --------------------------------
 * "Explorers: show a trust badge next to a contract's or project's URL."
 * (original spec, Use cases section).
 *
 * Read-only component: it never triggers transactions, it only reads the
 * latest available report via `get_report`. If the URL was never
 * analyzed, it shows a neutral state instead of triggering an on-chain
 * analysis from a public explorer page (that could be abused to spend the
 * explorer's wallet gas on random URLs). To force a first analysis,
 * expose a separate button that explicitly calls analyze().
 *
 * Usage:
 *   <TrustBadge url="https://uniswap.org" />
 */
import { useEffect, useState } from "react";
import { createReadClient } from "../shared/genlayerClient";
import { getReport, UrlReport } from "../shared/oracleClient";
import { CONTRACT_ADDRESS } from "../shared/config";

interface TrustBadgeProps {
  url: string;
}

type BadgeTier = "not_analyzed" | "danger" | "warning" | "safe";

const BADGE_STYLES: Record<BadgeTier, { background: string; label: string }> = {
  not_analyzed: { background: "#9CA3AF", label: "Not analyzed" },
  danger: { background: "#DC2626", label: "Risk" },
  warning: { background: "#D97706", label: "Caution" },
  safe: { background: "#16A34A", label: "Trusted" },
};

function classify(report: UrlReport): BadgeTier {
  if (report.status === "not_analyzed") return "not_analyzed";
  // Key off `risk_tier` alone. It's the field consensus actually gates
  // on (validators had to land in the exact same bucket as the leader),
  // so it's the only field safe to branch a decision on. `trust_score`
  // is shown below for reference but must never drive a decision itself.
  if (report.risk_tier === "high_risk") return "danger";
  if (report.risk_tier === "caution") return "warning";
  return "safe";
}

export function TrustBadge({ url }: TrustBadgeProps) {
  const [report, setReport] = useState<UrlReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const readClient = createReadClient();
    getReport(readClient, CONTRACT_ADDRESS, url)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((err) => {
        console.error(`TrustBadge: failed to load report for ${url}`, err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  if (loading) {
    return <span style={{ opacity: 0.5, fontSize: 12 }}>Loading reputation...</span>;
  }
  if (!report) return null;

  const tier = classify(report);
  const style = BADGE_STYLES[tier];

  return (
    <span
      title={
        report.status === "not_analyzed"
          ? "This URL has not been analyzed by the oracle yet"
          : report.reason
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        color: "white",
        backgroundColor: style.background,
      }}
    >
      {style.label}
      {report.status === "completed" && ` \u00b7 ${report.trust_score}/100`}
    </span>
  );
}
