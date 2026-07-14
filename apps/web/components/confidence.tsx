import { confidenceBand, formatConfidence } from "@/lib/format";

export function Confidence({
  value,
  showLabel = true,
}: {
  value: number;
  showLabel?: boolean;
}) {
  const band = confidenceBand(value);
  return (
    <div
      className="confidence-bar"
      aria-label={`${formatConfidence(value)} ${band} confidence`}
    >
      <div className="confidence-track" aria-hidden="true">
        <span
          className={`confidence-fill ${band}`}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      {showLabel ? (
        <span className="mono">{formatConfidence(value)}</span>
      ) : null}
    </div>
  );
}
