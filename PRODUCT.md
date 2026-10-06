# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Approved: local FastAPI/Uvicorn service, plain HTML/CSS/JavaScript, existing PostgreSQL database.

## Users and Purpose

The repository owner inspects scraped job listings and their complete stored details and triggers scraping from a browser. The underlying project collects job data for ML datasets; reliable scraping at scale remains its priority.

## Capabilities and Constraints

Approved scope: server-side pagination, search and source/company filters, job details with arbitrary attributes and sightings, background scraping with durable history, and CLI/dashboard/reset overlap prevention. Local-only, one process, no login or deployment in this version. Company ATS feeds include all open listings regardless of the day window.

## Evidence on Hand

Actual job records in the local PostgreSQL database, the company catalog, and the approved spec at `docs/superpowers/specs/2026-10-06-job-dashboard-design.md`. Counts must come from the database; no invented product claims.

## Product Principles

- Show stored data faithfully, including missing fields.
- Keep long scraping operations visible without blocking browsing.
- Preserve connector/storage separation and existing pacing.
- Keep dependencies and operating commands small.
