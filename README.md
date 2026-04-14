# Job Alert Bot 🔍

Scrapes **YC Work at a Startup** and **Welcome to the Jungle** daily for data/AI roles in London or remote. Sends new matches to Telegram.

## Customise keywords

Edit `KEYWORDS` and `EXCLUDE_KEYWORDS` in `job_scraper.py`:

```python
KEYWORDS = [
    "data scientist",
    "analytics engineer",
    "llm",
    "semantic layer",
    # add more...
]
```

## How it works

- Scrapes YC jobs board (data + ML roles, UK/remote)
- Scrapes Welcome to the Jungle (data/AI roles, GB)
- Deduplicates against previously seen jobs (cached between runs)
- Sends Telegram message only for new matches
