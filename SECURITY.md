# Security

## What `.gitignore` can and cannot do

- **Ignored files are not committed going forward**, but anything **already pushed** to GitHub remains in **git history** until you rewrite history (e.g. `git filter-repo`) and force-push. Making the repo public does **not** retroactively hide past commits.
- **You cannot “gitignore the whole project”** and still have a useful public repository: Git only publishes **tracked** content. Ignoring everything would mean nothing to clone and no workflows from your tree.
- **GitHub Pages** serves the **artifact** produced by Actions. Scraped JSON is **no longer committed**; it is generated in CI and bundled into the Pages deploy only.

## API keys and environment files

- **Never commit** `.env`, real API keys, tokens, or passwords to the repository.
- `.env` is listed in `.gitignore`. Use **`.env.example`** only as a template locally.
- For **GitHub Actions**, store secrets under **Settings → Secrets and variables → Actions**:
  - `SAM_GOV_API_KEY`
  - `GEMINI_API_KEY`

If a key was ever pasted into chat, a ticket, or a non-private file, **rotate it** at the provider (SAM.gov, Google AI Studio) and update secrets only.

## Dashboard access phrase (GitHub Pages / static hosting)

The dashboard uses a **browser-only** check before showing the UI. The repository stores only a **SHA-256 hash** of the access phrase in `dashboard/app.js` (not the phrase itself). To **change the phrase**, pick a new secret, compute its hash, and update the constant:

```bash
printf 'your-new-secret-phrase' | shasum -a 256
```

Paste the hex digest into `ACCESS_PHRASE_HASH_HEX` in `dashboard/app.js`, commit, and redeploy.

**Important limitations:**

- Anyone can still request **`data.json`** directly by URL unless you add **edge or origin** protection (e.g. [Cloudflare Access](https://www.cloudflare.com/products/zero-trust/access/), Netlify password protection, signed URLs, or private hosting).
- Determined users can bypass client-side UI checks via devtools.

Treat the gate as **casual access control**, not a substitute for server-side authentication.

## Public repository checklist

- [ ] No `.env` in git (`git ls-files .env` should be empty).
- [ ] No keys in tracked JSON, YAML, or source (search for `AIza`, `SAM-`, `Bearer `).
- [ ] GitHub Actions secrets used for scraper runs, not hardcoded keys.

## Reporting

If you find a leaked secret in this repo’s history, revoke the key immediately and open an issue (or contact the maintainer) so history can be cleaned if needed.
