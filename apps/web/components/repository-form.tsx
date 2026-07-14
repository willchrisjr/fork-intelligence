"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  GitCompareArrows,
  Github,
  Network,
  Route,
  Zap,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AnalysisMode } from "@/lib/types";

const modes: Array<{
  value: AnalysisMode;
  label: string;
  Icon: typeof Network;
}> = [
  { value: "explore", label: "Explore ecosystem", Icon: Network },
  { value: "successor", label: "Find maintained successor", Icon: Route },
  { value: "innovation", label: "Find unmerged innovation", Icon: Zap },
  { value: "compare", label: "Compare forks", Icon: GitCompareArrows },
];

const repositoryPattern =
  /^(?:https:\/\/github\.com\/)?[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/;

export function RepositoryForm() {
  const router = useRouter();
  const [repository, setRepository] = useState("");
  const [mode, setMode] = useState<AnalysisMode>("explore");
  const [validationError, setValidationError] = useState<string>();
  const mutation = useMutation({
    mutationFn: () =>
      api.createAnalysis(repository.trim().replace(/\/$/, ""), mode),
    onSuccess: (analysis) =>
      router.push(`/analyses/${encodeURIComponent(analysis.id)}`),
  });

  const submit = () => {
    mutation.reset();
    if (!repositoryPattern.test(repository.trim())) {
      setValidationError(
        "Enter owner/repository or a public github.com repository URL.",
      );
      return;
    }
    setValidationError(undefined);
    mutation.mutate();
  };

  const requestError = mutation.error
    ? mutation.error instanceof ApiError
      ? mutation.error.payload.message
      : "The analysis could not be started. Check the API connection and try again."
    : undefined;

  return (
    <div>
      <form
        className="repo-form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="repo-input-wrap">
          <Github aria-hidden="true" size={25} />
          <label className="sr-only" htmlFor="repository">
            GitHub repository
          </label>
          <input
            className="field"
            id="repository"
            autoComplete="off"
            inputMode="url"
            placeholder="owner/repository or GitHub URL"
            value={repository}
            onChange={(event) => setRepository(event.target.value)}
            aria-invalid={Boolean(validationError)}
            aria-describedby={validationError ? "repo-error" : undefined}
          />
        </div>
        <button
          className="button button-primary"
          type="submit"
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "Starting analysis…" : "Analyze repository"}
        </button>
      </form>
      {validationError || requestError ? (
        <p className="form-error" id="repo-error" role="alert">
          {validationError ?? requestError}
        </p>
      ) : null}
      <fieldset className="mode-fieldset">
        <legend>Analysis mode</legend>
        <div className="mode-options">
          {modes.map(({ value, label, Icon }) => (
            <label className="mode-option" key={value}>
              <input
                type="radio"
                name="mode"
                value={value}
                checked={mode === value}
                onChange={() => setMode(value)}
              />
              <Icon aria-hidden="true" size={24} />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="landing-links">
        <button
          type="button"
          onClick={() => setRepository("octocat/Hello-World")}
        >
          Try an example <ArrowRight aria-hidden="true" size={16} />
        </button>
        <a href="#methodology-summary">
          How the analysis works <ArrowRight aria-hidden="true" size={16} />
        </a>
      </div>
    </div>
  );
}
