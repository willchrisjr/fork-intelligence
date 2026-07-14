# Visual Fidelity Ledger

Validated on 2026-07-13 by comparing native-resolution Chromium captures with
the three approved concept images in `docs/design/`.

## Confirmed matches

- The landing page preserves the true-white canvas, navy typography, cobalt
  primary action, teal maintenance signal, and amber uncertainty signal.
- The first viewport keeps the approved headline, public-repository input,
  four analysis modes, security disclosure, and fork-lineage illustration in
  the same visual hierarchy.
- The workspace retains the compact top command bar, stage/navigation rail,
  metrics strip, partial-result banner, dense fork table, confidence bars, and
  comparison action.
- The comparison surface is fixed to upstream plus two forks and includes
  history, overlap, composition, integration, evidence, and missing-data
  regions.
- Desktop, Pixel 7 portrait, and Pixel 7 landscape layouts expose the same
  workflow without hover-only controls; the final responsive run has no
  horizontal page overflow.

## Intentional or bounded differences

- Illustrative repository labels were replaced with neutral names so a visual
  example cannot be mistaken for an analyzed result.
- Security copy says credentials remain server-side and sampling is disclosed;
  it does not make unsupported deletion or model-training promises.
- The implementation uses a lighter investigation shell than the comparison
  concept's dark product-wide rail, while preserving its role colors and
  three-repository framing.
- The workspace and comparison reference captures use deliberately small E2E
  fixtures. Empty space in those captures represents bounded fixture data, not
  hidden product sections; richer rows render when the API supplies evidence.
- The lineage preview is a deterministic SVG illustration rather than a live
  graph. The live evolution route uses Cytoscape with search, focus, zoom,
  reset, and an accessible synchronized table.

## Validation artifacts

- Approved concepts: `docs/design/landing-concept.png`,
  `docs/design/analysis-workspace-concept.png`, and
  `docs/design/comparison-concept.png`.
- Chromium captures: `/tmp/fork-intelligence-e2e/landing-1568x1002.png`,
  `/tmp/fork-intelligence-e2e/workspace-1680x936.png`, and
  `/tmp/fork-intelligence-e2e/comparison-1680x944.png`.
- Browser suite: 19 behavioral checks passed; 3 opt-in capture checks passed.

The in-app browser runtime failed twice during initialization with
`Cannot redefine property: process`. The standalone Playwright workflow was
used as the documented fallback and the resulting images were inspected beside
the approved concepts at original resolution.
