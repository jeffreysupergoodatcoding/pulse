# Dataset license note

The Pulse code is released under the MIT License (see `/LICENSE`).

The Twitter content in `*.jsonl` files is **separately** subject to
X (Twitter) Developer Terms. The data is published here under fair-use
academic-research provisions. The following terms apply to the dataset
specifically (in addition to MIT for the schema, scripts, and structure):

- The dataset must not be used for training commercial models
- Authors are anonymized via SHA-256 hash of original author IDs; no
  usernames are retained except in the `author_metadata.username` field
  for traceability — do not redistribute usernames separately
- If a tweet is later deleted from the source platform, or the author
  requests removal, the corresponding line in this dataset should be
  removed on request
- For maximum compliance with X/Twitter's developer terms, downstream
  researchers should:
  1. Use only the **derived data** (sentiment scores, aggregates, tweet
     IDs) from `aggregate_results.json` for redistribution
  2. Use the JSONL `content` fields **only for their own analysis**, not
     republish them
- If you need a strictly ToS-clean version, contact the repository
  maintainer for a tweet-IDs-only export that requires rehydration via
  the Twitter API.

See `dataset/README.md` for the full schema and methodology.
