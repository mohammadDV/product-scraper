# product-scraper

Python scraper for chain-store. Credentials and proxy live in `.env`. Decathlon is implemented first; other sites plug in as new parsers.

Fetching uses Camoufox (anti-detect Firefox) through the same proxy so Cloudflare challenges can complete. One retry is enabled by default.

```bash
cd product-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m camoufox fetch
cp .env.example .env   # then fill proxy + DB values
```

```bash
product-scraper check-proxy
product-scraper scrape "https://www.decathlon.com.tr/p/.../_/R-p-364504?mc=8941380" --dry-run
product-scraper scrape "https://www.decathlon.com.tr/p/.../_/R-p-364504?mc=8941380" --category-id 1
product-scraper run --limit 10 --brand decathlon
pytest
```
