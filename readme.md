### 3. Supabase tables
Run in Supabase SQL Editor:
```sql
create table links (
  id uuid default gen_random_uuid() primary key,
  url text not null,
  created_at timestamp with time zone default now()
);

create table handpicked_used (
  url text primary key,
  used_at timestamp with time zone default now()
);

alter table links enable row level security;
create policy "Allow insert" on links for insert with check (true);
create policy "Allow select" on links for select using (true);
```

### 4. YouTube auth (run once locally)
```bash
python upload.py
```
This opens a browser for Google login and generates `yt_token.json`. Paste its contents into the `GOOGLE_TOKEN` env var on Render.

## Running Locally
```bash
python orchestrator.py
```

## Deploying to Render

1. Push to GitHub (`.env`, `client_secrets.json`, `yt_token.json` are gitignored)
2. Render → **New → Background Worker**
3. Connect your GitHub repo
4. Add all env vars under **Environment**
5. Deploy — it runs every ~4 hours automatically forever

## Portfolio Priority Order

1. 📬 Supabase submissions (from your website)
2. ⭐ Handpicked list (100 curated portfolios, updated every 10-12 days)
3. 📦 Local JSON queue
4. 🔍 Extractor (scrapes GitHub, personalsit.es automatically)

## Disclaimer

This bot does not claim ownership of any portfolio shown. All rights belong to the original creators. Videos are for educational review purposes only. Owners can request removal by email.