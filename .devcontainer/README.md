# Dev Container

One-click adopter setup. Two entry points:

## GitHub Codespaces (cloud)

1. From the canvas-toolbox repo page on GitHub: click the green **`<> Code`** button → **Codespaces** tab → **Create codespace on main**.
2. Wait ~2-3 minutes on the first launch (initial Python image pull + `uv sync` + Chromium install via Playwright). Subsequent launches are seconds.
3. The codespace opens VS Code in your browser. Start with the toolkit's `README.md` and `AGENTS.md`.

Codespaces is free for ~60 hours/month on the personal plan; institutional accounts (GitHub Education) get more. See https://docs.github.com/en/codespaces/overview for current quotas.

## VS Code Dev Containers (local)

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Colima / OrbStack on macOS).
2. Install VS Code's [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).
3. Clone canvas-toolbox locally: `git clone https://github.com/chaz-clark/canvas-toolbox`.
4. Open the folder in VS Code → command palette → **Dev Containers: Reopen in Container**.
5. Wait for the same one-time setup as Codespaces; faster on subsequent re-opens.

## What's in the container

- **Python 3.14** (matches `pyproject.toml`'s `requires-python = ">=3.14"`)
- **uv** (the toolkit's package manager; auto-installs dependencies from `uv.lock`)
- **Playwright + Chromium** (used by `grader_follow_share_url.py` for ChatGPT/Gemini share-URL transcripts)
- **GitHub CLI** (`gh`) — for the bug-intake fallback path
- **Node 22 LTS** + **wrangler** (auto-installable via `npm i -g wrangler`) — for the bug-intake worker maintainer flow (only relevant if you're the toolkit maintainer rotating the PAT; adopters don't need this)
- **VS Code extensions** for Python, Markdown, TOML, YAML, Jupyter, and GitHub PRs

## What's NOT in the container

- **Your Canvas API credentials.** Drop a `.env` at the repo root with `CANVAS_API_TOKEN`, `CANVAS_BASE_URL`, `CANVAS_COURSE_ID` (see `.env.example`). The `.env` file is gitignored and stays inside the container's workspace.
- **An LLM key.** The toolkit's keyless-default path uses your existing agent runtime (Claude Code, Cursor, etc.). If you want to run `grader_grade.py`'s LLM-driven orchestrator directly, set `ANTHROPIC_API_KEY` in the same `.env`.
- **Student submission data.** The container's filesystem is yours; FERPA discipline still applies. Don't push `submissions_raw/` to git (the toolkit's `.gitignore` handles this by default).

## First-time adopters — quick sanity check

After the container opens:

```bash
# Confirm the toolkit loaded cleanly
uv run python lib/tools/grader_fetch.py --version
# → canvas-toolbox 0.50.x

# Confirm Playwright is wired (for #51 share-URL transcripts)
uv run playwright --version

# Confirm gh CLI is in PATH (for the bug-intake fallback)
gh --version
```

If any of those error, the dev container's `postCreateCommand` didn't finish. Re-run it from the command palette: **Dev Containers: Rebuild Container**.

## For adopting universities

If you're rolling out canvas-toolbox to a faculty cohort at your institution, the dev container path is the easiest distribution: faculty don't install Python, uv, Playwright, or the OS-level dependencies themselves. They click the Codespaces button (or open in their local VS Code) and have a working environment in 2-3 minutes.

Your institution's IT may want to:
- Set up GitHub Education (free Codespace quota for faculty + students)
- Stand up a self-hosted [DevPod](https://www.vcluster.com/blog/introducing-devpod-codespaces-but-open-source) if Codespaces' cloud-residency story doesn't match your data-handling rules
- Provide an institutional Canvas API token + LLM provider (Claude for Education, OpenAI Edu, etc.) — see the toolkit's `UPGRADING.md` and `SECURITY.md` for what each adopting institution needs to handle

See `ADOPTING.md` at the repo root (forthcoming) for the full institutional rollout guide.
