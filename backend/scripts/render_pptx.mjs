import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const pptxgen = require("pptxgenjs");

const [specPath, outputPath] = process.argv.slice(2);

if (!specPath || !outputPath) {
  console.error("Usage: node render_pptx.mjs <deck-spec.json> <output.pptx>");
  process.exit(2);
}

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const C = spec.palette ?? {};

function color(name, fallback) {
  return String(C[name] ?? fallback).replace(/^#/, "");
}

const colors = {
  yellow: color("yellow", "FFD000"),
  blue: color("blue", "1A1446"),
  teal: color("teal", "78E1E1"),
  darkTeal: color("dark_teal", "037B86"),
  gray: color("atmospheric_gray", "F5F5F5"),
  white: color("white", "FFFFFF"),
  darkGray: color("dark_gray", "343741"),
  black: color("black", "000000"),
};

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "TFR Assistant";
pptx.company = "TFR Assistant";
pptx.subject = spec.title ?? "Generated deck";
pptx.title = spec.title ?? "Generated deck";
pptx.lang = "en-US";
pptx.theme = {
  headFontFace: "Aptos Display",
  bodyFontFace: "Aptos",
  lang: "en-US",
};

const ShapeType = pptx.ShapeType;

function text(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function box(input, fallback) {
  const source = input ?? fallback;
  return {
    x: Number(source.x),
    y: Number(source.y),
    w: Number(source.w),
    h: Number(source.h),
  };
}

function addFooter(slide, index) {
  slide.addShape(ShapeType.line, {
    x: 0.55,
    y: 7.05,
    w: 12.25,
    h: 0,
    line: { color: "D9DCE2", pt: 0.7 },
  });
  slide.addText(`TFR Assistant | ${index + 1}`, {
    x: 0.6,
    y: 7.12,
    w: 4.8,
    h: 0.18,
    fontFace: "Aptos",
    fontSize: 7.5,
    color: "737680",
  });
}

function addHeader(slide, title) {
  slide.addShape(ShapeType.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 0.16,
    fill: { color: colors.yellow },
    line: { color: colors.yellow },
  });
  slide.addText(text(title), {
    x: 0.62,
    y: 0.44,
    w: 11.9,
    h: 0.42,
    fontFace: "Aptos Display",
    fontSize: 22,
    bold: true,
    color: colors.blue,
    fit: "shrink",
  });
}

function addNotes(slide, notes) {
  if (notes) {
    slide.addNotes(text(notes));
  }
}

function addTitleSlide(slide, slideSpec) {
  slide.background = { color: colors.white };
  slide.addShape(ShapeType.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 0.25,
    fill: { color: colors.yellow },
    line: { color: colors.yellow },
  });
  if (slideSpec.kicker) {
    slide.addText(text(slideSpec.kicker).toUpperCase(), {
      x: 0.75,
      y: 1.2,
      w: 9.5,
      h: 0.32,
      fontFace: "Aptos",
      fontSize: 10,
      bold: true,
      color: colors.darkTeal,
      charSpace: 0,
    });
  }
  slide.addText(text(slideSpec.title || spec.title), {
    x: 0.72,
    y: 1.65,
    w: 9.9,
    h: 1.15,
    fontFace: "Aptos Display",
    fontSize: 34,
    bold: true,
    color: colors.blue,
    fit: "shrink",
  });
  if (slideSpec.subtitle || spec.subtitle) {
    slide.addText(text(slideSpec.subtitle || spec.subtitle), {
      x: 0.75,
      y: 3.0,
      w: 9.4,
      h: 0.5,
      fontFace: "Aptos",
      fontSize: 15,
      color: colors.darkTeal,
      fit: "shrink",
    });
  }
  slide.addShape(ShapeType.rect, {
    x: 10.75,
    y: 1.25,
    w: 1.55,
    h: 1.55,
    rectRadius: 0.05,
    fill: { color: colors.teal, transparency: 10 },
    line: { color: colors.teal },
  });
  slide.addShape(ShapeType.rect, {
    x: 11.35,
    y: 2.05,
    w: 1.35,
    h: 1.35,
    rectRadius: 0.05,
    fill: { color: colors.blue },
    line: { color: colors.blue },
  });
}

