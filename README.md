# Northstar

Northstar is a private, explainable quantitative US equity research board. Phase 1 provides a professional sample-data Kanban with search, filters, sorting, drag-and-drop workflow, pinning, notes, archive/restore, research detail, factor provenance, freshness labels, score history, and CSV export.

## Scope

This milestone is decision-support UI only. It does not connect to brokers, place orders, or represent sample observations as live market data. Browser storage is used for local board state and notes. The typed candidate and factor boundary in `app/data.ts` is intended to be replaced by deterministic scanner output in the next phase.

## Run locally

```bash
npm install
npm run dev
```

## Validate

```bash
npm run build
```

## Planned next phase

Add the Python universe/price pipeline, deterministic technical indicators, SEC fundamentals, regime gating, configurable scoring, SQLite/PostgreSQL persistence, and a scheduled daily scan. Optional AI summaries remain feature-flagged and server-side.
