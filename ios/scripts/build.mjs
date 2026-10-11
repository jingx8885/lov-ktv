import { cp, mkdir, rm } from "node:fs/promises";
await rm("www", { recursive: true, force: true });
await mkdir("www", { recursive: true });
await cp("web", "www", { recursive: true });
await cp("../frontend/public/brand/icon.png", "www/icon.png");

await cp(
  "node_modules/@capacitor/core/dist/capacitor.js",
  "www/capacitor-runtime.js",
);
