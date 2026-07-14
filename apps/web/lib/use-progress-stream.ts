"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { AnalysisSummary, ProgressEvent } from "./types";

type ConnectionState =
  "connecting" | "live" | "reconnecting" | "closed" | "error";

export function useProgressStream(
  analysisId: string,
  initial?: AnalysisSummary,
): {
  analysis?: AnalysisSummary;
  connection: ConnectionState;
  lastEventId?: string;
  message?: string;
} {
  const analysis = initial;
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [lastEventId, setLastEventId] = useState<string>();
  const [message, setMessage] = useState<string>();
  const queryClient = useQueryClient();
  useEffect(() => {
    const source = new EventSource(api.progressUrl(analysisId));
    const handleEvent = (raw: MessageEvent<string>) => {
      try {
        const event = JSON.parse(raw.data) as ProgressEvent & {
          payload?: { message?: string };
        };
        setLastEventId(raw.lastEventId || undefined);
        if (event.message ?? event.payload?.message)
          setMessage(event.message ?? event.payload?.message);
        void queryClient.invalidateQueries({
          queryKey: ["analysis", analysisId],
        });
        void queryClient.invalidateQueries({ queryKey: ["forks", analysisId] });
        void queryClient.invalidateQueries({
          queryKey: ["clusters", analysisId],
        });
        void queryClient.invalidateQueries({
          queryKey: ["evolution", analysisId],
        });
        if (
          [
            "analysis.completed",
            "analysis.failed",
            "analysis.cancelled",
          ].includes(event.type)
        ) {
          setConnection("closed");
          source.close();
        }
      } catch {
        setMessage(
          "A progress update could not be read. Existing results remain available.",
        );
      }
    };
    source.onopen = () => setConnection("live");
    source.onerror = () =>
      setConnection(
        source.readyState === EventSource.CLOSED ? "error" : "reconnecting",
      );
    source.onmessage = handleEvent;
    for (const type of [
      "analysis.queued",
      "analysis.started",
      "analysis.completed",
      "analysis.cancelled",
      "analysis.failed",
      "analysis.cancel_requested",
      "analysis.resume_queued",
      "stage.started",
      "stage.completed",
      "census.page_persisted",
      "structural.repository_persisted",
      "structural.repository_failed",
    ]) {
      source.addEventListener(type, handleEvent as EventListener);
    }
    return () => {
      source.close();
    };
  }, [analysisId, queryClient]);

  return { analysis, connection, lastEventId, message };
}
