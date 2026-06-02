# Elthio

Know what you're taking.

Elthio is a supplement safety platform — check drug-supplement
interactions, get a daily timing schedule, find the best value
products, and bring a clear summary to your doctor.

**Tagline:** "Are your supplements safe with your medications?"

## Features

- Med Check — 75 curated drug-supplement interaction rules
- Separation Coach — daily timing schedule with 38 absorption rules
- Shopping Agent — best value supplement finder across iHerb
- Basket Compare — cheapest retailer for your full supplement list
- Value Compare — brand comparison by cost per serving and form quality
- Stack Chemistry — synergy and conflict detection
- Supplement Passport — verified record to share with your doctor
- Visit Packet — one-page PDF for doctor appointments

## Tech Stack

- Python 3.11+ with built-in HTTP server
- Bright Data Web Unlocker for iHerb scraping
- OpenAI GPT-4o for supplement label extraction
- NIH DSLD API for official supplement verification
- Supabase for database and authentication

## Setup

1. Clone the repo
2. Create a virtual environment: `python -m venv .venv`
3. Activate: `.venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in your credentials
6. Run: `python server.py`
7. Open: `http://127.0.0.1:8765`

## Health Check

```powershell
python healthcheck.py
python healthcheck.py --full
```

## Project Structure

```
server.py              → HTTP server and API endpoints
elthio.html            → Main app
rules.py               → Supplement timing rules (38 rules)
separation_coach.py    → Daily schedule generator
med_check_engine.py    → Drug-supplement interaction checker
interactions_db.json   → 75 curated interaction rules
shopping_agent.py      → Shopping agent and value scoring
basket_compare.py      → Multi-retailer basket comparison
pipeline.py            → GPT-4o label extraction pipeline
search_products.py     → iHerb product search
supabase_client.py     → Database operations
healthcheck.py         → Pre-launch test suite (23 tests)
```

## Disclaimer

Educational only — not medical advice. Always follow your
prescription label and consult your pharmacist or doctor.
