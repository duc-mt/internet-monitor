/**
 * "Save as PNG" for the latency chart, with no extra dependency.
 *
 * Why not screenshot the DOM: the legend and tooltip are HTML, while the plot
 * itself is one SVG. So the plot is serialised and drawn onto a canvas, and
 * the title, time window, legend and export time are drawn around it - which
 * is what makes the image usable as evidence for an ISP (what was measured,
 * when, and which line is which).
 *
 * The SVG uses CSS variables (stroke="var(--color-border)"). A standalone SVG
 * loaded as an <img> has no :root to resolve them against, so they are
 * resolved to concrete colours first.
 */

export interface LegendEntry {
  label: string;
  color: string;
  /** How the swatch is drawn: a line (default), a dashed line, or a block (for the loss bars). */
  style?: "line" | "dashed" | "block";
}

export interface ChartExportMeta {
  title: string;
  subtitle: string;
  legend: LegendEntry[];
}

type Theme = "light" | "dark";

// Solid Slate backgrounds (never pure white/black), per the design system.
const PALETTE: Record<Theme, { background: string; text: string; muted: string; rule: string }> = {
  light: { background: "#f8fafc", text: "#0f172a", muted: "#64748b", rule: "#cbd5e1" }, // slate-50
  dark: { background: "#020617", text: "#f1f5f9", muted: "#94a3b8", rule: "#1e293b" }, // slate-950
};

const PAD = 24;
const MIN_SCALE = 2;
const MAX_SCALE = 3;
const MONO = "'Fira Code', ui-monospace, monospace";

const pad2 = (n: number) => String(n).padStart(2, "0");

/** internet-monitor-chart-20260102-030405.png, in local time like the rest of the UI. */
export function chartFilename(date: Date = new Date()): string {
  const day = `${date.getFullYear()}${pad2(date.getMonth() + 1)}${pad2(date.getDate())}`;
  const time = `${pad2(date.getHours())}${pad2(date.getMinutes())}${pad2(date.getSeconds())}`;
  return `internet-monitor-chart-${day}-${time}.png`;
}

/** Full local date and time, e.g. for the image header (the UI's own formats omit the year). */
export function formatStamp(date: Date): string {
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

/** Replaces every var(--x) in the element tree's attributes with its resolved value. */
export function inlineCssVariables(root: Element, resolve: (name: string) => string): void {
  const pattern = /var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)/g;
  for (const node of [root, ...Array.from(root.querySelectorAll("*"))]) {
    for (const attr of Array.from(node.attributes)) {
      if (attr.value.includes("var(")) {
        node.setAttribute(attr.name, attr.value.replace(pattern, (_m, name: string) => resolve(name) || "#94a3b8"));
      }
    }
  }
}

/** Wraps legend entries into rows no wider than `maxWidth`. `measure` returns the rendered text width. */
export function layoutLegend(
  entries: LegendEntry[],
  maxWidth: number,
  measure: (text: string) => number,
  swatch = 22,
  gap = 8,
  itemGap = 20
): LegendEntry[][] {
  const rows: LegendEntry[][] = [];
  let row: LegendEntry[] = [];
  let used = 0;
  for (const entry of entries) {
    const width = swatch + gap + measure(entry.label);
    if (row.length > 0 && used + itemGap + width > maxWidth) {
      rows.push(row);
      row = [];
      used = 0;
    }
    used += (row.length > 0 ? itemGap : 0) + width;
    row.push(entry);
  }
  if (row.length > 0) rows.push(row);
  return rows;
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("The chart image could not be rendered"));
    img.src = url;
  });
}

function toBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("PNG encoding failed"))), "image/png")
  );
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function drawSwatch(ctx: CanvasRenderingContext2D, entry: LegendEntry, x: number, y: number, swatch: number) {
  ctx.save();
  if (entry.style === "block") {
    ctx.globalAlpha = 0.55;
    ctx.fillStyle = entry.color;
    ctx.fillRect(x + swatch / 2 - 2, y - 11, 4, 12);
  } else {
    ctx.strokeStyle = entry.color;
    ctx.lineWidth = entry.style === "dashed" ? 1.5 : 2.5;
    ctx.setLineDash(entry.style === "dashed" ? [3, 3] : []);
    ctx.beginPath();
    ctx.moveTo(x, y - 5);
    ctx.lineTo(x + swatch, y - 5);
    ctx.stroke();
  }
  ctx.restore();
}

/** Renders the chart found inside `container` to a PNG and triggers the browser download. */
export async function exportChartPng(container: HTMLElement, meta: ChartExportMeta): Promise<void> {
  const source = container.querySelector<SVGSVGElement>(".recharts-wrapper > svg.recharts-surface");
  if (!source) throw new Error("No chart to export");

  const rect = source.getBoundingClientRect();
  const width = Math.round(rect.width);
  const height = Math.round(rect.height);
  if (width === 0 || height === 0) throw new Error("The chart has no size yet");

  const theme: Theme = document.documentElement.classList.contains("light") ? "light" : "dark";
  const colors = PALETTE[theme];
  const rootStyle = getComputedStyle(document.documentElement);

  const svg = source.cloneNode(true) as SVGSVGElement;
  inlineCssVariables(svg, (name) => rootStyle.getPropertyValue(name).trim());
  // No explicit xmlns: XMLSerializer declares the SVG namespace itself, and setting
  // the attribute by hand makes some serialisers emit it twice (invalid XML).
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.removeAttribute("style"); // width/height: 100% only makes sense inside the page
  const svgUrl = URL.createObjectURL(
    new Blob([new XMLSerializer().serializeToString(svg)], { type: "image/svg+xml;charset=utf-8" })
  );

  try {
    const image = await loadImage(svgUrl);

    const totalWidth = width + PAD * 2;
    const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, window.devicePixelRatio || 1));
    const sans = getComputedStyle(document.body).fontFamily || "system-ui, sans-serif";

    // Measure first: the legend's wrapped height decides the canvas height.
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas is not available");
    ctx.font = `12px ${MONO}`;
    const rows = layoutLegend(meta.legend, totalWidth - PAD * 2, (text) => ctx.measureText(text).width);
    const totalHeight = PAD + 28 + 22 + rows.length * 20 + 8 + height + 8 + 20 + PAD;

    canvas.width = Math.round(totalWidth * scale);
    canvas.height = Math.round(totalHeight * scale);
    ctx.scale(scale, scale);

    ctx.fillStyle = colors.background;
    ctx.fillRect(0, 0, totalWidth, totalHeight);

    let y = PAD;
    ctx.fillStyle = colors.text;
    ctx.font = `600 18px ${sans}`;
    ctx.fillText(meta.title, PAD, y + 18);
    y += 28;
    ctx.fillStyle = colors.muted;
    ctx.font = `12px ${MONO}`;
    ctx.fillText(meta.subtitle, PAD, y + 12);
    y += 22;

    for (const row of rows) {
      let x = PAD;
      for (const entry of row) {
        drawSwatch(ctx, entry, x, y + 12, 22);
        ctx.fillStyle = colors.text;
        ctx.font = `12px ${MONO}`;
        ctx.fillText(entry.label, x + 22 + 8, y + 12);
        x += 22 + 8 + ctx.measureText(entry.label).width + 20;
      }
      y += 20;
    }
    y += 8;

    ctx.drawImage(image, PAD, y, width, height);
    y += height + 8;

    ctx.strokeStyle = colors.rule;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(PAD, y);
    ctx.lineTo(totalWidth - PAD, y);
    ctx.stroke();
    ctx.fillStyle = colors.muted;
    ctx.font = `11px ${MONO}`;
    ctx.fillText(`Exported ${formatStamp(new Date())} · Internet Monitor`, PAD, y + 15);

    downloadBlob(await toBlob(canvas), chartFilename());
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}