function addMetricSlide(slide, slideSpec) {
  addHeader(slide, slideSpec.title);
  const metrics = Array.isArray(slideSpec.metrics) ? slideSpec.metrics : [];
  const colWidth = metrics.length <= 2 ? 5.2 : metrics.length <= 3 ? 3.8 : 2.75;
  const startX = 0.7;
  metrics.slice(0, 4).forEach((metric, index) => {
    const x = startX + index * (colWidth + 0.25);
    slide.addShape(ShapeType.rect, {
      x,
      y: 1.55,
      w: colWidth,
      h: 2.1,
      fill: { color: "FAFAFB" },
      line: { color: "E0E2E6", pt: 0.8 },
    });
    slide.addText(text(metric.value), {
      x: x + 0.24,
      y: 1.86,
      w: colWidth - 0.48,
      h: 0.55,
      fontFace: "Aptos Display",
      fontSize: 26,
      bold: true,
      color: colors.blue,
      fit: "shrink",
    });
    slide.addText(text(metric.label), {
      x: x + 0.24,
      y: 2.48,
      w: colWidth - 0.48,
      h: 0.34,
      fontFace: "Aptos",
      fontSize: 11.5,
      bold: true,
      color: colors.darkGray,
      fit: "shrink",
    });
    if (metric.detail) {
      slide.addText(text(metric.detail), {
        x: x + 0.24,
        y: 2.94,
        w: colWidth - 0.48,
        h: 0.45,
        fontFace: "Aptos",
        fontSize: 8.5,
        color: "6B6E78",
        fit: "shrink",
      });
    }
  });
}

function addFindingsSlide(slide, slideSpec) {
  addHeader(slide, slideSpec.title);
  const findings = Array.isArray(slideSpec.findings) ? slideSpec.findings : [];
  const body = findings.map((finding) => `- ${text(finding)}`).join("\n");
  slide.addText(body, {
    x: 0.88,
    y: 1.35,
    w: 11.6,
    h: 4.9,
    fontFace: "Aptos",
    fontSize: 17,
    color: colors.darkGray,
    breakLine: false,
    fit: "shrink",
    valign: "top",
  });
}

function addImageSlide(slide, slideSpec) {
  addHeader(slide, slideSpec.title);
  if (slideSpec.imagePath && fs.existsSync(slideSpec.imagePath)) {
    slide.addImage({
      path: slideSpec.imagePath,
      x: 0.75,
      y: 1.25,
      w: 11.85,
      h: 5.15,
    });
  } else {
    slide.addText("Chart image unavailable", {
      x: 0.75,
      y: 2.8,
      w: 11.85,
      h: 0.5,
      fontSize: 18,
      color: colors.darkGray,
      align: "center",
    });
  }
  if (slideSpec.caption) {
    slide.addText(text(slideSpec.caption), {
      x: 0.75,
      y: 6.47,
      w: 11.85,
      h: 0.22,
      fontFace: "Aptos",
      fontSize: 8.5,
      color: "6B6E78",
      fit: "shrink",
    });
  }
}

function tableRows(headers, rows) {
  const safeHeaders = Array.isArray(headers) ? headers.map(text) : [];
  const safeRows = Array.isArray(rows) ? rows : [];
  return [
    safeHeaders.map((header) => ({
      text: header,
      options: {
        bold: true,
        color: colors.white,
        fill: { color: colors.blue },
      },
    })),
    ...safeRows.map((row) =>
      safeHeaders.map((_, index) => ({
        text: text(row?.[index]),
        options: { color: colors.darkGray },
      })),
    ),
  ];
}

function addTable(slide, headers, rows, tableBox, options = {}) {
  slide.addTable(tableRows(headers, rows), {
    ...tableBox,
    fontFace: "Aptos",
    fontSize: options.fontSize ?? 7.5,
    border: { type: "solid", color: "E3E5E8", pt: 0.45 },
    margin: 0.05,
    valign: "mid",
  });
}

