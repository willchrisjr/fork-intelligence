import type { Classification, MaintenanceState } from "./types";

export function formatNumber(value: number | null | undefined): string {
  if (value == null) return "Unavailable";
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatPercent(
  value: number | null | undefined,
  digits = 0,
): string {
  if (value == null) return "Unknown";
  return `${value.toFixed(digits)}%`;
}

export function formatConfidence(value: number): string {
  return value.toFixed(2);
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unknown date";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unknown time";
  return `${new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date)} UTC`;
}

const CLASSIFICATION_LABELS: Record<Classification, string> = {
  mirror: "Mirror-like",
  contribution: "Contribution fork",
  experimental: "Experimental",
  specialized: "Specialized variant",
  compatibility_patch: "Compatibility patch",
  maintained_continuation: "Maintained continuation",
  independent_direction: "Independent direction",
  unknown: "Unknown",
};

const MAINTENANCE_LABELS: Record<MaintenanceState, string> = {
  actively_maintained: "Actively maintained",
  maintained: "Maintained",
  low_activity: "Low activity",
  inactive: "Inactive",
  unknown: "Unknown",
};

export const classificationLabel = (value: Classification) =>
  CLASSIFICATION_LABELS[value];
export const maintenanceLabel = (value: MaintenanceState) =>
  MAINTENANCE_LABELS[value];

export function confidenceBand(value: number): "high" | "medium" | "low" {
  if (value >= 0.75) return "high";
  if (value >= 0.45) return "medium";
  return "low";
}
