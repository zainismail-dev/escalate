// Link preview check for a deployed URL: Open Graph title, description and image must be set,
// and the image must load as an image.   node scripts/check-link-preview.mjs https://escalate-chi.vercel.app
const url = process.argv[2] || process.env.DEMO_URL;
if (!url) {
  console.error("usage: node scripts/check-link-preview.mjs <url>");
  process.exit(2);
}
const html = await (await fetch(url, { headers: { "User-Agent": "link-preview-check" } })).text();
const meta = (key) =>
  html.match(new RegExp(`<meta[^>]+(?:property|name)="${key}"[^>]+content="([^"]*)"`, "i"))?.[1] ?? null;
const found = {
  "og:title": meta("og:title"),
  "og:description": meta("og:description"),
  "og:image": meta("og:image"),
  "twitter:card": meta("twitter:card"),
};
const problems = Object.entries(found).filter(([, v]) => !v).map(([k]) => `missing ${k}`);
if (found["og:image"]) {
  const img = new URL(found["og:image"].replaceAll("&amp;", "&"), url);
  if (img.origin !== new URL(url).origin) problems.push(`og:image is on another host: ${img.origin}`);
  const r = await fetch(img);
  const type = r.headers.get("content-type") || "";
  if (!r.ok || !type.startsWith("image/")) problems.push(`og:image ${img} -> ${r.status} ${type}`);
  else found["og:image"] = `${img} (${type}, ${(await r.arrayBuffer()).byteLength} bytes)`;
}
for (const [k, v] of Object.entries(found)) console.log(`${k}: ${v}`);
for (const p of problems) console.error(`FAIL ${p}`);
process.exit(problems.length ? 1 : 0);
