"""Mail merge: render templates against contact rows, write drafts to DB,
optionally export as .eml files or a JSON manifest the Gmail MCP can consume."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, StrictUndefined, UndefinedError

from .db import DB, Activity


@dataclass
class RenderedDraft:
    contact_id: int
    to_email: str
    subject: str
    body: str
    contact_name: str
    company_name: str | None


class MailMerge:
    def __init__(self, db: DB, from_name: str | None = None,
                 from_email: str | None = None):
        self.db = db
        self.from_name = from_name
        self.from_email = from_email
        self.env = Environment(undefined=StrictUndefined, autoescape=False)

    # ---------- template management ----------

    def save_template(self, name: str, subject: str, body: str,
                      description: str | None = None) -> int:
        return self.db.upsert_template(name, subject, body, description)

    def list_templates(self) -> list[dict]:
        return self.db.list_templates()

    def detect_variables(self, text: str) -> list[str]:
        return sorted(set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", text)))

    # ---------- rendering ----------

    def render_one(self, contact_id: int, template_name: str,
                   extra_context: dict | None = None) -> RenderedDraft:
        tpl = self.db.get_template(template_name)
        if not tpl:
            raise ValueError(f"template {template_name!r} not found")
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError(f"contact {contact_id} not found")
        if not contact.get("email"):
            raise ValueError(f"contact {contact_id} has no email")

        ctx = self._contact_context(contact)
        if extra_context:
            ctx.update(extra_context)

        try:
            subject = self.env.from_string(tpl["subject"]).render(**ctx)
            body = self.env.from_string(tpl["body"]).render(**ctx)
        except UndefinedError as e:
            raise ValueError(
                f"template variable missing for {contact.get('email')}: {e}"
            ) from e

        return RenderedDraft(
            contact_id=contact_id,
            to_email=contact["email"],
            subject=subject,
            body=body,
            contact_name=f"{contact.get('first_name','')} "
                         f"{contact.get('last_name','')}".strip(),
            company_name=contact.get("company_name"),
        )

    def merge(self, contact_ids: list[int], template_name: str,
              extra_context: dict | None = None,
              skip_missing_vars: bool = True) -> tuple[list[RenderedDraft], list[dict]]:
        """Render template against many contacts. Returns (drafts, errors)."""
        drafts: list[RenderedDraft] = []
        errors: list[dict] = []
        for cid in contact_ids:
            try:
                drafts.append(self.render_one(cid, template_name, extra_context))
            except ValueError as e:
                if not skip_missing_vars:
                    raise
                errors.append({"contact_id": cid, "error": str(e)})
        return drafts, errors

    # ---------- persistence + export ----------

    def save_drafts(self, drafts: list[RenderedDraft],
                    template_name: str | None = None) -> list[int]:
        ids: list[int] = []
        for d in drafts:
            draft_id = self.db.save_draft(
                contact_id=d.contact_id, template_name=template_name,
                to_email=d.to_email, subject=d.subject, body=d.body,
            )
            ids.append(draft_id)
            self.db.log_activity(Activity(
                kind="draft_created", direction="outbound",
                contact_id=d.contact_id, subject=d.subject, body=d.body,
                occurred_at=datetime.now(timezone.utc).isoformat(),
                metadata={"template": template_name, "draft_id": draft_id},
            ))
        return ids

    def export_eml(self, drafts: list[RenderedDraft], out_dir: Path | str) -> list[Path]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for d in drafts:
            msg = EmailMessage()
            msg["To"] = d.to_email
            msg["Subject"] = d.subject
            if self.from_email:
                msg["From"] = (f"{self.from_name} <{self.from_email}>"
                               if self.from_name else self.from_email)
            msg.set_content(d.body)
            slug = re.sub(r"[^a-z0-9]+", "-",
                          (d.contact_name or d.to_email).lower()).strip("-")
            path = out / f"{d.contact_id:05d}-{slug}.eml"
            path.write_bytes(bytes(msg))
            paths.append(path)
        return paths

    def export_manifest(self, drafts: list[RenderedDraft],
                        path: Path | str) -> Path:
        """Write JSON the Gmail MCP server's create_draft tool can consume."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "from_email": self.from_email,
            "drafts": [
                {
                    "contact_id": d.contact_id,
                    "to": d.to_email,
                    "subject": d.subject,
                    "body": d.body,
                    "contact_name": d.contact_name,
                    "company_name": d.company_name,
                }
                for d in drafts
            ],
        }
        out.write_text(json.dumps(payload, indent=2))
        return out

    # ---------- helpers ----------

    @staticmethod
    def _contact_context(contact: dict) -> dict:
        first = contact.get("first_name") or ""
        last = contact.get("last_name") or ""
        return {
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}".strip(),
            "title": contact.get("title") or "",
            "email": contact.get("email") or "",
            "company": contact.get("company_name") or "",
            "company_domain": contact.get("company_domain") or "",
        }
