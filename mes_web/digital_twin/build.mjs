import { copyFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Optionally reuse the pinned dependencies of the original local Babylon project.
const dependencyManifest = process.argv[2]
  ? pathToFileURL(resolve(process.argv[2], "package.json"))
  : new URL("./package.json", import.meta.url);
const require = createRequire(dependencyManifest);
const { build } = await import(pathToFileURL(require.resolve("vite")));
const coreManifest = require.resolve("@babylonjs/core/package.json");
const coreDir = resolve(coreManifest, "..");
const outDir = fileURLToPath(new URL("../static/digital-twin/engine/", import.meta.url));

await build({
  root: import.meta.dirname,
  configFile: false,
  publicDir: false,
  logLevel: "warn",
  resolve: { alias: { "@babylonjs/core": coreDir } },
  build: {
    outDir,
    emptyOutDir: true,
    lib: {
      entry: fileURLToPath(new URL("./model.js", import.meta.url)),
      formats: ["es"],
      fileName: () => "model.js",
    },
    minify: true,
    rolldownOptions: { output: { codeSplitting: false } },
    reportCompressedSize: false,
  },
});
await copyFile(resolve(coreDir, "license.md"), resolve(outDir, "BABYLON-LICENSE.md"));
await copyFile(resolve(coreDir, "NOTICE.md"), resolve(outDir, "BABYLON-NOTICE.md"));
