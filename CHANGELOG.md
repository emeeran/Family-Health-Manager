# Changelog

All notable changes to **Family Health Manager** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Repository-wide formatting and professionalization: enforced `ruff format`
  across the backend, expanded the README, added `LICENSE` / `SECURITY` /
  `CONTRIBUTING` policies, OpenAPI metadata, hardened CI triggers and coverage
  gate, and reconciled environment configuration.

## [1.0.4] - 2026-06-18

### Added
- Doctor and lab summary views on member profiles.
- Configurable AI provider API keys (OpenAI, Gemini, Groq, OpenRouter).
- Drag-and-drop upload drop zone for health records.

### Fixed
- Debian package metadata parsing failure during install.
- Reorganized the source tree for clearer separation of concerns.

_Entries prior to 1.0.4 predate this changelog and are not reconstructed here._
