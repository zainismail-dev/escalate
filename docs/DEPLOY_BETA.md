# Deploy the hosted beta (invite-only, free tiers)

This guide puts Escalate online for a few invited people, without paying for anything. It is
written for someone who has never deployed a web app, using an Intel Mac. Allow about 90
minutes the first time. Do the steps **in order**: later steps need values from earlier ones.

What you end up with:

| Piece | Service (free plan) | Region |
| --- | --- | --- |
| Web app `escalate-beta` | Vercel | global |
| API | Render (Docker web service) | Frankfurt |
| Database, sign-in, evidence files | Supabase | Frankfurt (EU Central) |
| AI | Groq (zero data retention) | — |
| Hourly reminders | GitHub Actions (`tick` workflow) | — |

How it behaves: people sign in with Google; only emails you invite get past the waitlist; each
user sees only their own cases; the AI provider is fixed (users can't change it); and Escalate
**never sends email**. After a user approves a letter, they send it from their own email app and
click "I've sent it". Self-hosted Escalate (`make up`) is not affected by any of this.

> ### ⚠️ Never paste these into a chat, an issue, a screenshot or a commit
> `DATABASE_URL` (it contains your database password), the Supabase **secret** /
> `service_role` key, the database password, the Google **client secret**, the Groq API key,
> `FERNET_KEY` and `TICK_SECRET`. They go only into the Supabase, Render, Vercel and GitHub
> settings pages named below. Keep a copy in a password manager. If one leaks, rotate it (make
> a new one and replace it everywhere). AI assistants included: never paste them into a chat.
>
> Public by design (fine to share): the Supabase project URL, the Supabase **publishable**
> (anon) key, the Google **client ID**, and your Render and Vercel URLs.

Keep a note (in your password manager) as you go. You will collect these values:

| # | Value | Example | Secret? |
| --- | --- | --- | --- |
| A | Supabase project URL | `https://abcdefghijkl.supabase.co` | no |
| B | Supabase publishable (anon) key | `sb_publishable_…` | no |
| C | Supabase secret key | `sb_secret_…` | **yes** |
| D | Database password | (you choose it) | **yes** |
| E | Session pooler connection string (`DATABASE_URL`) | `postgresql://postgres.abcdefghijkl:…@aws-0-eu-central-1.pooler.supabase.com:5432/postgres` | **yes** |
| F | Google OAuth client ID | `1234-abc.apps.googleusercontent.com` | no |
| G | Google OAuth client secret | `GOCSPX-…` | **yes** |
| H | Groq API key | `gsk_…` | **yes** |
| I | `FERNET_KEY` | 44 characters ending in `=` | **yes** |
| J | Render API URL | `https://escalate-api.onrender.com` | no |
| K | `TICK_SECRET` (Render generates it) | long random text | **yes** |
| L | Vercel web URL | `https://escalate-beta.vercel.app` | no |

---

## 1. Supabase project (database, sign-in, files)

1. Go to <https://supabase.com> → **Start your project** → sign in with GitHub.
2. **New project**:
   - Organization: your personal one (Free plan).
   - Name: `escalate-beta`.
   - Database password: click **Generate a password**, then **copy it into your password
     manager now** (value **D**). Tip: if you type your own, use only letters and digits (special
     characters need URL-encoding in the connection string).
   - Region: **Central EU (Frankfurt)**.
   - Click **Create new project** and wait about two minutes.
3. **Project URL and keys:** left sidebar → **Project Settings** (gear) → **API Keys**.
   - Copy the **Project URL** (also shown under *Data API*) → value **A**.
   - Copy the **Publishable key** (`sb_publishable_…`) → value **B**. If your project only shows
     *Legacy API keys*, use the `anon` `public` key instead.
   - Under *Secret keys*, click **Reveal** / copy the default secret key (`sb_secret_…`) →
     value **C**. (Legacy projects: the `service_role` key.) This key bypasses all security:
     server only.
4. **JWT signing key:** **Project Settings → JWT Keys**. The *current key* should say
   **ECC (P-256)**. If it says *Legacy HS256 (Shared Secret)*: click **Migrate JWT secret**,
   then **Rotate keys** so an ECC (P-256) key is current. (If you pick RSA instead, set
   `SUPABASE_JWT_ALG=RS256` on Render in step 4.) Escalate refuses HS256 tokens.
5. **Connection string:** click **Connect** at the top of the project page → tab
   **Connection String** → type **URI** → method **Session pooler** (port **5432**; not
   "Direct connection" and not "Transaction pooler"). Copy it and replace `[YOUR-PASSWORD]` with
   value **D** → value **E**.
6. Nothing else to create here: the API makes its tables (in a private `escalate` schema, not
   visible to Supabase's public API) and the private `evidence` storage bucket the first time it
   starts.

## 2. Google sign-in (Google Cloud console)

1. Go to <https://console.cloud.google.com> and sign in with the Google account that will own
   the beta. Accept the terms if asked.
2. Top bar: project picker → **New project** → name `escalate-beta` → **Create**, then make sure
   it is selected in the project picker.
3. Search bar: type **Google Auth Platform** and open it → **Get started**:
   - App name: `Escalate beta`; User support email: your email → **Next**.
   - Audience: **External** → **Next**.
   - Contact information: your email → **Next** → tick the agreement → **Create**.
4. **Audience** (left menu): leave *Publishing status* at **Testing**. Under **Test users** click
   **Add users** and add every email you will invite (Google allows up to 100 in testing mode).
   Only these accounts can sign in while the app is in testing.
5. **Data access** (left menu) → **Add or remove scopes** → tick `.../auth/userinfo.email`,
   `.../auth/userinfo.profile` and `openid` → **Update** → **Save**. Nothing else.
6. **Clients** (left menu) → **Create client**:
   - Application type: **Web application**; Name: `escalate-beta`.
   - **Authorized JavaScript origins:** leave empty for now (you add your Vercel URL in step 6).
   - **Authorized redirect URIs:** **Add URI** → `A/auth/v1/callback`, i.e. your Supabase project
     URL followed by `/auth/v1/callback`, for example
     `https://abcdefghijkl.supabase.co/auth/v1/callback`.
   - **Create**. Copy the **Client ID** → value **F** and the **Client secret** → value **G**
     (download the JSON or copy it now; Google may not show the secret again).
7. Back in Supabase: **Authentication → Sign In / Providers → Google** → turn it **on** → paste
   **Client ID** (F) and **Client Secret** (G) → **Save**. Leave other providers off. (Email
   sign-up can stay on or off; the beta only offers the Google button.)

## 3. Groq (the AI)

1. Go to <https://console.groq.com> → sign in.
2. **Zero Data Retention:** open **Settings → Data Controls** and turn on **Zero Data
   Retention** (for the whole organization). The beta's privacy policy says Groq keeps no data:
   don't skip this.
3. **API Keys → Create API Key** → name `escalate-beta` → copy it → value **H** (shown once).
4. Models: the Render blueprint uses `llama-3.3-70b-versatile` (smart) and
   `llama-3.1-8b-instant` (fast). Check they are still listed under **Docs → Models**; if Groq
   retired one, pick a current large and small model and use their ids in step 4.

## 4. The API on Render

1. **Make the encryption key** (value **I**). Open **Terminal** (Spotlight → "Terminal") and run:

   ```bash
   python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
   ```

   Copy the line it prints. Keep it safe: without it, uploaded evidence can never be decrypted.
2. Go to <https://render.com> → sign in with GitHub → allow access to the `escalate` repository.
3. **New + → Blueprint** → pick the `escalate` repository → branch `main` → Render reads
   `render.yaml` and shows the service **escalate-api** (Docker, Free, Frankfurt).
4. Fill in the values it asks for:

   | Render variable | Value |
   | --- | --- |
   | `DATABASE_URL` | E (session pooler string, with your password) |
   | `SUPABASE_URL` | A |
   | `SUPABASE_SERVICE_ROLE_KEY` | C |
   | `FERNET_KEY` | I |
   | `LLM_API_KEY` | H |
   | `WEB_ORIGIN` | `https://escalate-beta.vercel.app` (fix it in step 6 if Vercel gives a different URL) |
   | `ALLOWED_HOSTS` | `escalate-api.onrender.com` (fix it in step 5 if Render gives a different host) |

   `TICK_SECRET` is generated by Render. The other variables already have values from
   `render.yaml`. Click **Apply** / **Deploy Blueprint**.
5. The first build takes about 10 minutes. Then open the service: the URL at the top (e.g.
   `https://escalate-api.onrender.com`) is value **J**. If its host differs from what you typed
   in `ALLOWED_HOSTS`, go to **Environment**, correct `ALLOWED_HOSTS` to the host only (no
   `https://`, no `/`), **Save, rebuild and deploy**.
6. **Check it:** open `J/health` in your browser (e.g. `https://escalate-api.onrender.com/health`).
   It should show `{"ok":true}`. The first visit after a quiet period takes up to a minute (the
   free plan sleeps). If the deploy failed, open **Logs**: a line starting
   `DEPLOY_MODE=hosted refuses to start` lists exactly which variable is missing or wrong (names
   only, never values).
7. Copy `TICK_SECRET`: **Environment** → `TICK_SECRET` → reveal → copy → value **K**.

## 5. The web app on Vercel (second project: `escalate-beta`)

The public demo keeps its own Vercel project; this is a **second** project from the same repo.

1. Go to <https://vercel.com> → sign in with GitHub → **Add New… → Project** → **Import** the
   `escalate` repository (again, even if the demo already uses it).
2. **Project Name:** `escalate-beta`. **Root Directory:** **Edit** → choose `web`.
   Framework: Next.js. Leave the build command alone (`web/vercel.json` runs
   `npm run build:vercel`, which builds the beta when it sees `NEXT_PUBLIC_DEPLOY_MODE=hosted`
   and the demo otherwise).
3. **Environment Variables** (all are public by design: they end up in the browser):

   | Name | Value |
   | --- | --- |
   | `NEXT_PUBLIC_DEPLOY_MODE` | `hosted` |
   | `NEXT_PUBLIC_API_URL` | J (e.g. `https://escalate-api.onrender.com`, no trailing `/`) |
   | `NEXT_PUBLIC_SUPABASE_URL` | A |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | B (the **publishable**/anon key, never the secret key) |
   | `NEXT_PUBLIC_OPERATOR_NAME` | your name, as shown in the privacy policy and terms |
   | `NEXT_PUBLIC_CONTACT_EMAIL` | the address people can write to about their data |

   **Do not add any other variable here**, and never a secret: the build fails on purpose if a
   secret-looking value or a `NEXT_PUBLIC_…KEY/SECRET` variable other than these two Supabase
   ones would reach the browser.
4. **Deploy.** When it finishes, the domain shown (e.g. `https://escalate-beta.vercel.app`) is
   value **L**. If it differs from what you put in `WEB_ORIGIN` on Render, update `WEB_ORIGIN`
   on Render (exact origin, `https://…`, no trailing `/`) and redeploy the API.
5. **Settings → General → Node.js Version:** 22.x.

## 6. Connect the pieces

1. **Supabase → Authentication → URL Configuration:**
   - **Site URL:** L (e.g. `https://escalate-beta.vercel.app`).
   - **Redirect URLs → Add URL:** `L/auth/callback`
     (e.g. `https://escalate-beta.vercel.app/auth/callback`). Save.
2. **Google Auth Platform → Clients → escalate-beta:** under *Authorized JavaScript origins* add
   L → **Save**.
3. **GitHub secrets for the hourly tick:** on github.com open your `escalate` repository →
   **Settings → Secrets and variables → Actions → New repository secret**, twice:
   - `TICK_URL` = `J/internal/tick` (e.g. `https://escalate-api.onrender.com/internal/tick`)
   - `TICK_SECRET` = K
   Then **Actions → tick → Run workflow** once: it should finish green and print `HTTP 200`.
   (Until both secrets exist the workflow does nothing and still succeeds.)

## 7. Database tables and invites

The API creates and upgrades its tables when it starts, so after step 4 they exist. To run the
migrations yourself (optional, e.g. after an upgrade), and to invite people, use your Mac with
the repository checked out (`make setup` not needed, only `uv`):

```bash
cd escalate
uv sync
make migrate-hosted                     # optional: create/upgrade the tables
make invite EMAIL=you@gmail.com          # invite yourself first
make invite EMAIL=friend@example.com
make invites                             # list everyone invited
make uninvite EMAIL=friend@example.com   # remove an invite
```

Each command asks: *Paste the Supabase session pooler connection string (input hidden)*. Paste
value **E** and press Enter: nothing appears while you paste, and it is not saved in your shell
history. Remember the invited emails must also be **test users** in Google (step 2.4) while the
Google app is in testing mode.

## 8. Smoke test (with a made-up case)

1. Open L in a private browser window → **Sign in** → **Continue with Google** → choose an
   invited account.
2. You should see **Before you start** (the consent page) → **I understand and agree**.
3. The header shows your email and **Sign out**. Settings shows **Your account** (no AI or email
   settings).
4. **New case** with fictional data, e.g. "I bought a kettle from Example Shop for 40 GBP on
   1 October 2026, order EX-1001. It broke after a week and they refuse a refund." Upload a small
   made-up receipt (a `.txt` file is fine). Start it.
5. Review the draft and **Approve** it. You should get **Open in my email app**, **Copy
   letter**, **Download PDF** and **I've sent it**. Don't actually email a real company: click
   **I've sent it**; the case now waits for a reply.
6. Settings → **Export my data** downloads a zip with your case.
7. Sign in with a Google account that is **not** invited: you should see **You're on the
   waitlist**.
8. Clean up: delete the test case, or Settings → **Delete my account** (type `DELETE`) to check
   that deletion works end to end (you can invite yourself again afterwards).

## Day-to-day

- **Limits** (Render → Environment): `MAX_OPEN_CASES` (3), `AI_CALLS_PER_DAY` (40 per user),
  `GLOBAL_AI_CALLS_PER_DAY` (1000 for everyone; then users see "The AI is busy today, try
  tomorrow").
- **Cold starts:** the free API sleeps after about 15 idle minutes; the web app shows "Waking
  the server…" and retries for about 90 seconds.
- **Updates:** `render.yaml` sets `autoDeploy: false`; click **Manual Deploy** on Render after
  merging changes. Vercel redeploys on every push to `main`.
- **Rotating a secret:** make a new one at its source, replace it on Render (or GitHub), redeploy.
  Never rotate `FERNET_KEY` without a plan: existing evidence can only be decrypted with the old
  key.
- **Free-tier limits change.** Check each provider's current free plan before inviting more
  people. Supabase pauses free projects after a period without activity. The hourly tick queries
  the database, which should keep it active, but check the dashboard now and then.
