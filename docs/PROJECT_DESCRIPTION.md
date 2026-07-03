# Project Description — AI Web-Design Lead Finder

> This is a placeholder for the original `PROJECT_DESCRIPTION.md` context doc. The
> authoritative build plan lives in [`BUILD_PROMPT.md`](BUILD_PROMPT.md). This file
> summarises the product intent so the repo is self-describing even before the
> original context docs are dropped in.

## One-liner

A modular Python platform that discovers local (UK) businesses, audits their
online presence, scores them as web-design prospects, and drafts personalised
outreach for human review before sending.

## Who it's for

A web-design studio / freelancer doing outbound B2B sales in the UK who wants a
qualified, evidence-backed pipeline of local businesses whose websites are weak,
missing, or dated — and ready-to-review outreach for the best of them.

## Guiding principles

- **Walking skeleton first** — a narrow end-to-end slice before breadth.
- **Provider-abstracted discovery** — never scrape Google Maps; swap data
  sources behind one interface.
- **Unknown is never invented** — absent evidence yields `null`/"unknown", not a
  guess. Every score explains itself.
- **A human sends** — the system only drafts outreach; approval is manual.
- **Compliance built in** — robots.txt, truthful UA, rate limits, GDPR/PECR,
  suppression list, unsubscribe, lawful-basis notes.
