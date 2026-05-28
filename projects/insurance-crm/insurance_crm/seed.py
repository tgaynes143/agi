"""Seed default templates for insurance middle-market outreach."""

from .db import DB

DEFAULTS = [
    {
        "name": "cold_intro_risk_manager",
        "description": "Cold intro to a Risk Manager / VP Risk at a middle market firm.",
        "subject": "Quick question on {{ company }}'s casualty program",
        "body": (
            "Hi {{ first_name }},\n\n"
            "I work with middle-market companies on their property & casualty "
            "and executive risk placements. A few of our {{ company }}-sized "
            "clients have recently benchmarked their primary GL and umbrella "
            "and found 10–20% in premium savings without ceding coverage.\n\n"
            "If a 20-minute benchmark on {{ company }}'s next renewal would be "
            "useful, I'm happy to put one together. No obligation.\n\n"
            "Best,\n"
        ),
    },
    {
        "name": "cold_intro_cfo",
        "description": "Cold intro to a CFO/Controller framing TCOR.",
        "subject": "{{ company }} — TCOR benchmark for your next renewal",
        "body": (
            "Hi {{ first_name }},\n\n"
            "Quick note from one CFO conversation to another: most of the "
            "middle-market finance teams I work with are surprised to see how "
            "much of their total cost of risk (TCOR) sits in retained losses "
            "rather than premium. A clean benchmark usually surfaces 1–2 "
            "structural changes worth real dollars.\n\n"
            "Would a short call before {{ company }}'s next renewal be useful?\n\n"
            "Best,\n"
        ),
    },
    {
        "name": "renewal_followup",
        "description": "Pre-renewal check-in 90 days out.",
        "subject": "90 days to {{ company }}'s renewal — quick check-in",
        "body": (
            "Hi {{ first_name }},\n\n"
            "We're about 90 days out from {{ company }}'s renewal. A few items "
            "worth pre-empting on the underwriter call:\n"
            "  • updated revenue + headcount\n"
            "  • any new locations, products, or contract terms\n"
            "  • loss control items from last cycle\n\n"
            "Want me to send a one-pager you can fill in?\n\n"
            "Thanks,\n"
        ),
    },
    {
        "name": "post_meeting_recap",
        "description": "Post-meeting recap; recipient is the buyer.",
        "subject": "Recap — {{ company }} discussion",
        "body": (
            "Hi {{ first_name }},\n\n"
            "Thanks for the time today. Quick recap of what we agreed:\n\n"
            "  • [action item 1]\n"
            "  • [action item 2]\n"
            "  • [action item 3]\n\n"
            "I'll circle back on {{ company }}'s submissions by end of week. "
            "Let me know if I missed anything.\n\n"
            "Best,\n"
        ),
    },
]


def seed_templates(db: DB) -> int:
    n = 0
    for t in DEFAULTS:
        db.upsert_template(t["name"], t["subject"], t["body"], t["description"])
        n += 1
    return n
