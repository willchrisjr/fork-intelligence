import { formatNumber } from "@/lib/format";
import type { StarGrowth } from "@/lib/types";

export function StarGrowthPanel({
  growth,
  heading = "h3",
}: {
  growth?: StarGrowth;
  heading?: "h2" | "h3";
}) {
  if (!growth) return null;
  const Heading = heading;
  const peak = Math.max(1, ...growth.weeklyCreated);
  return (
    <section
      className={heading === "h3" ? "inspector-section" : undefined}
      aria-label="Star growth"
    >
      <Heading>Star growth</Heading>
      <p className="muted star-growth-lead">
        Identity-free GitHub totals. Star velocity is an indicator, not proof of
        quality or reuse.
      </p>
      <dl className="detail-list">
        <div>
          <dt>Current stars</dt>
          <dd>{formatNumber(growth.count)}</dd>
        </div>
        <div>
          <dt>Created last 4 weeks</dt>
          <dd>{formatNumber(growth.createdLast4Weeks)}</dd>
        </div>
        <div>
          <dt>Created last 12 weeks</dt>
          <dd>{formatNumber(growth.createdLast12Weeks)}</dd>
        </div>
      </dl>
      {growth.weeklyCreated.length ? (
        <div
          className="star-sparkline"
          role="img"
          aria-label={sparklineLabel(growth)}
        >
          {growth.weeklyCreated.map((total, index) => {
            const newest = index === growth.weeklyCreated.length - 1;
            const height = total <= 0 ? 0 : Math.max(2, (total / peak) * 100);
            return (
              <span
                key={`${index}-${total}`}
                className={
                  newest ? "star-sparkline-bar is-newest" : "star-sparkline-bar"
                }
                style={{ height: `${height}%` }}
                title={
                  newest
                    ? `${total} created this week (may be incomplete)`
                    : `${total} created that week`
                }
              />
            );
          })}
        </div>
      ) : null}
      <p className="muted star-growth-note">
        Newest week may be incomplete; week boundaries are not guaranteed UTC. A
        single week can spike far above the median (about 35× in flask-class
        bursts), so the 4- and 12-week windows are the better read. These totals
        are not summed into the current count.
      </p>
    </section>
  );
}

function sparklineLabel(growth: StarGrowth): string {
  const series = growth.weeklyCreated.join(", ");
  return (
    `Weekly created stars, oldest to newest: ${series}. ` +
    "Newest week may be incomplete."
  );
}
