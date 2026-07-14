"use client";

import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";
import type { EvolutionGraph as EvolutionGraphData } from "@/lib/types";

const THEME_EVENT = "fork-intelligence:theme-change";

function cssColor(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

export default function EvolutionGraph({
  graph,
  mode,
  colorBy,
  sizeBy,
  selectedId,
  onSelect,
  onReady,
}: {
  graph: EvolutionGraphData;
  mode: "lineage" | "cluster";
  colorBy: "classification" | "cluster";
  sizeBy: "confidence" | "original_work" | "activity";
  selectedId?: string;
  onSelect: (id: string) => void;
  onReady: (controls: {
    fit: () => void;
    zoomIn: () => void;
    zoomOut: () => void;
  }) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<cytoscape.Core | undefined>(undefined);
  const [themeVersion, setThemeVersion] = useState(0);

  useEffect(() => {
    const refreshTheme = () => setThemeVersion((version) => version + 1);
    window.addEventListener(THEME_EVENT, refreshTheme);
    return () => window.removeEventListener(THEME_EVENT, refreshTheme);
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const classColors: Record<string, string> = {
      mirror: cssColor("--muted"),
      contribution: cssColor("--cobalt"),
      experimental: cssColor("--amber"),
      specialized: cssColor("--violet"),
      compatibility_patch: "#ef8b4b",
      maintained_continuation: cssColor("--teal"),
      independent_direction: "#53a8df",
      unknown: cssColor("--muted"),
    };
    const clusterColors = new Map<string, string>();
    const palette = [
      cssColor("--cobalt"),
      cssColor("--teal"),
      cssColor("--violet"),
      cssColor("--amber"),
      "#53a8df",
      "#e865a3",
    ];
    const colorFor = (node: EvolutionGraphData["nodes"][number]) => {
      if (colorBy === "classification")
        return classColors[node.classification] ?? classColors.unknown;
      if (!node.clusterId) return classColors.unknown;
      if (!clusterColors.has(node.clusterId))
        clusterColors.set(
          node.clusterId,
          palette[clusterColors.size % palette.length],
        );
      return clusterColors.get(node.clusterId)!;
    };
    const sizeFor = (node: EvolutionGraphData["nodes"][number]) => {
      const raw =
        sizeBy === "confidence"
          ? node.confidence * 100
          : sizeBy === "original_work"
            ? (node.originalWorkPercent ?? 0)
            : (node.activity30d ?? 0);
      return Math.max(26, Math.min(58, 26 + raw * 0.32));
    };
    const instance = cytoscape({
      container: containerRef.current,
      elements: [
        ...graph.nodes.map((node) => ({
          data: { ...node, color: colorFor(node), size: sizeFor(node) },
        })),
        ...graph.edges.map((edge) => ({ data: edge })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            width: "data(size)",
            height: "data(size)",
            label: "data(label)",
            color: cssColor("--ink"),
            "font-family": "Inter, sans-serif",
            "font-size": 10,
            "text-wrap": "ellipsis",
            "text-max-width": "110px",
            "text-valign": "bottom",
            "text-margin-y": 8,
            "overlay-opacity": 0,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": cssColor("--line-strong"),
            "target-arrow-color": cssColor("--line-strong"),
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.7,
          },
        },
        {
          selector: "edge[kind = 'similarity']",
          style: {
            "line-style": "dashed",
            "line-color": cssColor("--violet"),
            "target-arrow-shape": "none",
          },
        },
        {
          selector: ":selected",
          style: {
            "border-color": cssColor("--ink"),
            "border-width": 4,
            "border-opacity": 1,
          },
        },
      ],
      layout:
        mode === "lineage"
          ? {
              name: "breadthfirst",
              directed: true,
              spacingFactor: 1.5,
              padding: 35,
            }
          : { name: "concentric", minNodeSpacing: 65, padding: 35 },
      minZoom: 0.35,
      maxZoom: 2.5,
    });
    instance.on("tap", "node", (event) => onSelect(event.target.id()));
    instance.on("tap", (event) => {
      if (event.target === instance) instance.elements().unselect();
    });
    instanceRef.current = instance;
    onReady({
      fit: () => instance.fit(undefined, 35),
      zoomIn: () =>
        instance.zoom({
          level: Math.min(instance.zoom() * 1.25, 2.5),
          renderedPosition: {
            x: instance.width() / 2,
            y: instance.height() / 2,
          },
        }),
      zoomOut: () =>
        instance.zoom({
          level: Math.max(instance.zoom() / 1.25, 0.35),
          renderedPosition: {
            x: instance.width() / 2,
            y: instance.height() / 2,
          },
        }),
    });
    return () => {
      instance.destroy();
      instanceRef.current = undefined;
    };
  }, [colorBy, graph, mode, onReady, onSelect, sizeBy, themeVersion]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance) return;
    instance.elements().unselect();
    if (selectedId) {
      const node = instance.getElementById(selectedId);
      node.select();
      instance.animate({
        center: { eles: node },
        duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? 0
          : 180,
      });
    }
  }, [selectedId]);

  return (
    <div
      className="graph-canvas"
      ref={containerRef}
      role="img"
      aria-label={`Interactive ${mode} graph with ${graph.displayedNodes} displayed repositories. Use the synchronized table for keyboard access.`}
    />
  );
}
