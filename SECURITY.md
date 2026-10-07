# Security policy

## Supported deployment

The deployment target is a Vercel frontend, Railway API and one scraping worker, with separate PostgreSQL and Redis services. Keep database and broker access private.

The `/api/session` token protects requests; it is not user authentication. The application does not provide accounts, public multi-user access, or tenant isolation. Do not expose its dashboard directly to a public network without a separately designed authentication and TLS boundary.

Keep environment files and deployment secrets private, use a unique database password, and retain explicit Host/Origin allowlists. Scraped datasets and exports may contain personal information; do not attach them to public reports.

## Reporting

A private reporting contact is not documented in this repository.

Do not open a public issue containing exploit details, credentials, or sensitive data. Request a private reporting channel from the maintainer without sharing sensitive details publicly. Include the affected version, reproduction, impact, and a sanitized example in the private report. No support SLA or disclosure timetable is promised.
