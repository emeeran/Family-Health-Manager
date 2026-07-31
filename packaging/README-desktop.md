# Health Manager — Desktop app (.deb, Tauri)

A native **desktop** build of the Family Health Manager, packaged as a Debian
`.deb`. It runs the same FastAPI backend and React frontend as the server build,
but wrapped in a Tauri (native webview) shell so it installs and launches like a
normal Linux desktop application — no browser, no systemd, no Caddy.

```
Tauri shell (/usr/bin/health-manager-desktop)
  └─ spawns a PyInstaller-frozen backend (sidecar) on a random 127.0.0.1 port
  └─ the backend serves the built SPA + API same-origin, so the httpOnly auth
     cookies work over plain HTTP (no TLS needed locally)
  └─ the webview loads http://127.0.0.1:<port>/ and shows the app in a window
```

This is a **separate package** (`health-manager-desktop`) from the server deb
(`health-manager`), so both can be installed at once.

## Build prerequisites

```bash
# runtime libs the build links against + external tools the backend shells out to
sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev \
                    libayatana-appindicator3-dev libssl-dev \
                    tesseract-ocr ghostscript

# toolchains
#   node 20+ , uv (https://docs.astral.sh/uv/), rust (https://rustup.rs)
cargo install tauri-cli --version "^2"   # or: the repo already has tauri-cli 2.x
```

PyInstaller is a backend dev dependency (`uv add --dev pyinstaller`, already in
`backend/pyproject.toml`).

## Build the .deb

From the repo root:

```bash
bash packaging/build-desktop-deb.sh
```

Output: `desktop/target/release/bundle/deb/health-manager-desktop_<ver>_amd64.deb`.

The script refuses to build from a dirty working tree — commit or stash first,
or prefix with `HM_ALLOW_DIRTY=1` to override — so a `.deb` always traces back
to a commit.

## Install

```bash
sudo apt install ./health-manager-desktop_<ver>_amd64.deb
```

(`apt install` resolves the runtime dependencies — `libwebkit2gtk-4.1-0`,
`tesseract-ocr`, `ghostscript`, etc. — automatically. A bare `dpkg -i` will not.)

Launch it from your application menu (search "Health Manager") or run
`health-manager-desktop`.

## Where your data lives

Everything is per-user (no root, no system service):

```
~/.local/share/com.dawnstar.healthmanager/
├── config.env          # auto-generated secrets (SECRET_KEY / ENCRYPTION_KEY / …)
└── data/
    ├── health.db       # SQLite database (migrations auto-run on every launch)
    ├── scheduler.db    # APScheduler jobstore
    ├── attachments/    # encrypted uploaded files
    └── backups/        # local DB backups
```

To reset the app: quit it and delete that directory.

## Local AI (Ollama) — optional but recommended

The app's document extraction, smart reports, and chat use AI. With no AI
provider configured it degrades gracefully (those features return empty / a
friendly message). For **fully local, private** AI:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:4b          # the model the app uses by default
```

The desktop app auto-starts `ollama serve` if it's installed but not running.
Cloud providers (Groq / Google / OpenRouter / OpenAI) can also be configured in
the app's **Settings → AI Providers** instead of — or in addition to — Ollama.

**Google Gemini works zero-config** if you've run
`gcloud auth application-default login`: the app auto-detects the standard gcloud
credentials (`~/.config/gcloud/application_default_credentials.json`) and infers
the Vertex project from them — no API key or `.env` needed. Exporting a report to
PDF opens a native Save-As dialog.

## Troubleshooting

- **App window never appears / closes immediately.** Launch from a terminal
  (`health-manager-desktop`) and read the `[backend]` log lines. The usual cause
  is a missing runtime library the deb dependencies didn't cover.
- **AI features empty.** Install Ollama + pull `qwen3:4b` (above), or add a cloud
  provider key in Settings. Check `/health/detail` (needs the HEALTH_CHECK_SECRET
  in `~/.local/share/com.dawnstar.healthmanager/config.env`).
- **A previous instance is still running.** The app enforces a single instance;
  a second launch just focuses the existing window. The backend sidecar
  (`/usr/bin/health-manager-backend`) is torn down via its whole process tree
  when you close the window, and self-terminates if its parent dies, so orphans
  are rare. If one is left behind (e.g. the shell was `kill -9`'d):
  `pkill -f health-manager-backend`.

## Coexistence with the server deb

Both packages can be installed together. The server deb runs on fixed ports
(uvicorn :8000, Caddy :8080) under a system user; the desktop app uses an
ephemeral port and your own user's data dir. They don't conflict.
