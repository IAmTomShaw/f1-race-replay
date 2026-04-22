import * as esbuild from "esbuild";

const isWatch = process.argv.includes("--watch");

const ctx = await esbuild.context({
  entryPoints: ["src/index.jsx"],
  bundle: true,
  outfile: "dist/bundle.js",
  format: "iife",
  jsx: "transform",
  jsxFactory: "React.createElement",
  jsxFragment: "React.Fragment",
  target: ["chrome90", "firefox90", "safari15"],
  // React/ReactDOM are loaded from CDN as globals — no import statements to externalize
  // All files assign to window.XXX explicitly, so the IIFE wrapper
  // doesn't need to export anything. We just need the side-effects.
  footer: {
    js: "// side-effects only — window.APEX, window.LIVE, etc.",
  },
  minify: !isWatch,
  sourcemap: isWatch,
  logLevel: "info",
});

if (isWatch) {
  await ctx.watch();
  console.log("Watching for changes...");
} else {
  await ctx.rebuild();
  await ctx.dispose();
  console.log("Build complete.");
}
