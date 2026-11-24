# 100-Application Authentication Research Report

## Research objective

Build a persistent, auditable research system for studying normal application authentication and developer API authentication across 100 applications in 10 categories.

## Methodology

The system seeds 100 applications from a structured JSON dataset. Public research jobs perform bounded HTTP requests against official public URLs and store timestamps, findings, response outcomes, and evidence rows in SQLite. No account is created, no personal information is submitted, and no CAPTCHA, MFA, paywall, or access control is bypassed.

## Current findings

The baseline dataset contains 100 applications and 10 categories. Authentication-specific fields intentionally remain unknown until an official page or documented source verifies them. Public HTTP probes provide evidence only for website availability and public reachability; they do not verify login methods, MFA, API credentials, or signup restrictions.

## Verification rules

- **Verified:** supported by a reviewed official source.
- **Public documentation only:** official public documentation exists, but account behavior was not tested.
- **Requires account:** account access is necessary to verify the claim.
- **Requires paid subscription / partner approval:** official or public evidence states a restriction.
- **Blocked:** public access failed or returned an access response.
- **Not tested:** no evidence has been collected.

## Technical limitations

Public pages may render authentication options dynamically. Regional restrictions, bot protection, cookie walls, and JavaScript-only content can prevent complete verification. Official documentation can change after retrieval. These results must not be interpreted as security guarantees.

## Student run instructions

Run the application with `python -m uvicorn backend:app --reload`, open `http://127.0.0.1:8000`, search or filter applications, and start a read-only public probe. Export the SQLite-backed dataset as CSV or JSON before sharing a report.
