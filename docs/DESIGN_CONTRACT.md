# Approved Visual Design Contract

Approval status: approved by the user on 2026-07-13.

## References

- Landing: `docs/design/landing-concept.png`
- Analysis: `docs/design/analysis-workspace-concept.png`
- Comparison: `docs/design/comparison-concept.png`

## Locked elements

- True-white surfaces, ink/navy text, cobalt actions/selections, teal healthy or
  maintained evidence, amber uncertainty/partial data, restrained red errors.
- Editorial sans typography with monospace repository, commit, patch, and
  evidence identifiers.
- Landing prioritizes the repository input and restrained lineage preview.
- Operational workspace uses compact command/status bar, navigation/stage rail,
  dominant evidence table or viewport, and synchronized evidence inspector.
- Comparison preserves upstream-plus-two structure, relationship view, overlap
  matrix, composition, integration notes, and evidence list.
- No decorative gradients, glow, bokeh, generic card grids, hover-only evidence,
  or rasterized factual UI.

## Responsive continuation

- Mobile portrait leads with evidence and uses command drawers for secondary
  controls; applied controls return focus to the affected evidence.
- Mobile landscape is supported for the evolution network with explicit zoom,
  reset, search, step-through, and table controls.
- Stale, partial, sampled, rate-limited, and missing-data states remain visible.

## Renderer ownership and accessibility

React owns data, labels, filters, URL state, selection, panels, and accessible
summaries. Cytoscape owns bounded graph geometry and picking inside a lazy-loaded
client component. Every graph conclusion is available through the synchronized
keyboard-accessible table. Motion is non-essential and disabled for reduced
motion.
