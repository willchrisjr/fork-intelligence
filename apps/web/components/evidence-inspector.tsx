"use client";

import { AlertTriangle, ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { Confidence } from "./confidence";
import {
  classificationLabel,
  formatDateTime,
  formatPercent,
} from "@/lib/format";
import type { ForkDetail } from "@/lib/types";

export function EvidenceInspector({
  detail,
  isLoading,
  onClose,
  analysisId,
}: {
  detail?: ForkDetail;
  isLoading: boolean;
  onClose: () => void;
  analysisId: string;
}) {
  return (
    <aside
      className="inspector"
      aria-label="Evidence inspector"
      aria-live="polite"
    >
      <div className="inspector-header">
        <h2>Evidence</h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close evidence inspector"
        >
          <X size={18} />
        </button>
      </div>
      {isLoading ? (
        <div className="inspector-body" aria-label="Loading evidence">
          <div className="skeleton" style={{ width: "72%", height: 20 }} />
          <div
            className="skeleton"
            style={{ width: "100%", height: 120, marginTop: 20 }}
          />
        </div>
      ) : detail ? (
        <div className="inspector-body">
          <a
            className="inspector-title"
            href={detail.url}
            target="_blank"
            rel="noreferrer"
          >
            {detail.fullName} <ExternalLink aria-hidden="true" size={13} />
          </a>
          <dl className="detail-list">
            <div>
              <dt>Classification</dt>
              <dd>{classificationLabel(detail.classification)}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>
                <Confidence value={detail.confidence} />
              </dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd>{formatPercent(detail.dataCoverage)}</dd>
            </div>
            <div>
              <dt>Depth</dt>
              <dd>{detail.analysisDepth}</dd>
            </div>
          </dl>
          <div
            className="inspector-tabs"
            role="tablist"
            aria-label="Evidence sections"
          >
            <button role="tab" aria-selected="true">
              Summary
            </button>
            <button role="tab" aria-selected="false">
              Commits
            </button>
            <button role="tab" aria-selected="false">
              Patches
            </button>
            <button role="tab" aria-selected="false">
              Files
            </button>
          </div>
          <section className="inspector-section">
            <h3>Classification reasons</h3>
            <ul className="reason-list">
              {detail.classificationReasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </section>
          <section className="inspector-section">
            <h3>Score inputs</h3>
            <table className="score-table">
              <thead>
                <tr>
                  <th>Factor</th>
                  <th>Value</th>
                  <th>Weight</th>
                </tr>
              </thead>
              <tbody>
                {detail.scoreComponents.map((component) => (
                  <tr key={component.key}>
                    <td>{component.label}</td>
                    <td>
                      {component.missing
                        ? "Missing"
                        : String(component.value ?? "—")}
                    </td>
                    <td>
                      {component.weight == null
                        ? "—"
                        : component.weight.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {detail.missingData.length ? (
            <section className="inspector-section">
              <h3>Missing data</h3>
              <ul className="missing-list">
                {detail.missingData.map((item) => (
                  <li key={item}>
                    <AlertTriangle size={14} />
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          <section className="inspector-section">
            <h3>Evidence records</h3>
            <ul className="evidence-list">
              {detail.evidence.slice(0, 6).map((item) => (
                <li key={item.id}>
                  <strong>{item.title}</strong>
                  <span>{item.summary}</span>
                  <small>
                    {item.provenance} · {formatDateTime(item.retrievedAt)}
                  </small>
                  {item.sourceUrl ? (
                    <a href={item.sourceUrl} target="_blank" rel="noreferrer">
                      Open source <ExternalLink size={12} />
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
            <Link
              className="text-link"
              href={`/analyses/${encodeURIComponent(analysisId)}/forks/${encodeURIComponent(detail.id)}`}
            >
              Open full fork details
            </Link>
          </section>
        </div>
      ) : (
        <div className="inspector-body">
          <p className="muted">Select a fork to inspect its evidence.</p>
        </div>
      )}
    </aside>
  );
}
