function fontStack(fontName) {
  return `"${fontName}", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`;
}

function marpBaseImport(variant) {
  return variant === "oram-dark" ? "uncover" : "gaia";
}

function slidePxPerIn(slide) {
  return 720 / slide.heightIn;
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

  return `/* ORAM PDF layout — from themes/oram-common.json */

.mermaid {
  margin: ${m.diagramMarginTopEm}em 0 ${m.diagramMarginBottomEm}em;
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
  margin: ${m.diagramMarginTopEm}em auto ${m.diagramMarginBottomEm}em;
}

span.label {
  display: block;
  font-size: ${m.labelScale}em;
  font-weight: 600;
  letter-spacing: ${m.labelLetterSpacingEm}em;
  text-transform: uppercase;
  margin-bottom: 0.35em;
}

.takeaway {
  position: absolute;
  bottom: ${m.takeawayBottomPx}px;
  left: ${m.takeawayInsetPx}px;
  right: ${m.takeawayInsetPx}px;
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
  margin: 0 0 ${m.gapAfterTitleEm}em;
  padding: 0;
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
  marpBaseImport,
  renderLayoutCss,
  renderVariantCss,
};
