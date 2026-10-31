# Deploy the public live demo (Vercel)

The live demo is the web app built with `NEXT_PUBLIC_DEMO_STATIC=true`: bundled sample data,
no API, nothing saved or sent (why: [DECISIONS.md](DECISIONS.md#why-the-public-demo-is-static)).
Vercel's free Hobby plan is enough.

## One-time setup

1. Sign in at <https://vercel.com> with GitHub.
2. **Add New… → Project → Import** the `escalate` repository.
3. **Root Directory:** click *Edit* and choose **`web`**. Vercel then reads `web/vercel.json`,
   which sets:
   - Framework preset: **Next.js**
   - Install command: `npm ci`
   - Build command: **`npm run build:vercel`**, which runs `npm run build:demo` (sets
     `NEXT_PUBLIC_DEMO_STATIC=true`). Only a project with `NEXT_PUBLIC_DEPLOY_MODE=hosted` builds
     the hosted beta instead ([DEPLOY_BETA.md](DEPLOY_BETA.md)).
   Leave *Output Directory* empty (Next.js default).
4. **Environment variables:** none are needed. Do **not** add `NEXT_PUBLIC_API_URL` or any
   secret: the demo talks to no server, and anything `NEXT_PUBLIC_*` ends up in the browser.
5. **Node.js version** (Settings → General): 22.x.
6. Click **Deploy**. The first build takes about two minutes.
7. Optional: **Settings → Domains** to add your own domain; **Settings → Git** to keep
   "Production Branch" = `main`.

Every push to `main` redeploys; pull requests get preview URLs.

## After the first deploy

- Open the URL and check: the lime banner "Live demo · sample data · nothing is sent", four
  sample cases under *My cases*, and that *Approve* opens the "This is a live demo" dialog.
- Check the headers: `curl -sI https://<your-demo>.vercel.app/cases` should show
  `content-security-policy` (with `connect-src 'self'`), `strict-transport-security`,
  `x-frame-options: DENY`, `x-content-type-options: nosniff`, `referrer-policy` and
  `permissions-policy`.
- The live demo is <https://escalate-chi.vercel.app> (README badge and link). On a fork, change
  it there and in `.github/workflows/demo-preview.yml`.
- `make demo-preview` checks the link preview (Open Graph title, description, image) on the
  deployed URL; the `demo-preview` workflow runs it after each production deployment and daily.
- Share preview: the Open Graph image is `web/src/app/opengraph-image.png` (the *My cases*
  screen). Check it with any link-preview tool.

## Updating the sample data

```bash
make demo-fixtures   # throwaway DEMO_MODE API on a scratch DB in a temp folder (never escalate.db)
make demo-build      # builds the demo and scans the bundle for secrets and internal URLs
git add web/src/demo && git commit -m "chore(demo): refresh sample data"
```

To try the demo locally: `make demo-build`, then
`cd web && cp -r .next/static .next/standalone/.next/ && PORT=3000 node .next/standalone/server.js`
and open <http://localhost:3000>. No API needs to run.

## What CI checks on every push (`demo` job)

The demo build; the bundle scan (secrets, local/internal URLs) plus gitleaks; the Playwright
`demo` project (no request may leave the app's origin; writes open the dialog; the wizard ends
at "Demo ends here"); and the console guard, in light and dark. No API is started in that job.
