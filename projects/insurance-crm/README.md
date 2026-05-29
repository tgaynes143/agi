# Insurance Middle-Market CRM

Lightweight contact hunting, mail merge, and relationship memory for commercial
insurance middle-market outreach. Python library + Streamlit UI.

## What it does

1. **Hunt contacts** — Free web sources only. Searches DuckDuckGo for LinkedIn
   profiles matching insurance-buyer titles at a target company (Risk Manager,
   VP Risk, CFO, Treasurer, GC, etc.), scrapes the company's About / Team /
   Contact pages for emails, and generates verified email permutations.
2. **Mail merge** — Jinja2 templates rendered against contact rows. Drafts get
   saved to a local SQLite DB and can be exported as `.eml` files or a JSON
   manifest that the Gmail MCP server can ingest as Gmail drafts.
3. **Relationship memory** — Append-only activity log (emails, calls, meetings,
   notes). Ask plain-English questions and Claude reads the relevant slice of
   history to answer. Prompt caching keeps repeated questions about the same
   contact cheap. Falls back to keyword search if no API key.

## Install

```bash
cd projects/insurance-crm
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

The DB lives at `data/crm.db`. Templates seed automatically on first run.

## Optional config

| Env var | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables LLM-backed `Memory.ask()` on the Memory page |
| `CRM_FROM_EMAIL` | Default From: address pre-filled in mail merge |

## Library use (no UI)

```python
from insurance_crm import DB, ContactHunter, MailMerge, Memory

db = DB()
hunter = ContactHunter(db)
hunter.hunt_company("Acme Manufacturing", domain="acmemfg.com",
                    industry="Manufacturing", revenue_band="$50M-$250M")

merger = MailMerge(db, from_name="Jane Broker", from_email="jane@brokerage.com")
contacts = [c["id"] for c in db.list_contacts() if c.get("email")]
drafts, errors = merger.merge(contacts, "cold_intro_risk_manager")
merger.save_drafts(drafts, "cold_intro_risk_manager")
merger.export_eml(drafts, "data/drafts")

mem = Memory(db)
mem.log_note("Risk Mgr open to benchmark, asked for callback in Sept.",
             contact_id=contacts[0])
print(mem.ask("What did we last hear from this contact?",
              contact_id=contacts[0])["answer"])
```

## Pushing drafts to Gmail

After running a merge, `data/drafts_manifest.json` contains a JSON list of
drafts. Ask Claude in this session to push them to Gmail drafts — it can iterate
the manifest and call the Gmail MCP `create_draft` tool for each item. Drafts
land in your Gmail account, ready to review and send.

## Template variables

Anywhere in a template's subject or body, use Jinja2 expressions:

- `{{ first_name }}` `{{ last_name }}` `{{ full_name }}`
- `{{ title }}`
- `{{ company }}` `{{ company_domain }}`
- `{{ email }}`

## Sample files

`examples/sample_prospects.xlsx` — 10 companies + 23 contacts across
manufacturing, healthcare, real estate, technology, hospitality, etc. Two
sheets (`Companies`, `Contacts`) with header columns matching the importer.

`examples/sample_outreach_letter.docx` — Microsoft Word letter with real
`MERGEFIELD` codes (`first_name`, `last_name`, `title`, `company`,
`merge_date`). In Word: **Mailings → Select Recipients → Use Existing List**,
pick the .xlsx, and choose the `Contacts` sheet. Word's native mail merge
fills the fields.

Regenerate either file: `python examples/generate_samples.py`

Bulk-load the Excel into the CRM:

```python
from insurance_crm import DB, import_xlsx
import_xlsx(DB(), "examples/sample_prospects.xlsx")
```

Or use the **Import XLSX** page in the Streamlit UI to upload any workbook
matching the same column layout.

## Default templates seeded

- `cold_intro_risk_manager` — to Risk Mgr / VP Risk
- `cold_intro_cfo` — to CFO / Controller, framed around TCOR
- `renewal_followup` — 90-day pre-renewal check-in
- `post_meeting_recap` — recap after a buyer meeting

Edit on the Templates page.

## Notes

- DuckDuckGo is the search backend (Google blocks scrapers). Results vary; the
  hunter saves whatever it finds plus the company's own scraped emails.
- The hunter does **not** SMTP-probe — that gets you flagged. It uses MX
  presence as a weak signal. Treat low-confidence emails as a hypothesis to
  verify before sending.
- All data is local. Nothing leaves the box except the LLM call when you ask a
  Memory question, and only the activity log for the queried subject is sent.
