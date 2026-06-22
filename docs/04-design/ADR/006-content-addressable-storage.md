# ADR-006: Content-Addressable Storage with Dedup and Encryption

## Status

Accepted

## Date

2026-06-01

## Context

The original attachment storage stored files using UUID-based filenames in a flat directory structure (`original medical records/`). This led to several issues:

1. **No deduplication** — uploading the same file multiple times stores duplicate copies
2. **No integrity verification** — silent data corruption would go undetected
3. **No streaming I/O** — files were read entirely into memory before writing
4. **No thumbnails** — no preview capability for attachments
5. **No encryption at rest** — medical document files were stored unencrypted
6. **Fragile paths** — hardcoded directory names with spaces in production paths
7. **No storage abstraction** — no way to swap backends (e.g., S3) without rewriting

## Decision

Implement a content-addressable storage system with the following characteristics:

### Storage Layout
Files are stored using SHA-256 content hashing with two-level sharding:
```
{STORAGE_PATH}/
├── files/ab/cdef0123456789...pdf    # Content-addressed files
├── staging/                          # Temporary upload staging
└── thumbnails/abc123.webp            # Generated thumbnails
```

### Key Components

1. **`save_file_hashed()`** — Stream-writes to a temp file while computing SHA-256, then moves to sharded path. Deduplicates on identical hash.

2. **Streaming I/O** — All uploads and downloads use 1MB chunked streaming via `aiofiles`. Downloads use `StreamingResponse` for zero-buffer delivery.

3. **Reference-counted deletion** — Physical files are only deleted when no other `Attachment` row references the same `content_hash`.

4. **Thumbnail generation** — Automatic WebP thumbnails (300px) for images (Pillow) and PDFs (PyMuPDF first page).

5. **Encryption at rest** — Optional Fernet encryption (via `cryptography` library) using a key derived from `SECRET_KEY` via PBKDF2 with 480k iterations.

6. **Storage backend protocol** — `StorageBackend` Protocol class with `LocalStorageBackend` implementation. Factory pattern allows future backends (S3, etc.).

7. **Background jobs** — Staging cleanup (hourly), file integrity verification (daily SHA-256 re-check).

### Attachment Model Changes
Four new columns added to the `attachments` table:
- `content_hash` VARCHAR(64) — SHA-256 hex digest, indexed for dedup queries
- `storage_backend` VARCHAR(20) — backend identifier, defaults to `'local'`
- `thumbnail_path` VARCHAR(500) — path to generated thumbnail
- `encrypted` BOOLEAN — whether the file is encrypted at rest

## Consequences

### Positive
- Storage deduplication reduces disk usage for repeated uploads
- SHA-256 integrity verification detects silent data corruption
- Streaming I/O reduces memory pressure for large files
- Thumbnails improve UX for browsing attachments
- Encryption at rest protects sensitive medical documents
- Pluggable backend enables future cloud storage migration
- Reference counting prevents accidental data loss from dedup

### Negative
- Additional `cryptography` dependency
- File migration needed for existing attachments (provided via `migrate_files.py`)
- Encrypted files cannot be streamed (must decrypt full content first)
- Hash computation adds marginal CPU overhead on upload
- Two-level directory sharding adds minor filesystem complexity

### Risks
- **Key rotation**: Changing `SECRET_KEY` would require re-encrypting all files. The migration script handles this but is a one-way operation.
- **Hash collisions**: SHA-256 collision risk is negligible (~2^-128 birthday bound), but monitoring via the integrity check job is prudent.
