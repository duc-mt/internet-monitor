import { afterEach, describe, expect, it, vi } from "vitest";
import { chartFilename, exportChartPng, inlineCssVariables, layoutLegend, type LegendEntry } from "../src/services/exportChart";

describe("chartFilename", () => {
  it("embeds the local date and time, zero-padded", () => {
    expect(chartFilename(new Date(2026, 0, 2, 3, 4, 5))).toBe("internet-monitor-chart-20260102-030405.png");
    expect(chartFilename(new Date(2026, 10, 12, 13, 14, 15))).toBe("internet-monitor-chart-20261112-131415.png");
  });
});

describe("inlineCssVariables", () => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const build = () => {
    const svg = document.createElementNS(SVG_NS, "svg");
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("stroke", "var(--color-border)");
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("fill", "var(--color-muted)");
    text.setAttribute("font-size", "11");
    svg.append(line, text);
    return { svg, line, text };
  };

  it("replaces var() references with the resolved values and leaves other attributes alone", () => {
    const { svg, line, text } = build();
    inlineCssVariables(svg, (name) => ({ "--color-border": "#1e293b", "--color-muted": "#94a3b8" })[name] ?? "");
    expect(line.getAttribute("stroke")).toBe("#1e293b");
    expect(text.getAttribute("fill")).toBe("#94a3b8");
    expect(text.getAttribute("font-size")).toBe("11");
  });

  it("falls back to a slate colour for a variable that does not resolve", () => {
    const { svg, line } = build();
    inlineCssVariables(svg, () => "");
    expect(line.getAttribute("stroke")).toBe("#94a3b8");
  });
});

describe("layoutLegend", () => {
  const entry = (label: string): LegendEntry => ({ label, color: "#fff" });
  const measure = (text: string) => text.length * 10;

  it("keeps entries on one row while they fit", () => {
    const rows = layoutLegend([entry("A"), entry("B")], 400, measure);
    expect(rows.map((r) => r.map((e) => e.label))).toEqual([["A", "B"]]);
  });

  it("wraps onto a new row when the next entry would overflow", () => {
    // each entry: 22 swatch + 8 gap + 10 text = 40; two entries + 20 gap = 100 > 90
    const rows = layoutLegend([entry("A"), entry("B"), entry("C")], 90, measure);
    expect(rows.map((r) => r.map((e) => e.label))).toEqual([["A"], ["B"], ["C"]]);
  });

  it("puts an over-long entry on its own row rather than dropping it", () => {
    expect(layoutLegend([entry("a-very-long-target-name")], 50, measure)).toHaveLength(1);
  });

  it("returns no rows for no entries", () => {
    expect(layoutLegend([], 400, measure)).toEqual([]);
  });
});

describe("exportChartPng", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
    document.documentElement.classList.remove("light", "dark");
  });

  function setup() {
    document.body.innerHTML = `
      <div id="chart"><div class="recharts-wrapper">
        <svg class="recharts-surface" width="800" height="280" style="width: 100%; height: 100%;">
          <line stroke="var(--color-border)" x1="0" y1="0" x2="10" y2="10"></line>
        </svg>
      </div></div>`;
    const container = document.getElementById("chart") as HTMLElement;
    const svg = container.querySelector("svg") as SVGSVGElement;
    svg.getBoundingClientRect = () => ({ width: 800, height: 280 }) as DOMRect;

    const fills: string[] = [];
    const texts: string[] = [];
    const ctx = {
      set fillStyle(v: string) { fills.push(v); },
      font: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1,
      scale: vi.fn(), fillRect: vi.fn(), drawImage: vi.fn(), save: vi.fn(), restore: vi.fn(),
      beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), setLineDash: vi.fn(),
      fillText: vi.fn((text: string) => { texts.push(text); }),
      measureText: (t: string) => ({ width: t.length * 7 }),
    };
    const canvases: HTMLCanvasElement[] = [];
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(function (this: HTMLCanvasElement) {
      canvases.push(this);
      return ctx as unknown as CanvasRenderingContext2D;
    });
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((cb) => cb(new Blob(["png"], { type: "image/png" })));

    const svgBlobs: Blob[] = [];
    URL.createObjectURL = vi.fn((blob: Blob | MediaSource) => {
      svgBlobs.push(blob as Blob);
      return "blob:fake";
    });
    URL.revokeObjectURL = vi.fn();
    class FakeImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) { queueMicrotask(() => this.onload?.()); }
    }
    vi.stubGlobal("Image", FakeImage);

    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push(this.download);
    });
    return { container, ctx, fills, texts, canvases, svgBlobs, downloads };
  }

  const meta = {
    title: "Internet Monitor · Latency",
    subtitle: "window",
    legend: [
      { label: "Gateway", color: "#34d8c6" },
      { label: "Packet loss", color: "#ef4444", style: "block" as const },
    ],
  };

  it("draws header, legend and plot on a themed canvas and downloads a PNG", async () => {
    const { container, ctx, fills, texts, canvases, downloads } = setup();
    await exportChartPng(container, meta);

    expect(texts).toContain("Internet Monitor · Latency");
    expect(texts).toContain("Gateway");
    expect(texts).toContain("Packet loss");
    expect(texts.some((t) => t.startsWith("Exported "))).toBe(true);
    expect(ctx.drawImage).toHaveBeenCalledTimes(1);
    expect(fills[0]).toBe("#020617"); // solid slate-950 background in the dark theme
    expect(canvases[0].width).toBe((800 + 48) * 2);
    expect(downloads).toHaveLength(1);
    expect(downloads[0]).toMatch(/^internet-monitor-chart-\d{8}-\d{6}\.png$/);
  });

  it("uses the slate-50 background in the light theme", async () => {
    const { container, fills } = setup();
    document.documentElement.classList.add("light");
    await exportChartPng(container, meta);
    expect(fills[0]).toBe("#f8fafc");
  });

  it("serialises a standalone SVG with no CSS variables left in it", async () => {
    const { container, svgBlobs } = setup();
    await exportChartPng(container, meta);
    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(svgBlobs[0]);
    });
    expect(text).not.toContain("var(");
    expect(text).toContain('width="800"');
    expect(text).not.toContain("width: 100%");
  });

  it("rejects when there is no chart to export", async () => {
    document.body.innerHTML = '<div id="empty"></div>';
    await expect(exportChartPng(document.getElementById("empty") as HTMLElement, meta)).rejects.toThrow("No chart to export");
  });
});