function addTableSlide(slide, slideSpec) {
  addHeader(slide, slideSpec.title);
  addTable(slide, slideSpec.headers, slideSpec.rows, {
    x: 0.7,
    y: 1.35,
    w: 11.95,
    h: 5.15,
  });
  slide.addText(`Showing ${slideSpec.rendered_rows ?? 0} of ${slideSpec.row_count ?? 0} row(s). Full data is in the workbook.`, {
    x: 0.72,
    y: 6.55,
    w: 11.4,
    h: 0.22,
    fontFace: "Aptos",
    fontSize: 8,
    color: "6B6E78",
  });
}

function addCustomSlide(slide, slideSpec) {
  addHeader(slide, slideSpec.title);
  const elements = Array.isArray(slideSpec.elements) ? slideSpec.elements : [];
  elements.forEach((element) => {
    const b = box(element.box, { x: 0.7, y: 1.2, w: 4, h: 1 });
    if (element.kind === "text") {
      slide.addText(text(element.text), {
        ...b,
        fontFace: "Aptos",
        fontSize: Number(element.style?.fontSize ?? 13),
        bold: Boolean(element.style?.bold),
        color: colorFromStyle(element.style, colors.darkGray),
        fit: "shrink",
        valign: "top",
      });
    } else if (element.kind === "callout") {
      slide.addShape(ShapeType.rect, {
        ...b,
        fill: { color: colors.gray },
        line: { color: colors.teal, pt: 1.1 },
      });
      slide.addText(text(element.text), {
        x: b.x + 0.15,
        y: b.y + 0.13,
        w: Math.max(0.1, b.w - 0.3),
        h: Math.max(0.1, b.h - 0.26),
        fontSize: Number(element.style?.fontSize ?? 11),
        color: colorFromStyle(element.style, colors.darkGray),
        fit: "shrink",
      });
    } else if (element.kind === "metric") {
      slide.addText(text(element.value), {
        ...b,
        fontSize: Number(element.style?.fontSize ?? 24),
        bold: true,
        color: colorFromStyle(element.style, colors.blue),
        fit: "shrink",
      });
      if (element.label) {
        slide.addText(text(element.label), {
          x: b.x,
          y: b.y + Math.max(0.35, b.h - 0.28),
          w: b.w,
          h: 0.25,
          fontSize: 9,
          bold: true,
          color: colors.darkGray,
          fit: "shrink",
        });
      }
    } else if (element.kind === "shape") {
      slide.addShape(ShapeType.rect, {
        ...b,
        fill: { color: colorFromStyle(element.style?.fill, colors.gray) },
        line: { color: colorFromStyle(element.style?.line, colors.teal), pt: 0.8 },
      });
    } else if (element.kind === "table") {
      addTable(slide, element.headers, element.rows, b, { fontSize: element.fontSize });
    } else if (element.kind === "chart" && element.imagePath) {
      slide.addImage({ path: element.imagePath, ...b });
    }
  });
}

function colorFromStyle(style, fallback) {
  if (!style) return fallback;
  const value = typeof style === "string" ? style : style.color;
  return value ? String(value).replace(/^#/, "") : fallback;
}

(spec.slides ?? []).forEach((slideSpec, index) => {
  const slide = pptx.addSlide();
  slide.background = { color: colors.white };
  if (slideSpec.type === "title") {
    addTitleSlide(slide, slideSpec);
  } else if (slideSpec.type === "metrics") {
    addMetricSlide(slide, slideSpec);
  } else if (slideSpec.type === "findings") {
    addFindingsSlide(slide, slideSpec);
  } else if (slideSpec.type === "chart") {
    addImageSlide(slide, slideSpec);
  } else if (slideSpec.type === "table") {
    addTableSlide(slide, slideSpec);
  } else if (slideSpec.type === "custom") {
    addCustomSlide(slide, slideSpec);
  } else {
    addHeader(slide, slideSpec.title ?? "Generated slide");
    slide.addText(`Unsupported slide type: ${slideSpec.type}`, {
      x: 0.8,
      y: 2.5,
      w: 11.5,
      h: 0.4,
      color: colors.darkGray,
      align: "center",
    });
  }
  addFooter(slide, index);
  addNotes(slide, slideSpec.notes);
});

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
await pptx.writeFile({ fileName: outputPath });
