export function LineagePreview() {
  return (
    <figure className="lineage-preview" aria-labelledby="lineage-title">
      <h2 id="lineage-title">Fork lineage</h2>
      <div className="lineage-legend" aria-hidden="true">
        <span>
          <i className="status-dot" style={{ background: "#0b57e3" }} />
          Upstream
        </span>
        <span>
          <i className="status-dot good" />
          Maintained
        </span>
        <span>
          <i className="status-dot warning" />
          Uncertain
        </span>
        <span>
          <i className="status-dot" />
          Inactive
        </span>
      </div>
      <div className="lineage-graphic" aria-hidden="true">
        <svg
          className="lineage-svg"
          viewBox="0 0 680 330"
          preserveAspectRatio="none"
        >
          <path
            d="M30 167H177C222 167 222 32 268 32H510"
            fill="none"
            stroke="#078a7b"
            strokeWidth="2"
          />
          <path
            d="M30 167H177C222 167 222 105 268 105H510"
            fill="none"
            stroke="#078a7b"
            strokeWidth="2"
          />
          <path
            d="M30 167H510"
            fill="none"
            stroke="#d97706"
            strokeWidth="2"
            strokeDasharray="9 7"
          />
          <path
            d="M30 167H177C222 167 222 235 268 235H510"
            fill="none"
            stroke="#7d8898"
            strokeWidth="2"
          />
          <path
            d="M30 167H177C222 167 222 304 268 304H510"
            fill="none"
            stroke="#7d8898"
            strokeWidth="2"
          />
          {[30, 90, 150].map((x) => (
            <circle key={`u${x}`} cx={x} cy="167" r="7" fill="#0b57e3" />
          ))}
          {[268, 330, 392, 454, 510].map((x) => (
            <circle key={`a${x}`} cx={x} cy="32" r="6" fill="#078a7b" />
          ))}
          {[268, 330, 392, 454, 510].map((x) => (
            <circle key={`b${x}`} cx={x} cy="105" r="6" fill="#078a7b" />
          ))}
          {[268, 330, 392, 454, 510].map((x) => (
            <circle key={`c${x}`} cx={x} cy="167" r="6" fill="#d97706" />
          ))}
          {[268, 330, 392, 454, 510].map((x) => (
            <circle key={`d${x}`} cx={x} cy="235" r="6" fill="#7d8898" />
          ))}
          {[268, 330, 392, 454, 510].map((x) => (
            <circle key={`e${x}`} cx={x} cy="304" r="6" fill="#7d8898" />
          ))}
        </svg>
        <span className="lineage-label">
          current/project<small className="tone-good">Maintained</small>
        </span>
        <span className="lineage-label">
          team/project<small className="tone-good">Maintained</small>
        </span>
        <span className="lineage-label">
          feature/project<small className="tone-warning">Uncertain</small>
        </span>
        <span className="lineage-label">
          archive/project<small>Inactive</small>
        </span>
      </div>
      <figcaption className="sr-only">
        Illustrative lineage: one upstream project branches into maintained,
        uncertain, and inactive forks.
      </figcaption>
    </figure>
  );
}
