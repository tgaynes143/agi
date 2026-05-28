"""Relationship memory.

Two layers:
  - log() — append any interaction (email, call, meeting, note) to the activity table
  - ask() — answer natural-language questions about a contact/company using
            Claude as the reasoner over the activity history. Falls back to
            keyword search if no API key is set.

Prompt caching is on: the long activity history for a given contact is sent as
a cache_control breakpoint so repeated questions about the same contact stay cheap.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from .db import DB, Activity

DEFAULT_MODEL = "claude-sonnet-4-6"


class Memory:
    def __init__(self, db: DB, anthropic_api_key: str | None = None,
                 model: str = DEFAULT_MODEL):
        self.db = db
        self.api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

    # ---------- write side ----------

    def log(self, kind: str, body: str,
            contact_id: int | None = None,
            company_id: int | None = None,
            subject: str | None = None,
            direction: str | None = None,
            occurred_at: str | None = None,
            metadata: dict[str, Any] | None = None) -> int:
        return self.db.log_activity(Activity(
            kind=kind, body=body, subject=subject,
            contact_id=contact_id, company_id=company_id,
            direction=direction,
            occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        ))

    def log_note(self, body: str, contact_id: int | None = None,
                 company_id: int | None = None) -> int:
        return self.log("note", body, contact_id=contact_id,
                        company_id=company_id, direction="internal")

    def log_email_sent(self, contact_id: int, subject: str, body: str) -> int:
        return self.log("email_sent", body, subject=subject,
                        contact_id=contact_id, direction="outbound")

    def log_email_received(self, contact_id: int, subject: str, body: str) -> int:
        return self.log("email_received", body, subject=subject,
                        contact_id=contact_id, direction="inbound")

    def log_call(self, contact_id: int, body: str) -> int:
        return self.log("call", body, contact_id=contact_id, direction="outbound")

    def log_meeting(self, body: str, contact_id: int | None = None,
                    company_id: int | None = None) -> int:
        return self.log("meeting", body, contact_id=contact_id,
                        company_id=company_id)

    # ---------- read side ----------

    def timeline(self, contact_id: int | None = None,
                 company_id: int | None = None, limit: int = 200) -> list[dict]:
        if contact_id is not None:
            return self.db.activities_for_contact(contact_id, limit=limit)
        if company_id is not None:
            return self.db.activities_for_company(company_id, limit=limit)
        return self.db.all_activities(limit=limit)

    def ask(self, question: str,
            contact_id: int | None = None,
            company_id: int | None = None,
            history_limit: int = 100) -> dict:
        """Answer a question against the activity log.

        Returns {answer: str, used_llm: bool, activities_considered: int}.
        """
        activities = self.timeline(contact_id=contact_id, company_id=company_id,
                                   limit=history_limit)
        if not activities:
            return {"answer": "No activity recorded yet.",
                    "used_llm": False, "activities_considered": 0}

        if self.api_key:
            return self._ask_llm(question, activities, contact_id, company_id)
        return self._ask_keyword(question, activities)

    # ---------- LLM path ----------

    def _client_lazy(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def _ask_llm(self, question: str, activities: list[dict],
                 contact_id: int | None, company_id: int | None) -> dict:
        subject_info = self._subject_block(contact_id, company_id)
        history = self._format_activities(activities)

        system = [
            {
                "type": "text",
                "text": (
                    "You are a CRM memory assistant for a commercial insurance "
                    "broker focused on the middle market. Answer questions "
                    "about the relationship from the activity log. Be specific: "
                    "cite dates and pull quotes when relevant. If the log does "
                    "not contain the answer, say so plainly."
                ),
            },
            {
                "type": "text",
                "text": f"## Subject\n{subject_info}\n\n## Activity log\n{history}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        client = self._client_lazy()
        resp = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return {
            "answer": text,
            "used_llm": True,
            "activities_considered": len(activities),
            "model": self.model,
            "usage": {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0),
                "cache_create": getattr(resp.usage, "cache_creation_input_tokens", 0),
            },
        }

    # ---------- fallback path ----------

    def _ask_keyword(self, question: str, activities: list[dict]) -> dict:
        terms = [t for t in re.findall(r"[A-Za-z0-9']{3,}", question.lower())
                 if t not in STOPWORDS]
        scored = []
        for a in activities:
            hay = " ".join(str(a.get(k) or "") for k in ("subject", "body", "kind")).lower()
            score = sum(hay.count(t) for t in terms)
            if score > 0:
                scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [a for _, a in scored[:5]]
        if not top:
            return {"answer": "No matching activity found.",
                    "used_llm": False, "activities_considered": len(activities)}
        lines = ["Top matches:"]
        for a in top:
            when = (a.get("occurred_at") or "")[:10]
            head = a.get("subject") or (a.get("body") or "")[:80]
            lines.append(f"- [{when}] {a.get('kind')}: {head}")
        return {"answer": "\n".join(lines),
                "used_llm": False, "activities_considered": len(activities)}

    # ---------- helpers ----------

    def _subject_block(self, contact_id: int | None,
                       company_id: int | None) -> str:
        if contact_id is not None:
            c = self.db.get_contact(contact_id) or {}
            return json.dumps({
                "type": "contact", "id": contact_id,
                "name": f"{c.get('first_name','')} {c.get('last_name','')}".strip(),
                "title": c.get("title"), "email": c.get("email"),
                "company": c.get("company_name"),
            }, indent=2)
        if company_id is not None:
            co = self.db.get_company(company_id) or {}
            return json.dumps({
                "type": "company", "id": company_id,
                "name": co.get("name"), "domain": co.get("domain"),
                "industry": co.get("industry"),
                "revenue_band": co.get("revenue_band"),
                "lines": co.get("lines_of_coverage"),
            }, indent=2)
        return '{"type": "all"}'

    @staticmethod
    def _format_activities(activities: list[dict]) -> str:
        rows = []
        for a in activities:
            when = (a.get("occurred_at") or "")[:19]
            kind = a.get("kind", "?")
            who = ""
            if a.get("first_name") or a.get("last_name"):
                who = f" {a.get('first_name','')} {a.get('last_name','')}".strip()
            subj = a.get("subject") or ""
            body = (a.get("body") or "").strip()
            head = f"[{when}] {kind}{who}"
            if subj:
                head += f" — {subj}"
            rows.append(head + "\n" + body)
        return "\n\n".join(rows)


STOPWORDS = {
    "the", "and", "for", "with", "what", "when", "where", "did", "does",
    "have", "has", "had", "from", "this", "that", "they", "them", "their",
    "are", "was", "were", "been", "being", "about", "into", "over", "under",
    "than", "then", "also", "just", "very", "much", "more", "less", "some",
    "any", "all", "you", "your", "our", "ours", "his", "hers", "him", "her",
}
