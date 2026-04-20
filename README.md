# Arctic Defense Opportunity Scraper

An automated Python agent that collects defense solicitations (RFPs, RFIs, SBIRs, STTRs, OTAs, BAAs, CSOs) from 13+ government and defense innovation sources, filters them for arctic relevance using the Gemini API, and serves results through a web dashboard.

## Features

- **Multi-source collection**: Pulls opportunities from SAM.gov, Grants.gov, SBIR.gov, ERDCWERX, DSIP, DIU, DARPA, AFWERX, NavalX, SOFWERX, Navy SBIR, Army Applications Lab, and SpaceWERX
- **Arctic relevance filtering**: Uses Gemini AI to score opportunities for relevance to arctic/cold-region operations
- **Smart deduplication**: Identifies the same solicitation across multiple sources and merges data
- **Automated scheduling**: Runs twice daily via GitHub Actions (6 AM and 6 PM ET)
- **Static dashboard**: Responsive web interface deployed to GitHub Pages

## Security

**Do not commit** API keys, tokens, or a populated `.env` file. Use **GitHub Actions secrets** for automation and keep local keys only in `.env` (gitignored). See **[SECURITY.md](SECURITY.md)** for the full checklist, dashboard access limitations, and how to rotate credentials.

## Quick Start

### Prerequisites

- Python 3.11+
- SAM.gov API key (get one at [sam.gov](https://sam.gov))
- Gemini API key (get one at [Google AI Studio](https://aistudio.google.com))

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/arctic-defense-scraper.git
cd arctic-defense-scraper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for web scraping)
playwright install chromium
```

### Configuration

Copy the template and add your keys locally (this file is never committed):

```bash
cp .env.example .env
# Edit .env — do not commit it
```

Or export for the current shell:

```bash
export SAM_GOV_API_KEY="your-sam-gov-api-key"
export GEMINI_API_KEY="your-gemini-api-key"
```

### Run the Scraper

```bash
python -m scraper.main
```

This will:
1. Collect opportunities from all sources
2. Deduplicate across sources
3. Score for arctic relevance using Gemini
4. Save results to `data/opportunities.json` and `data/arctic_opportunities.json`

### View the Dashboard

Open `dashboard/index.html` in a browser, or serve it:

```bash
cd dashboard
python -m http.server 8000
```

Then visit http://localhost:8000 — you will be prompted for the **access phrase** (shared separately with your team; see `SECURITY.md`). Anyone who knows the direct URL to `data.json` can still download it unless you add edge protection (e.g. Cloudflare Access).

## Project Structure

```
arctic-defense-scraper/
├── .github/workflows/
│   └── scrape.yml              # GitHub Actions workflow
├── scraper/
│   ├── __init__.py
│   ├── main.py                 # Orchestrator
│   ├── models.py               # Pydantic data models
│   ├── config.py               # Configuration and constants
│   ├── dedup.py                # Deduplication logic
│   ├── llm_filter.py           # Gemini arctic relevance scoring
│   ├── collectors/             # Source-specific collectors
│   │   ├── base.py
│   │   ├── sam_gov.py
│   │   ├── grants_gov.py
│   │   ├── sbir_gov.py
│   │   ├── erdcwerx.py         # PRIORITY: CRREL CSO
│   │   ├── dsip.py
│   │   ├── diu.py
│   │   ├── darpa.py
│   │   ├── afwerx.py
│   │   ├── navalx.py
│   │   ├── sofwerx.py
│   │   ├── navy_sbir.py
│   │   ├── army_apps_lab.py
│   │   └── spacewerx.py
│   └── utils/
│       ├── http_client.py      # Rate-limited HTTP client
│       └── playwright_helpers.py
├── dashboard/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/
│   ├── opportunities.json      # All opportunities
│   ├── arctic_opportunities.json # Filtered for arctic relevance
│   └── run_log.json
├── tests/
├── requirements.txt
└── README.md
```

## Data Sources

### API-Based (Tier 1)
| Source | Endpoint | Auth Required |
|--------|----------|---------------|
| SAM.gov | Opportunities API v2 | API Key |
| Grants.gov | search2 API | None |
| SBIR.gov | Solicitations API | None |

### Web Scrapers (Tier 2)
| Source | Focus | Notes |
|--------|-------|-------|
| ERDCWERX | CRREL CSO (arctic priority!) | Cold regions research |
| DSIP | DoD SBIR/STTR topics | Authoritative source |
| DIU | CSOs via OTA | Defense innovation |
| DARPA | BAAs, Research Announcements | Has RSS feed |
| AFWERX | Air Force SBIR/STTR | Largest by volume |
| NavalX | Tech Bridge challenges | 15 regional hubs |
| SOFWERX | SOCOM challenges | Fast awards |
| Navy SBIR | Navy BAAs, Catapult | 3 BAAs/year |
| Army Apps Lab | Army Futures Command CSOs | Rapid prototyping |
| SpaceWERX | Space Force SBIR/STTR | Polar orbit relevance |

## Arctic Relevance Scoring

Opportunities are scored 0.0 to 1.0:

- **1.0**: Explicitly about arctic, polar, cold regions
- **0.8**: Strongly related (Alaska, CRREL, permafrost, ice)
- **0.6**: Moderately related (extreme environments, northern theaters)
- **0.4**: Tangentially related (general resilience tech)
- **0.2**: Weakly related (broad BAA with cold region applications)
- **0.0**: Not relevant

The dashboard shows opportunities with score ≥ 0.3 by default (adjustable).

### Arctic Keywords (auto-include)
arctic, polar, cold region, cold weather, extreme cold, permafrost, ice, icebreaker, high latitude, alaska, greenland, crrel, tundra, glacial

### Adjacent Keywords (send to LLM)
extreme environment, contested logistics, austere environment, expeditionary, NORTHCOM, EUCOM, INDOPACOM, all-domain, JADC2

## GitHub Actions Setup

1. Go to your repository Settings > Secrets and variables > Actions
2. Add these secrets:
   - `SAM_GOV_API_KEY`
   - `GEMINI_API_KEY`
3. **GitHub Pages source must be “GitHub Actions”** (Settings → Pages → Build and deployment → Source). If it is set to **Deploy from a branch** (for example `main` / `/`), GitHub will publish the whole repository and the site will look like a **README** or Jekyll default, not the dashboard. The workflows in `.github/workflows/deploy.yml` and `.github/workflows/scrape.yml` upload only the `dashboard/` folder as the site when Actions is the source.
4. After switching to GitHub Actions, run **Actions → “Deploy Dashboard to GitHub Pages” → Run workflow** once (or push a change under `dashboard/`) so a fresh artifact deploys.
5. The scrape workflow runs automatically at 6 AM and 6 PM ET, or trigger it manually from Actions.

If you must use **branch-based** Pages from `/` for some reason, open **`/dashboard/`** on the site (this repo includes a root `index.html` that redirects there) and keep a `.nojekyll` file at the publish root so Jekyll does not rewrite static assets.

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

## Estimated Costs

| Component | Monthly Cost |
|-----------|-------------|
| GitHub Actions | Free (under 2000 min/month) |
| GitHub Pages | Free |
| SAM.gov API | Free |
| Grants.gov API | Free |
| Gemini Flash API | ~$0.30 |
| **Total** | **~$0.30/month** |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
