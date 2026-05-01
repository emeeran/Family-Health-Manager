# ADR-001: SQLite with SQLCipher for Encrypted Storage

## Status: Accepted

## Context

The Family Health Tracker application requires:
- Encrypted storage of sensitive health data at rest (NFR-003)
- Single-household deployment (v1 scope)
- Zero-config deployment via Docker Compose (NFR-009)
- Memory footprint ≤512 MB (NFR-010)
- Self-hosted on user's server

Key requirements from SPEC.md:
- SQLCipher encryption (AES-256)
- Single-file database for simplicity
- No external database server dependency

## Decision

Use **SQLite with SQLCipher** as the database engine.

**Implementation details:**
- Database file: `/data/health.db` (Docker volume)
- Encryption: SQLCipher 4.x with AES-256
- Connection: SQLAlchemy 2.x with `pysqlcipher3` driver
- Password: 32+ character key from environment variable

**Connection string format:**
```
sqlite:////data/health.db?_pragma=page_size=4096&_pragma=cipher_page_size=4096&_pragma=key='<PASSWORD>'
```

**Rationale:**
1. **Single-file deployment** — Database is a single encrypted file, trivial to backup/restore
2. **Zero external dependencies** — No separate database server to configure or maintain
3. **SQLCipher maturity** — Widely used, audited encryption extension for SQLite
4. **Memory efficient** — SQLite engine uses <50 MB RAM, well under 512 MB budget
5. **Adequate performance** — For single-household workload (1-10 users), SQLite handles 100+ req/s easily

## Consequences

**Positive:**
- Simplified deployment (no database container)
- Easy backup (copy single file)
- Low memory footprint
- No network latency to database

**Negative:**
- Limited concurrency (writes are serialized)
- No point-in-time recovery (WAL mode helps but limited)
- Cannot scale beyond single machine
- SQLCipher is GPL-licensed (acceptable for personal use)

**Mitigations:**
- Concurrency: Rate limiting (100 req/min) prevents write contention
- Recovery: Regular volume snapshots via Docker backup tools
- Scale: Multi-household (v2) will use separate DB per household, not shared server

**Migration path:**
If PostgreSQL becomes necessary in v2:
1. SQLAlchemy abstraction allows DB swap with minimal code changes
2. Data migration script can export/import between SQLite and PostgreSQL
3. Per-household DB isolation already designed (single DB per deployment)

## Alternatives Considered

### PostgreSQL + pgcrypto
- **Pros:** Full ACID, better concurrency, industry standard
- **Cons:** Requires separate container, more memory (~200 MB baseline), more complex backup
- **Verdict:** Overkill for single-household v1; can migrate later

### MySQL/MariaDB
- **Pros:** Familiar, good tooling
- **Cons:** Same as PostgreSQL; encryption at rest requires Enterprise Edition or manual setup
- **Verdict:** Not suitable for encrypted single-file requirement

### SQLite without encryption
- **Pros:** Simpler, no license concerns
- **Cons:** Violates NFR-003 (encryption at rest)
- **Verdict:** Rejected — security requirement is mandatory

### MongoDB
- **Pros:** Flexible schema for health records
- **Cons:** No native encryption at rest in community edition, higher memory usage
- **Verdict:** Relational model fits health data better; rejected

### DuckDB
- **Pros:** Fast analytics, single-file
- **Cons:** No encryption support, OLAP-focused not OLTP
- **Verdict:** Not suitable for transactional health records

---

**Date:** 2026-04-02  
**Author:** Principal Engineer (AI)  
**Reviewers:** Specification Review Gate
