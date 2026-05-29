"""Streamlit UI for the insurance middle-market CRM."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from insurance_crm import DB, ContactHunter, MailMerge, Memory, import_xlsx
from insurance_crm.seed import seed_templates

DATA_DIR = Path(__file__).parent / "data"
DRAFTS_DIR = DATA_DIR / "drafts"
MANIFEST_PATH = DATA_DIR / "drafts_manifest.json"

st.set_page_config(page_title="Insurance MM CRM", layout="wide")


@st.cache_resource
def get_db() -> DB:
    db = DB()
    if not db.list_templates():
        seed_templates(db)
    return db


def main():
    db = get_db()
    st.sidebar.title("Insurance MM CRM")
    page = st.sidebar.radio("View", [
        "Dashboard", "Hunt Contacts", "Import XLSX", "Contacts",
        "Mail Merge", "Drafts", "Memory / Recall", "Templates",
    ])

    if page == "Dashboard":
        page_dashboard(db)
    elif page == "Hunt Contacts":
        page_hunt(db)
    elif page == "Import XLSX":
        page_import(db)
    elif page == "Contacts":
        page_contacts(db)
    elif page == "Mail Merge":
        page_merge(db)
    elif page == "Drafts":
        page_drafts(db)
    elif page == "Memory / Recall":
        page_memory(db)
    elif page == "Templates":
        page_templates(db)


def page_dashboard(db: DB):
    st.header("Pipeline overview")
    companies = db.list_companies()
    contacts = db.list_contacts()
    drafts = db.list_drafts()
    activities = db.all_activities(limit=10)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Companies", len(companies))
    col2.metric("Contacts", len(contacts))
    col3.metric("Drafts pending", sum(1 for d in drafts if d["status"] == "pending"))
    col4.metric("Activities (last 10)", len(activities))

    st.subheader("Recent activity")
    if activities:
        st.dataframe(
            [{"when": (a.get("occurred_at") or "")[:19],
              "kind": a["kind"], "subject": a.get("subject"),
              "contact": f"{a.get('first_name','')} {a.get('last_name','')}".strip(),
              "company": a.get("company_name")} for a in activities],
            use_container_width=True,
        )
    else:
        st.info("No activity yet. Hunt contacts or log a note to start.")


def page_hunt(db: DB):
    st.header("Hunt contacts")
    st.caption("Free sources: DuckDuckGo for LinkedIn discovery + company-site "
               "scraping for emails. No API keys needed. Be patient — polite "
               "rate-limiting between requests.")

    with st.form("hunt_form"):
        company_name = st.text_input("Company name", placeholder="Acme Manufacturing")
        domain = st.text_input("Domain (optional)", placeholder="acmemfg.com")
        industry = st.selectbox("Industry", [
            "", "Manufacturing", "Healthcare", "Real Estate", "Technology",
            "Professional Services", "Construction", "Distribution",
            "Hospitality", "Financial Services", "Other",
        ])
        revenue_band = st.selectbox("Revenue band", [
            "", "$10M-$50M", "$50M-$250M", "$250M-$1B", "$1B+",
        ])
        custom_titles = st.text_area(
            "Custom titles (optional, one per line)",
            help="Leave blank to use defaults (Risk Mgr, CFO, GC, Treasurer, etc.)",
        )
        go = st.form_submit_button("Hunt", type="primary")

    if go and company_name:
        hunter = ContactHunter(db)
        titles = [t.strip() for t in custom_titles.splitlines() if t.strip()] or None
        with st.spinner(f"Hunting contacts for {company_name}..."):
            res = hunter.hunt_company(
                company_name=company_name, domain=domain or None,
                titles=titles, industry=industry or None,
                revenue_band=revenue_band or None,
            )
        st.success(
            f"LinkedIn hits: {res['linkedin_hits']} · "
            f"Scraped emails: {res['scraped_emails']} · "
            f"Contacts saved: {res['contacts_saved']}"
        )
        st.session_state["last_company_id"] = res["company_id"]


def page_import(db: DB):
    st.header("Import prospects (XLSX)")
    st.caption(
        "Upload an Excel workbook with a Companies sheet and a Contacts sheet. "
        "See examples/sample_prospects.xlsx for the column layout."
    )
    sample = Path(__file__).parent / "examples" / "sample_prospects.xlsx"
    if sample.exists():
        with open(sample, "rb") as f:
            st.download_button("Download sample_prospects.xlsx",
                               f.read(), file_name="sample_prospects.xlsx")

    uploaded = st.file_uploader("Workbook (.xlsx)", type=["xlsx"])
    if uploaded and st.button("Import", type="primary"):
        tmp = DATA_DIR / "_uploaded.xlsx"
        tmp.write_bytes(uploaded.read())
        result = import_xlsx(db, tmp)
        st.success(
            f"Loaded {result['companies']} companies and "
            f"{result['contacts']} contacts."
        )


def page_contacts(db: DB):
    st.header("Contacts")
    companies = db.list_companies()
    company_filter = st.selectbox(
        "Filter by company",
        ["(all)"] + [f"{c['name']} (#{c['id']})" for c in companies],
    )
    company_id = None
    if company_filter != "(all)":
        company_id = int(company_filter.rsplit("#", 1)[1].rstrip(")"))

    q = st.text_input("Search", placeholder="name, title, email, or company")
    rows = (db.search_contacts(q) if q.strip()
            else db.list_contacts(company_id=company_id))

    if not rows:
        st.info("No contacts. Try the Hunt page.")
        return

    st.dataframe(
        [{"id": r["id"], "name": f"{r.get('first_name','')} {r.get('last_name','')}".strip(),
          "title": r.get("title"), "email": r.get("email"),
          "confidence": round(r.get("email_confidence") or 0, 2),
          "company": r.get("company_name"), "source": r.get("source")}
         for r in rows],
        use_container_width=True,
    )


def page_merge(db: DB):
    st.header("Mail merge")
    templates = db.list_templates()
    if not templates:
        st.warning("No templates yet. Add one on the Templates page.")
        return
    tname = st.selectbox("Template", [t["name"] for t in templates])

    contacts = db.list_contacts()
    if not contacts:
        st.warning("No contacts yet. Hunt some first.")
        return

    candidates = [c for c in contacts if c.get("email")]
    options = {
        f"{c['first_name'] or '?'} {c['last_name'] or ''} — {c['email']} "
        f"({c.get('company_name','')})": c["id"]
        for c in candidates
    }
    selected_labels = st.multiselect("Recipients", list(options.keys()))
    contact_ids = [options[l] for l in selected_labels]

    from_name = st.text_input("From name", value=st.session_state.get("from_name", ""))
    from_email = st.text_input(
        "From email",
        value=st.session_state.get("from_email", os.environ.get("CRM_FROM_EMAIL", "")),
    )
    st.session_state["from_name"] = from_name
    st.session_state["from_email"] = from_email

    if st.button("Preview", type="secondary") and contact_ids:
        merger = MailMerge(db, from_name=from_name or None,
                           from_email=from_email or None)
        drafts, errors = merger.merge(contact_ids, tname)
        if errors:
            st.error(f"{len(errors)} errors")
            st.json(errors)
        for d in drafts[:5]:
            with st.expander(f"To: {d.to_email} — {d.subject}"):
                st.code(d.body)
        if len(drafts) > 5:
            st.caption(f"...and {len(drafts) - 5} more")
        st.session_state["_preview_drafts"] = drafts
        st.session_state["_preview_template"] = tname

    drafts = st.session_state.get("_preview_drafts")
    if drafts:
        col1, col2, col3 = st.columns(3)
        if col1.button("Save drafts to DB"):
            merger = MailMerge(db, from_name=from_name or None,
                               from_email=from_email or None)
            ids = merger.save_drafts(drafts, st.session_state["_preview_template"])
            st.success(f"Saved {len(ids)} drafts to DB.")
        if col2.button("Export .eml files"):
            merger = MailMerge(db, from_name=from_name or None,
                               from_email=from_email or None)
            paths = merger.export_eml(drafts, DRAFTS_DIR)
            st.success(f"Wrote {len(paths)} .eml files to {DRAFTS_DIR}")
        if col3.button("Export Gmail manifest"):
            merger = MailMerge(db, from_name=from_name or None,
                               from_email=from_email or None)
            p = merger.export_manifest(drafts, MANIFEST_PATH)
            st.success(f"Manifest at {p}. Ask Claude to push to Gmail drafts.")


def page_drafts(db: DB):
    st.header("Drafts")
    status_filter = st.selectbox("Status", ["(all)", "pending", "exported", "sent", "failed"])
    drafts = db.list_drafts(None if status_filter == "(all)" else status_filter)
    if not drafts:
        st.info("No drafts.")
        return
    for d in drafts:
        with st.expander(
            f"#{d['id']} → {d['to_email']} · {d['status']} · {d['subject']}"
        ):
            st.caption(f"To: {d['to_email']} | Template: {d.get('template_name')} | "
                       f"Created: {d['created_at']}")
            st.text_area("Body", value=d["body"], height=200,
                         key=f"body-{d['id']}", disabled=True)
            cols = st.columns(3)
            if cols[0].button("Mark exported", key=f"exp-{d['id']}"):
                db.mark_draft_status(d["id"], "exported")
                st.rerun()
            if cols[1].button("Mark sent", key=f"sent-{d['id']}"):
                db.mark_draft_status(d["id"], "sent")
                st.rerun()
            if cols[2].button("Mark failed", key=f"fail-{d['id']}"):
                db.mark_draft_status(d["id"], "failed")
                st.rerun()


def page_memory(db: DB):
    st.header("Relationship memory")
    st.caption("Log notes/calls/meetings. Then ask plain-English questions and "
               "the LLM will answer from history. Set ANTHROPIC_API_KEY for LLM; "
               "otherwise falls back to keyword search.")

    tab_log, tab_ask = st.tabs(["Log activity", "Ask"])

    with tab_log:
        contacts = db.list_contacts()
        opts = {"(none)": None}
        opts.update({
            f"{c['first_name']} {c['last_name']} — {c.get('company_name','')}": c["id"]
            for c in contacts
        })
        contact_label = st.selectbox("Contact", list(opts.keys()))
        contact_id = opts[contact_label]
        kind = st.selectbox("Kind", ["note", "call", "meeting", "email_sent",
                                      "email_received"])
        subject = st.text_input("Subject (optional)")
        body = st.text_area("Body", height=180)
        if st.button("Log") and body.strip():
            mem = Memory(db)
            company_id = None
            if contact_id:
                c = db.get_contact(contact_id)
                company_id = c.get("company_id") if c else None
            mem.log(kind=kind, body=body, subject=subject or None,
                    contact_id=contact_id, company_id=company_id)
            st.success("Logged.")

    with tab_ask:
        contacts = db.list_contacts()
        companies = db.list_companies()
        scope = st.radio("Scope", ["All", "Contact", "Company"], horizontal=True)
        contact_id = None
        company_id = None
        if scope == "Contact" and contacts:
            sel = st.selectbox(
                "Contact",
                [f"{c['first_name']} {c['last_name']} (#{c['id']})" for c in contacts],
            )
            contact_id = int(sel.rsplit("#", 1)[1].rstrip(")"))
        elif scope == "Company" and companies:
            sel = st.selectbox(
                "Company",
                [f"{c['name']} (#{c['id']})" for c in companies],
            )
            company_id = int(sel.rsplit("#", 1)[1].rstrip(")"))

        question = st.text_input("Question",
                                  placeholder="What did we last discuss?")
        if st.button("Ask", type="primary") and question.strip():
            mem = Memory(db)
            with st.spinner("Thinking..."):
                res = mem.ask(question, contact_id=contact_id,
                              company_id=company_id)
            st.write(res["answer"])
            st.caption(
                f"{'LLM' if res['used_llm'] else 'keyword'} · "
                f"{res['activities_considered']} activities considered"
            )
            if res.get("usage"):
                st.caption(
                    f"Tokens — in: {res['usage']['input_tokens']}, "
                    f"out: {res['usage']['output_tokens']}, "
                    f"cache_read: {res['usage']['cache_read']}, "
                    f"cache_create: {res['usage']['cache_create']}"
                )


def page_templates(db: DB):
    st.header("Templates")
    templates = db.list_templates()
    names = ["(new)"] + [t["name"] for t in templates]
    sel = st.selectbox("Template", names)
    if sel == "(new)":
        name = st.text_input("Name (snake_case)")
        subject = st.text_input("Subject")
        body = st.text_area("Body", height=240)
        desc = st.text_input("Description (optional)")
        if st.button("Save", type="primary") and name and subject and body:
            db.upsert_template(name, subject, body, desc or None)
            st.success(f"Saved {name}.")
            st.rerun()
    else:
        t = db.get_template(sel)
        subject = st.text_input("Subject", value=t["subject"])
        body = st.text_area("Body", value=t["body"], height=300)
        desc = st.text_input("Description", value=t.get("description") or "")
        st.caption("Available variables: {{first_name}}, {{last_name}}, "
                   "{{full_name}}, {{title}}, {{email}}, {{company}}, "
                   "{{company_domain}}")
        if st.button("Update", type="primary"):
            db.upsert_template(sel, subject, body, desc or None)
            st.success("Updated.")


if __name__ == "__main__":
    main()
