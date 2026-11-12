# Data Cleaner (sample project)

> **Sample project.** Built to show how I approach data cleaning jobs. It runs on a synthetic dataset in `sample_data/`, not client data.

A reusable Python script that cleans CSV, Excel and JSON datasets, plus a small Django API around it.

It removes duplicates, handles missing values, fixes numbers and dates stored as text, merges inconsistent category labels, and normalises user-written text (HTML, URLs, emoji, repeated characters). Every run produces a report of what changed.

## Setup

Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

## Run the script

```bash
python -m cleaner sample_data/messy_reviews.csv
```

That writes `sample_data/messy_reviews_cleaned.csv` using automatic settings. To control the run:

```bash
python -m cleaner input.xlsx -o cleaned.csv -c config.example.json -r report.json
```

| Flag | Meaning |
| --- | --- |
| `-o` | Output file. The extension sets the format: `.csv .tsv .xlsx .json .jsonl` |
| `-c` | JSON config file |
| `-r` | Save the cleaning report as JSON |

Use it from Python:

```python
from cleaner import clean, read_table, write_table

df, report = clean(read_table("input.csv"), {"date_columns": ["Created"]})
write_table(df, "cleaned.csv")
```

## What it does, in order

1. Renames columns to `snake_case` and makes them unique.
2. Trims whitespace. Turns `N/A`, `null`, `none`, `-`, `?` and blanks into real missing values.
3. Drops empty rows, empty columns, and any columns you list.
4. Converts numbers stored as text (`"$1,200"`, `" 4 "`). Values with leading zeros (zip codes, phone numbers) stay as text.
5. Converts dates to `YYYY-MM-DD`. Impossible dates such as `2026-02-30` become missing and are listed in the report.
6. Merges label variants (`USA`, `usa`, `USA ` become one). Your own mappings handle the rest (`U.S.A.` to `USA`).
7. Cleans free text into a new `<column>_clean` column. The original text is kept.
8. Drops rows that miss required fields, are mostly empty, or have text that is too short.
9. Fills missing values, only if you ask for it.
10. Removes duplicates. Text is compared ignoring case, punctuation, spacing and markup. ID columns are ignored, so the same record under two IDs counts as a duplicate.

## Config

Every key is optional. Column names can be written as they appear in your file. Unknown keys are rejected so typos do not pass silently.

| Key | Default | Meaning |
| --- | --- | --- |
| `drop_columns` | `[]` | Columns to remove |
| `id_columns` | auto | Columns ignored when looking for duplicates |
| `text_columns` | auto | Free-text columns to clean |
| `date_columns` | auto | Columns to convert to ISO dates |
| `numeric_columns` | `[]` | Columns to force to numbers |
| `keep_as_text` | `[]` | Columns that must never become numbers |
| `title_case_columns` | `[]` | Columns to title-case, such as names |
| `required_columns` | `[]` | Rows missing any of these are dropped |
| `max_missing_ratio` | `0.7` | Drop rows emptier than this. `1` turns it off |
| `numeric_fill` | `"none"` | `none`, `median`, `mean` or `zero` |
| `fill_values` | `{}` | `{"column": value}` used for missing cells |
| `dayfirst` | `false` | Read `03/04/2026` as 3 April |
| `infer_dates`, `infer_numeric` | `true` | Turn automatic detection off |
| `category_maps` | `{}` | `{"column": {"from": "to"}}` |
| `standardize_categories` | `true` | Merge case and spacing variants |
| `keep_raw_text` | `true` | Keep the original text next to the cleaned one |
| `lowercase_text`, `strip_emoji`, `strip_handles` | `true` | Text cleaning switches |
| `mask_pii` | `false` | Replace emails and phone numbers with `[email]` and `[phone]` |
| `add_tokens` | `false` | Add a `<column>_tokens` column of words |
| `remove_stopwords` | `false` | Drop common English words from the tokens |
| `min_text_length` | `0` | Drop rows whose cleaned text is shorter |
| `drop_duplicates` | `true` | Remove duplicates |
| `dedupe_subset` | all non-ID columns | Columns that define a duplicate |

`config.example.json` is a working example for the sample data.

## Run the API

```bash
cd api
DJANGO_DEBUG=1 python manage.py runserver
```

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health/` | Returns `{"status": "ok"}` |
| `POST /api/clean/` | Send `file` as multipart form data. Optional `config` field holds the JSON config. Returns `{"report": ..., "rows": [...]}` |
| `POST /api/clean/?download=csv` | Same input. Returns the cleaned data as a CSV file |

```bash
curl -F file=@../sample_data/messy_reviews.csv \
     -F 'config={"date_columns": ["Submitted At"]}' \
     http://127.0.0.1:8000/api/clean/
```

Errors come back as `{"error": "..."}` with status 400, 401, 405 or 413.

Environment variables:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required unless `DJANGO_DEBUG=1` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names. Default `localhost,127.0.0.1` |
| `CLEANER_API_KEY` | If set, requests must send it in the `X-API-Key` header |
| `CLEANER_MAX_UPLOAD_MB` | Upload limit. Default 10 |

The API keeps nothing: no database, no files on disk. For production, run it behind gunicorn and HTTPS and set `CLEANER_API_KEY`.

## Tests

```bash
python -m unittest discover -s tests -t .
cd api && DJANGO_DEBUG=1 python manage.py test
```

## Limits to know about

- The text cleaning is rule-based and tuned for English. There is no spell-checking, stemming or lemmatisation.
- Duplicate detection finds the same record written differently. It does not find paraphrases or typos.
- Ambiguous dates such as `03/04/2026` follow the `dayfirst` setting for the whole column.
- A column is treated as numeric when 90% of its values parse. The rest become missing and are listed in the report. Use `keep_as_text` to prevent this.
- Title-casing turns `McDonald` into `Mcdonald`.
- The whole file is loaded into memory. A 116,000-row file cleaned in about 5 seconds in testing.
- The sample data is synthetic.
