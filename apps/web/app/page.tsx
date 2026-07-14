import { ArrowRight, GitBranch, LockKeyhole, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { Brand } from "@/components/brand";
import { LineagePreview } from "@/components/lineage-preview";
import { RepositoryForm } from "@/components/repository-form";
import { ThemeToggle } from "@/components/theme-toggle";

export default function LandingPage() {
  return (
    <>
      <header className="landing-header">
        <div className="landing-header-inner">
          <Brand />
          <nav className="landing-actions" aria-label="Primary">
            <Link href="/methodology">Methodology</Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>
      <main className="landing-main" id="main-content">
        <section className="landing-hero">
          <div className="landing-copy">
            <h1>Find the forks that actually matter.</h1>
            <p className="landing-lede">
              Analyze a public GitHub repository to uncover maintained
              successors, original development, and useful work outside
              upstream.
            </p>
            <RepositoryForm />
            <p className="security-note">
              <LockKeyhole aria-hidden="true" size={18} />
              Public repositories only. Repository code is inspected, never
              executed.
            </p>
          </div>
          <LineagePreview />
        </section>
        <section
          className="landing-bottom"
          aria-label="Security and methodology"
        >
          <article>
            <ShieldCheck aria-hidden="true" size={54} strokeWidth={1.7} />
            <div>
              <h2>Security</h2>
              <p>We analyze public repository data using read-only access.</p>
              <ul className="check-list">
                <li>No repository code is executed</li>
                <li>No changes are made to repositories</li>
                <li>Credentials stay server-side</li>
                <li>Sampling and limits are disclosed</li>
              </ul>
              <Link className="text-link" href="/methodology#security">
                Learn more about security{" "}
                <ArrowRight aria-hidden="true" size={15} />
              </Link>
            </div>
          </article>
          <article id="methodology-summary">
            <GitBranch aria-hidden="true" size={54} strokeWidth={1.7} />
            <div>
              <h2>Methodology</h2>
              <p>
                Multiple independent signals surface forks that provide real
                value beyond the upstream repository.
              </p>
              <ul className="check-list">
                <li>Code lineage and commit relationships</li>
                <li>Development activity and maintenance signals</li>
                <li>Original contributions and unmerged changes</li>
                <li>Transparent, explainable analysis</li>
              </ul>
              <Link className="text-link" href="/methodology">
                Learn about our methodology{" "}
                <ArrowRight aria-hidden="true" size={15} />
              </Link>
            </div>
          </article>
        </section>
      </main>
    </>
  );
}
