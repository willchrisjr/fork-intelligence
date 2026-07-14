"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import {
  AlertTriangle,
  Focus,
  List,
  Minus,
  Plus,
  Search,
  StepForward,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { AnalysisShell } from "./analysis-shell";
import { api } from "@/lib/api";
import { classificationLabel, formatPercent } from "@/lib/format";
import { useWorkspaceState } from "@/lib/use-workspace-state";

const Graph = dynamic(() => import("./evolution-graph"), {
  ssr: false,
  loading: () => (
    <div className="graph-canvas graph-loading">Loading bounded graph…</div>
  ),
});

type GraphControls = {
  fit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
};

export function EvolutionPage({ analysisId }: { analysisId: string }) {
  const { state, update } = useWorkspaceState();
  const [controls, setControls] = useState<GraphControls>();
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: ({ signal }) => api.getAnalysis(analysisId, signal),
  });
  const queryParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("mode", state.graphMode);
    params.set("color_by", state.graphColor);
    params.set("size_by", state.graphSize);
    if (state.graphSearch) params.set("q", state.graphSearch);
    if (!state.lowSignal) params.set("hide_low_signal", "true");
    params.set("limit", "180");
    return params;
  }, [
    state.graphColor,
    state.graphMode,
    state.graphSearch,
    state.graphSize,
    state.lowSignal,
  ]);
  const graph = useQuery({
    queryKey: ["evolution", analysisId, queryParams.toString()],
    queryFn: ({ signal }) => api.getEvolution(analysisId, queryParams, signal),
    enabled: Boolean(analysis.data),
  });
  const select = useCallback(
    (id: string) => update({ evidence: id }, true),
    [update],
  );
  const ready = useCallback((value: GraphControls) => setControls(value), []);
  if (!analysis.data)
    return (
      <main id="main-content" className="state-panel">
        <p>Loading evolution workspace…</p>
      </main>
    );
  return (
    <AnalysisShell analysis={analysis.data}>
      <main className="workspace" id="main-content">
        <div className="workspace-main evolution-page">
          <header className="page-heading">
            <div>
              <h1>Repository evolution</h1>
              <p>
                Bounded lineage and development-cluster views. Every visible
                conclusion is available in the table.
              </p>
            </div>
            {graph.data?.bounded ? (
              <span className="limit-note">
                <AlertTriangle size={14} />
                Showing {graph.data.displayedNodes} of {graph.data.totalNodes}
              </span>
            ) : null}
          </header>
          <div className="graph-command-bar">
            <div className="segmented" aria-label="Graph mode">
              {(["lineage", "cluster"] as const).map((mode) => (
                <button
                  key={mode}
                  aria-pressed={state.graphMode === mode}
                  onClick={() => update({ graphMode: mode }, true)}
                >
                  {mode}
                </button>
              ))}
            </div>
            <div className="command-search">
              <Search size={15} />
              <label className="sr-only" htmlFor="graph-search">
                Search graph repositories
              </label>
              <input
                id="graph-search"
                className="field"
                placeholder="Search repositories"
                value={state.graphSearch}
                onChange={(event) =>
                  update({ graphSearch: event.target.value })
                }
              />
            </div>
            <label>
              <span className="sr-only">Color nodes by</span>
              <select
                className="select"
                value={state.graphColor}
                onChange={(event) =>
                  update(
                    {
                      graphColor: event.target.value as typeof state.graphColor,
                    },
                    true,
                  )
                }
              >
                <option value="classification">Color: classification</option>
                <option value="cluster">Color: cluster</option>
              </select>
            </label>
            <label>
              <span className="sr-only">Size nodes by</span>
              <select
                className="select"
                value={state.graphSize}
                onChange={(event) =>
                  update(
                    { graphSize: event.target.value as typeof state.graphSize },
                    true,
                  )
                }
              >
                <option value="confidence">Size: confidence</option>
                <option value="original_work">Size: original work</option>
                <option value="activity">Size: activity</option>
              </select>
            </label>
          </div>
          {graph.isError ? (
            <div className="state-panel">
              <div>
                <AlertTriangle size={34} />
                <h2>Evolution data unavailable</h2>
                <p>
                  The graph endpoint did not return data. No inferred
                  relationships are shown.
                </p>
                <button className="button" onClick={() => graph.refetch()}>
                  Try again
                </button>
              </div>
            </div>
          ) : graph.data ? (
            <div className="graph-workspace">
              <section className="graph-panel" aria-label="Evolution graph">
                <div className="graph-controls">
                  <button
                    onClick={() => controls?.zoomIn()}
                    aria-label="Zoom in"
                  >
                    <Plus />
                  </button>
                  <button
                    onClick={() => controls?.zoomOut()}
                    aria-label="Zoom out"
                  >
                    <Minus />
                  </button>
                  <button
                    onClick={() => controls?.fit()}
                    aria-label="Reset graph view"
                  >
                    <Focus />
                  </button>
                  <button
                    onClick={() => {
                      const nodes = graph.data?.nodes ?? [];
                      const index = Math.max(
                        -1,
                        nodes.findIndex((node) => node.id === state.evidence),
                      );
                      select(nodes[(index + 1) % nodes.length]?.id ?? "");
                    }}
                    aria-label="Step to next repository"
                  >
                    <StepForward />
                  </button>
                </div>
                <Graph
                  graph={graph.data}
                  mode={state.graphMode}
                  colorBy={state.graphColor}
                  sizeBy={state.graphSize}
                  selectedId={state.evidence}
                  onSelect={select}
                  onReady={ready}
                />
              </section>
              <section className="graph-table-panel">
                <h2>
                  <List size={17} />
                  Accessible repository table
                </h2>
                <div className="table-scroll">
                  <table className="graph-table">
                    <thead>
                      <tr>
                        <th>Repository</th>
                        <th>Classification</th>
                        <th>Confidence</th>
                        <th>Original work</th>
                      </tr>
                    </thead>
                    <tbody>
                      {graph.data.nodes.map((node) => (
                        <tr
                          key={node.id}
                          className={
                            node.id === state.evidence ? "selected" : ""
                          }
                        >
                          <td>
                            <button onClick={() => select(node.id)}>
                              {node.label}
                            </button>
                          </td>
                          <td>{classificationLabel(node.classification)}</td>
                          <td>{node.confidence.toFixed(2)}</td>
                          <td>{formatPercent(node.originalWorkPercent, 1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          ) : (
            <div className="graph-canvas graph-loading">
              Loading bounded graph…
            </div>
          )}
        </div>
      </main>
    </AnalysisShell>
  );
}
