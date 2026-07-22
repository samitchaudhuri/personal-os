function fontStack(fontName) {
  return `"${fontName}", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`;
}

function marpBaseImport(variant) {
  return variant === "oram-dark" ? "uncover" : "gaia";
}

function slidePxPerIn(slide) {
  return 720 / slide.heightIn;
}

function layoutInToPx(inches, slide) {
  return Math.round(inches * slidePxPerIn(slide));
}

function renderLayoutCss(common, variant) {
  const m = common.typography.marp;
  const l = common.layout;
  const c = common.columns;
  const h = m.headings;
  const letterSpacing =
    variant === "oram-dark" ? "\n  letter-spacing: normal;" : "";
  const contentPadBottom =
    (l.takeawayBottomIn + l.takeawayBandHeightIn) * slidePxPerIn(common.slide);
  const gapAfterTitlePx = layoutInToPx(l.gapAfterTitleIn, common.slide);
  const gapAfterDiagramPx = layoutInToPx(l.gapAfterDiagramIn, common.slide);
  const gapAfterKickerPx = layoutInToPx(l.gapAfterKickerIn, common.slide);
  const titleBoxPadPx = layoutInToPx(l.titleBoxPadIn ?? 0.04, common.slide);
  const titleLineHeight = l.titleLineHeight ?? 1.3;
  const chromeTopPx = layoutInToPx(l.chromeTopIn, common.slide);
  const kickerHeightPx = layoutInToPx(l.kickerHeightIn, common.slide);
  const takeawayBottomPx = layoutInToPx(l.takeawayBottomIn, common.slide);
  const takeawayInsetPx = layoutInToPx(l.marginIn, common.slide);
  const labelScale = common.typography.pptx.kicker / m.bodyPx;

  return `/* ORAM PDF layout — from themes/oram-common.json (derived from PPTX layout tokens) */

.mermaid {
  margin: 0 0 ${gapAfterDiagramPx}px;
}

section {
  font-family: ${fontStack(common.font)};
  font-size: ${m.bodyPx}px;
  line-height: ${l.lineHeight};
  text-align: left;
  display: block;
  place-content: normal;
  justify-content: flex-start;
  align-items: stretch;
  box-sizing: border-box;
  padding-top: ${chromeTopPx}px;
  padding-bottom: ${contentPadBottom}px;${letterSpacing}
}

header,
footer {
  display: none !important;
}

section img {
  flex-shrink: 0;
  max-height: ${l.diagramMaxHeightPx}px;
  max-width: 100%;
  height: auto;
  width: auto;
  display: block;
  margin: 0 auto ${gapAfterDiagramPx}px;
}

span.label {
  display: block;
  font-size: ${labelScale}em;
  font-weight: 600;
  letter-spacing: ${m.labelLetterSpacingEm}em;
  text-transform: uppercase;
  min-height: ${kickerHeightPx}px;
  margin-bottom: ${gapAfterKickerPx}px;
}

.takeaway {
  position: absolute;
  bottom: ${takeawayBottomPx}px;
  left: ${takeawayInsetPx}px;
  right: ${takeawayInsetPx}px;
  font-size: ${m.takeawayScale}em;
  padding: ${m.takeawayPaddingEm}em 0.65em;
  border-radius: 4px;
}

section::before,
section::after {
  display: none !important;
}

h1 {
  font-size: ${h.h1}em;
  line-height: ${titleLineHeight};
  margin: 0 0 ${gapAfterTitlePx}px;
  padding: 0 0 ${titleBoxPadPx}px;
  border: 0;
}

h2 {
  font-size: ${h.h2}em;
  margin: 0 0 0.2em;
}

h3 {
  font-size: ${h.h3}em;
  margin: 0 0 0.15em;
}

blockquote {
  margin-top: 0.2em;
  margin-bottom: 0.2em;
}

p,
ul,
ol {
  margin-top: 0.2em;
  margin-bottom: 0.2em;
}

li {
  margin: 0.025em 0;
}

ol > li > p,
ul > li > p {
  margin: 0.025em 0;
}

section > *:first-child {
  margin-top: 0;
}

section > *:last-child {
  margin-bottom: 0;
}

.cols {
  display: flex;
  gap: ${c.gapPx}px;
  align-items: flex-start;
}

.col-left {
  flex: 0 0 ${c.leftPercent}%;
}

.col-right {
  flex: 1;
}

.col-left .mermaid {
  margin-top: 0;
  margin-bottom: 0;
}

.col-right ul {
  margin-top: 0.15em;
  margin-bottom: 0.35em;
}

.col-right li {
  margin: 0.05em 0;
}
`;
}

function renderVariantCss(variant, merged) {
  const colors = merged.colors;
  const themeName = merged.pdf?.marpTheme || variant;
  const commonOnly = {
    font: merged.font,
    slide: merged.slide,
    layout: merged.layout,
    typography: merged.typography,
    columns: merged.columns,
  };

  return `/* @theme ${themeName} */
@import '${marpBaseImport(variant)}';

${renderLayoutCss(commonOnly, variant)}

section {
  background-color: ${colors.background};
  background-image: none;
  color: ${colors.ink};
}

span.label {
  color: ${colors.accent};
}

.takeaway {
  background-color: ${colors.takeawayFill};
  color: ${colors.takeawayText};
}

h1,
h2,
h3,
h4,
h5,
h6 {
  color: ${colors.ink};
}

a {
  color: ${colors.accent};
}

em {
  color: ${colors.accent};
}
`;
}

module.exports = {
  fontStack,
  layoutInToPx,
  marpBaseImport,
  renderLayoutCss,
  renderVariantCss,
  slidePxPerIn,
};
