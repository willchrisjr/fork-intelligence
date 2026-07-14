import {
  AlertTriangle,
  ArrowLeft,
  Binary,
  GitCompareArrows,
  LockKeyhole,
  Scale,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { Brand } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";

const stages = [
  [
    "01",
    "Resolve",
    "Validate the GitHub identifier and establish requested, parent, and root repositories.",
  ],
  [
    "02",
    "Census",
    "Collect broad public metadata with pagination, checkpoints, quota tracking, and visible caps.",
  ],
  [
    "03",
    "Shortlist",
    "Prioritize likely meaningful forks using low-cost signals; metadata-only forks remain labeled.",
  ],
  [
    "04",
    "Analyze",
    "Inspect commit ancestry, unique commits, stable patches, files, and dependency changes without executing code.",
  ],
  [
    "05",
    "Explain",
    "Calculate versioned dimensions, confidence, classifications, and deterministic clusters linked to evidence.",
  ],
];

export default function MethodologyPage() {
  return (
    <>
      <header className="method-header">
        <Brand />
        <div className="method-actions">
          <ThemeToggle />
          <Link className="button" href="/">
            <ArrowLeft size={15} />
            Analyze a repository
          </Link>
        </div>
      </header>
      <main className="methodology" id="main-content">
        <header className="method-hero">
          <h1>Evidence first. Interpretation second.</h1>
          <p>
            Fork Intelligence separates directly observed data, deterministic
            Git calculations, heuristic classifications, and optional
            evidence-grounded AI language. It shows uncertainty instead of
            hiding it.
          </p>
        </header>
        <nav className="method-nav" aria-label="On this page">
          <a href="#stages">Stages</a>
          <a href="#scores">Scores</a>
          <a href="#patches">Patch equivalence</a>
          <a href="#confidence">Confidence</a>
          <a href="#security">Security</a>
          <a href="#limits">Limitations</a>
        </nav>
        <section className="method-section" id="stages">
          <div className="method-intro">
            <span>How it works</span>
            <h2>Progressive analysis stages</h2>
            <p>
              Broad, low-cost evidence arrives first. Expensive structural
              analysis is bounded and prioritized, so users can inspect honest
              partial results without waiting for the entire network.
            </p>
          </div>
          <ol className="method-stages">
            {stages.map(([number, title, description]) => (
              <li key={number}>
                <span>{number}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{description}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
        <section className="method-section split" id="scores">
          <div className="method-intro">
            <span>Separate dimensions</span>
            <h2>No universal “best fork” score</h2>
            <p>
              Popularity, activity, maintenance, original work, divergence,
              adoption, compatibility, successor likelihood, and unmerged
              innovation answer different questions.
            </p>
          </div>
          <div className="method-detail">
            <Scale size={36} />
            <h3>Named ranking profiles</h3>
            <p>
              Profiles combine visible, versioned inputs for a specific intent.
              The workspace shows raw values, normalized values, weights,
              missing inputs, calculation version, and analysis depth.
            </p>
            <div className="formula mono">
              profile = Σ(normalized input × visible weight)
            </div>
            <p className="muted">
              High divergence describes distance from upstream; it does not
              imply quality. Popularity remains separate from technical merit.
            </p>
          </div>
        </section>
        <section className="method-section split" id="patches">
          <div className="method-intro">
            <span>Deterministic equivalence</span>
            <h2>Same commit is not the only kind of overlap</h2>
            <p>
              Rebases and cherry-picks change commit identifiers. Stable patch
              fingerprints help identify equivalent changes while preserving the
              underlying evidence.
            </p>
          </div>
          <div className="method-detail">
            <GitCompareArrows size={36} />
            <ul className="definition-list">
              <li>
                <strong>Same commit</strong>
                <span>Identical commit object.</span>
              </li>
              <li>
                <strong>Equivalent patch</strong>
                <span>Deterministic normalized patch fingerprint.</span>
              </li>
              <li>
                <strong>Similar implementation</strong>
                <span>
                  Shared changed areas or highly similar diff; never presented
                  as proven semantic equivalence.
                </span>
              </li>
              <li>
                <strong>Unknown</strong>
                <span>Insufficient history or unavailable evidence.</span>
              </li>
            </ul>
          </div>
        </section>
        <section className="method-section split" id="confidence">
          <div className="method-intro">
            <span>Uncertainty</span>
            <h2>Confidence and coverage travel with every claim</h2>
            <p>
              A score can be high while its evidence coverage is low. These are
              shown separately, with missing inputs and analysis depth.
            </p>
          </div>
          <div className="method-detail">
            <Binary size={36} />
            <div className="confidence-example">
              <span>0.92 · high confidence</span>
              <i>
                <b style={{ width: "92%" }} />
              </i>
              <small>
                Structural evidence, recent metadata, and score inputs available
              </small>
            </div>
            <div className="confidence-example warning">
              <span>0.48 · limited confidence</span>
              <i>
                <b style={{ width: "48%" }} />
              </i>
              <small>
                Metadata only; release and patch evidence unavailable
              </small>
            </div>
          </div>
        </section>
        <section className="method-section split" id="security">
          <div className="method-intro">
            <span>Hostile inputs</span>
            <h2>Repository code is data, never instructions</h2>
            <p>
              Public repositories can contain malicious hooks, filenames,
              configuration, prompts, and content. The analysis boundary treats
              all of it as untrusted.
            </p>
          </div>
          <div className="method-detail">
            <ShieldCheck size={36} />
            <ul className="definition-list">
              <li>
                <strong>No execution</strong>
                <span>
                  No repository builds, tests, scripts, package managers,
                  binaries, or hooks.
                </span>
              </li>
              <li>
                <strong>Restricted network</strong>
                <span>
                  Repository identifiers are normalized to supported GitHub
                  hosts; arbitrary URLs are not fetched.
                </span>
              </li>
              <li>
                <strong>Sterile Git operations</strong>
                <span>
                  Validated argument arrays, configuration isolation, timeouts,
                  and storage limits.
                </span>
              </li>
              <li>
                <strong>Credential isolation</strong>
                <span>
                  Tokens stay in the platform service and are never rendered in
                  the web app.
                </span>
              </li>
            </ul>
            <div className="banner">
              <LockKeyhole size={15} />
              Public repositories only in the MVP.
            </div>
          </div>
        </section>
        <section className="method-section split" id="limits">
          <div className="method-intro">
            <span>Known limits</span>
            <h2>What the analysis cannot prove</h2>
            <p>
              Results describe available public evidence at a specific time,
              under a specific configuration and analysis version.
            </p>
          </div>
          <div className="method-detail">
            <AlertTriangle size={36} />
            <ul className="definition-list">
              <li>
                <strong>Network visibility</strong>
                <span>
                  Deleted, private, transferred, or inaccessible forks may be
                  absent.
                </span>
              </li>
              <li>
                <strong>Sampling</strong>
                <span>
                  Large networks and branch sets may be capped. The workspace
                  and exports disclose caps.
                </span>
              </li>
              <li>
                <strong>Maintenance</strong>
                <span>
                  Activity signals do not prove code quality, intent, security,
                  or future support.
                </span>
              </li>
              <li>
                <strong>Patch identity</strong>
                <span>
                  Deterministic fingerprints do not establish broad semantic
                  equivalence.
                </span>
              </li>
              <li>
                <strong>AI language</strong>
                <span>
                  Optional labels are constrained to linked evidence; the core
                  product works without an AI key.
                </span>
              </li>
            </ul>
          </div>
        </section>
      </main>
    </>
  );
}
