// Copies pinned HTMX/Alpine builds from node_modules into static/js/ so they
// are served as local static assets (via django.contrib.staticfiles) instead
// of CDN <script> tags. Run via `npm run build:js` (or `npm run build`),
// same as the Tailwind CLI step -- see README.md.
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = path.join(ROOT, "static", "js");

const FILES = [
  {
    src: path.join(ROOT, "node_modules", "htmx.org", "dist", "htmx.min.js"),
    dest: path.join(OUT_DIR, "htmx.min.js"),
  },
  {
    src: path.join(ROOT, "node_modules", "alpinejs", "dist", "cdn.min.js"),
    dest: path.join(OUT_DIR, "alpine.min.js"),
  },
];

fs.mkdirSync(OUT_DIR, { recursive: true });

for (const { src, dest } of FILES) {
  fs.copyFileSync(src, dest);
  console.log(`copied ${path.relative(ROOT, src)} -> ${path.relative(ROOT, dest)}`);
}
