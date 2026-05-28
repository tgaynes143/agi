"""Smoke tests — no network, no API keys required."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from insurance_crm import DB, MailMerge, Memory
from insurance_crm.db import Company, Contact
from insurance_crm.seed import seed_templates


def test_full_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db = DB(Path(tmp) / "crm.db")
        n = seed_templates(db)
        assert n == 4
        assert {t["name"] for t in db.list_templates()} >= {
            "cold_intro_risk_manager", "cold_intro_cfo",
            "renewal_followup", "post_meeting_recap",
        }

        company_id = db.upsert_company(Company(
            name="Acme Manufacturing", domain="acmemfg.com",
            industry="Manufacturing", revenue_band="$50M-$250M",
        ))
        contact_id = db.upsert_contact(Contact(
            first_name="Jane", last_name="Doe", title="Risk Manager",
            email="jane.doe@acmemfg.com", email_confidence=0.9,
            company_id=company_id, source="test",
        ))

        merger = MailMerge(db, from_name="Broker", from_email="broker@x.com")
        drafts, errors = merger.merge([contact_id], "cold_intro_risk_manager")
        assert not errors
        assert len(drafts) == 1
        d = drafts[0]
        assert "Jane" in d.body
        assert "Acme Manufacturing" in d.body
        assert d.to_email == "jane.doe@acmemfg.com"

        ids = merger.save_drafts(drafts, "cold_intro_risk_manager")
        assert len(ids) == 1
        assert db.list_drafts()[0]["subject"] == d.subject

        eml_dir = Path(tmp) / "out"
        paths = merger.export_eml(drafts, eml_dir)
        assert paths and paths[0].exists()
        assert b"Subject: " in paths[0].read_bytes()

        manifest = merger.export_manifest(drafts, Path(tmp) / "manifest.json")
        assert manifest.exists()
        import json
        loaded = json.loads(manifest.read_text())
        assert loaded["drafts"][0]["to"] == "jane.doe@acmemfg.com"

        mem = Memory(db)
        mem.log_note("Asked for benchmark on GL/umbrella before Sept renewal.",
                     contact_id=contact_id)
        mem.log_call(contact_id, "Followed up — sent template loss runs request.")
        timeline = mem.timeline(contact_id=contact_id)
        assert len(timeline) >= 2
        # activity log also includes the draft_created entry
        kinds = {a["kind"] for a in timeline}
        assert {"note", "call", "draft_created"} <= kinds

        # Fallback keyword search (no API key)
        ans = mem.ask("benchmark", contact_id=contact_id)
        assert not ans["used_llm"]
        assert "benchmark" in ans["answer"].lower()

        print("OK — smoke test passed")


if __name__ == "__main__":
    test_full_roundtrip()
