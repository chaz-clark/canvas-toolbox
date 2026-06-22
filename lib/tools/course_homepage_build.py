"""course_homepage_build.py — generate a Canvas course home page from a schedule file.

The DesignPLUS-free replacement for the "module list on the home page that
auto-tracks the current week" pattern. Pure HTML + inline CSS — no
JavaScript in the rendered page, no DesignPLUS dependencies, no
account-level CSS injection required.

THE MODEL
  The instructor maintains `schedule.yml` (one per course-section)
  with the semester's week-by-week structure. This tool reads the
  schedule + today's date, renders a static HTML home page with the
  matching week pre-expanded (`<details open>`), and optionally pushes
  it to the Canvas course's front page via `--apply`.

  Re-run whenever the "current week" should change — manually (Monday
  morning routine), via local cron, or via a GitHub Actions scheduled
  workflow. The page is static at render time; the regeneration is
  the cadence-controlled refresh.

PURE-CSS BEHAVIOR
  - Block buttons at top — anchor-jump links to each week's section
    (`<a href="#week-04">`). The currently-active week gets a
    `.current` CSS class for visual highlight.
  - Sections below — each week is a `<details>` collapsible. The
    current week is `<details open>`; others are collapsed.
  - No JavaScript in the rendered page; the only "dynamic" part is
    the build-time selection of which week is current.

USAGE
  # Bootstrap a schedule file from the course's current modules
  uv run python lib/tools/course_homepage_build.py \\
      --bootstrap-from-canvas --course-id 415138 \\
      --output schedule.yml

  # Render the home page HTML from a schedule (default today's date)
  uv run python lib/tools/course_homepage_build.py \\
      --schedule schedule.yml --output homepage.html

  # Render for a specific date (e.g., preview what week 4's page looks like)
  uv run python lib/tools/course_homepage_build.py \\
      --schedule schedule.yml --output homepage.html \\
      --date 2026-05-10

  # Push the rendered HTML to the Canvas course's front page
  # (uses CANVAS_COURSE_ID from .env unless --course-id is passed;
  # honors canvas_course_guard's enrolled-course write-gate)
  uv run python lib/tools/course_homepage_build.py \\
      --schedule schedule.yml --apply

EXIT CODES
  0  rendered (or applied) successfully
  1  setup / config / Canvas error
  2  the schedule.yml is malformed or missing required fields

FERPA
  Reads modules + their unlock dates from the Canvas API. NO student
  data touched. The rendered HTML contains module names + dates only.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests
import yaml

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

try:
    from canvas_course_guard import enforce as guard_enforce
except ImportError:
    guard_enforce = None


_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Pure-logic helpers (testable without Canvas API / filesystem)
# ---------------------------------------------------------------------------

def parse_iso_date(s) -> date:
    """Accept a YAML date object OR an ISO-8601 string OR a datetime. Return
    a date. Raises ValueError on garbage."""
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, str):
        return date.fromisoformat(s)
    raise ValueError(f"cannot parse as date: {s!r}")


def validate_schedule(schedule: dict) -> list[str]:
    """Return a list of validation errors. Empty list = valid."""
    errors: list[str] = []
    if not isinstance(schedule, dict):
        return ["schedule is not a dict at top level"]

    course = schedule.get("course")
    if not isinstance(course, dict):
        errors.append("missing or non-dict `course` block")
    else:
        for field in ("name", "code", "base_url", "course_id"):
            if not course.get(field):
                errors.append(f"course.{field} is required")

    weeks = schedule.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        errors.append("missing or empty `weeks` list")
        return errors

    for i, w in enumerate(weeks):
        if not isinstance(w, dict):
            errors.append(f"weeks[{i}] is not a dict")
            continue
        for field in ("week", "title", "start", "end"):
            if field not in w:
                errors.append(f"weeks[{i}].{field} is required")
        try:
            if "start" in w:
                parse_iso_date(w["start"])
            if "end" in w:
                parse_iso_date(w["end"])
        except ValueError as e:
            errors.append(f"weeks[{i}] date parse error: {e}")
    return errors


def pick_current_week(weeks: list[dict], today: date) -> dict | None:
    """Find the week whose start <= today <= end. Returns the week dict,
    or None if no week matches (pre-term, post-term, gap between weeks)."""
    for w in weeks:
        try:
            start = parse_iso_date(w["start"])
            end = parse_iso_date(w["end"])
        except (ValueError, KeyError):
            continue
        if start <= today <= end:
            return w
    return None


def build_module_href(course_block: dict, week: dict) -> str:
    """Compute the Canvas URL for a week's module. If the week dict carries
    `href` use that; otherwise build from base_url + course_id + module_id."""
    if week.get("href"):
        return week["href"]
    base = course_block.get("base_url", "").rstrip("/")
    cid = course_block.get("course_id")
    mid = week.get("module_id")
    if base and cid and mid:
        return f"{base}/courses/{cid}/modules/{mid}"
    return "#"  # caller can pick this up as "no link"


# ---------------------------------------------------------------------------
# CSS — inline, deliberately minimal. No DesignPLUS classes, no Bootstrap,
# no Font Awesome. Pure CSS + system fonts.
# ---------------------------------------------------------------------------

_CSS_TEMPLATE = """\
<style>
.ct-homepage {{
  font-family: {font_family};
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
  color: #1a1a1a;
}}
.ct-homepage .ct-header {{
  background: {primary_color};
  color: #fff;
  padding: 16px 24px;
  border-radius: 8px;
  margin-bottom: 16px;
}}
.ct-homepage .ct-header h2 {{
  margin: 0;
  font-size: 1.6rem;
  font-weight: 700;
}}
.ct-homepage .ct-header .ct-code {{
  display: inline-block;
  background: rgba(255,255,255,0.18);
  padding: 2px 10px;
  border-radius: 4px;
  margin-right: 12px;
  font-size: 0.85rem;
  letter-spacing: 0.5px;
}}
.ct-homepage .ct-banner {{
  width: 100%;
  height: auto;
  border-radius: 8px;
  margin-bottom: 16px;
  display: block;
}}
.ct-homepage .ct-quick-links {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}}
.ct-homepage .ct-quick-links a {{
  background: {secondary_color};
  color: #1a1a1a;
  text-decoration: none;
  padding: 14px 18px;
  border-radius: 6px;
  border: 1px solid #d0d0d0;
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 500;
  transition: background 0.15s, transform 0.15s;
}}
.ct-homepage .ct-quick-links a:hover {{
  background: #ebebeb;
  transform: translateY(-1px);
}}
.ct-homepage .ct-quick-links .ct-icon {{
  font-size: 1.2rem;
  line-height: 1;
}}
.ct-homepage .ct-week-buttons {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
  margin-bottom: 24px;
}}
.ct-homepage .ct-week-buttons a {{
  background: {secondary_color};
  color: #1a1a1a;
  text-decoration: none;
  padding: 14px 10px;
  border-radius: 6px;
  border: 1px solid #d0d0d0;
  text-align: center;
  font-weight: 600;
  font-size: 0.95rem;
  transition: background 0.15s, transform 0.15s;
}}
.ct-homepage .ct-week-buttons a:hover {{
  background: #ebebeb;
  transform: translateY(-1px);
}}
.ct-homepage .ct-week-buttons a.current {{
  background: {current_color};
  color: #1a1a1a;
  border-color: #a8861f;
  box-shadow: 0 2px 6px rgba(0,0,0,0.12);
}}
.ct-homepage details.ct-week {{
  border: 1px solid #d0d0d0;
  border-radius: 6px;
  margin-bottom: 10px;
  background: #fff;
}}
.ct-homepage details.ct-week[open] {{
  border-color: {primary_color};
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}}
.ct-homepage details.ct-week summary {{
  cursor: pointer;
  padding: 14px 18px;
  font-weight: 600;
  font-size: 1.05rem;
  list-style: none;
}}
.ct-homepage details.ct-week summary::-webkit-details-marker {{ display: none; }}
.ct-homepage details.ct-week summary::before {{
  content: "▸ ";
  display: inline-block;
  margin-right: 6px;
  transition: transform 0.15s;
}}
.ct-homepage details.ct-week[open] summary::before {{ content: "▾ "; }}
.ct-homepage details.ct-week .ct-week-body {{
  padding: 0 18px 16px;
  font-size: 0.95rem;
  line-height: 1.5;
}}
.ct-homepage details.ct-week .ct-week-dates {{
  color: #555;
  font-size: 0.85rem;
  margin-bottom: 8px;
}}
.ct-homepage details.ct-week .ct-week-summary {{
  margin-bottom: 12px;
}}
.ct-homepage details.ct-week .ct-week-link {{
  display: inline-block;
  color: {primary_color};
  text-decoration: none;
  font-weight: 500;
  padding: 6px 12px;
  border: 1px solid {primary_color};
  border-radius: 4px;
  transition: background 0.15s, color 0.15s;
}}
.ct-homepage details.ct-week .ct-week-link:hover {{
  background: {primary_color};
  color: #fff;
}}
.ct-homepage .ct-footer {{
  color: #777;
  font-size: 0.8rem;
  text-align: center;
  margin-top: 24px;
}}
@media (max-width: 600px) {{
  .ct-homepage .ct-week-buttons {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
"""


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_homepage(schedule: dict, today: date) -> str:
    """Pure rendering — schedule + today's date → HTML string. No Canvas API."""
    course = schedule["course"]
    weeks = schedule["weeks"]
    style = schedule.get("style") or {}
    quick_links = schedule.get("quick_links") or []
    current_week = pick_current_week(weeks, today)

    css = _CSS_TEMPLATE.format(
        font_family=style.get("font_family",
                              "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"),
        primary_color=style.get("primary_color", "#800000"),
        secondary_color=style.get("secondary_color", "#f5f5f5"),
        current_color=style.get("current_color", "#FFD700"),
    )

    parts: list[str] = [css, '<div class="ct-homepage">']

    # Header
    parts.append('  <div class="ct-header">')
    parts.append(f'    <h2><span class="ct-code">{_html_escape(course["code"])}</span>'
                 f'{_html_escape(course["name"].replace(course.get("code","") + " — ", ""))}</h2>')
    parts.append('  </div>')

    # Banner (optional)
    if course.get("banner_url"):
        parts.append(f'  <img class="ct-banner" src="{_html_escape(course["banner_url"])}" '
                     f'alt="{_html_escape(course["name"])} banner">')

    # Quick links
    if quick_links:
        parts.append('  <nav class="ct-quick-links" aria-label="Quick links">')
        for ql in quick_links:
            icon = ql.get("icon", "")
            icon_html = f'<span class="ct-icon" aria-hidden="true">{_html_escape(icon)}</span>' if icon else ""
            parts.append(f'    <a href="{_html_escape(ql.get("href","#"))}">'
                         f'{icon_html}{_html_escape(ql.get("title",""))}</a>')
        parts.append('  </nav>')

    # Week buttons (anchor-jump nav)
    parts.append('  <nav class="ct-week-buttons" aria-label="Week navigation">')
    for w in weeks:
        is_current = (current_week is not None and w.get("week") == current_week.get("week"))
        cls = "current" if is_current else ""
        wk_id = f"week-{w.get('week', '?')}"
        label = f"Week {w.get('week', '?')}"
        parts.append(f'    <a href="#{wk_id}" class="{cls}">{_html_escape(label)}</a>')
    parts.append('  </nav>')

    # Week sections (collapsible)
    parts.append('  <section class="ct-weeks">')
    for w in weeks:
        is_current = (current_week is not None and w.get("week") == current_week.get("week"))
        open_attr = " open" if is_current else ""
        wk_id = f"week-{w.get('week', '?')}"
        title = _html_escape(w.get("title", f"Week {w.get('week','?')}"))
        href = build_module_href(course, w)
        try:
            start = parse_iso_date(w["start"]).strftime("%b %-d")
            end = parse_iso_date(w["end"]).strftime("%b %-d, %Y")
            dates = f"{start} – {end}"
        except (ValueError, KeyError):
            dates = ""
        summary_text = w.get("summary", "")

        parts.append(f'    <details id="{wk_id}" class="ct-week"{open_attr}>')
        parts.append(f'      <summary>{title}</summary>')
        parts.append('      <div class="ct-week-body">')
        if dates:
            parts.append(f'        <div class="ct-week-dates">{_html_escape(dates)}</div>')
        if summary_text:
            parts.append(f'        <div class="ct-week-summary">{_html_escape(summary_text)}</div>')
        if href != "#":
            parts.append(f'        <a class="ct-week-link" href="{_html_escape(href)}">'
                         f'Open the {title} module →</a>')
        parts.append('      </div>')
        parts.append('    </details>')
    parts.append('  </section>')

    # Footer (rendering provenance — useful for debugging cron drift)
    parts.append(f'  <div class="ct-footer">Last rendered: {today.isoformat()} '
                 f'· canvas-toolbox v{__version__}</div>')
    parts.append('</div>')
    return "\n".join(parts)


def _html_escape(s) -> str:
    """Lightweight HTML escape — sufficient for the values we control (no
    arbitrary user input flows into here; schedule.yml is operator-authored)."""
    if s is None:
        return ""
    s = str(s)
    return (s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Canvas API helpers (subprocess-shaped; not heavily unit-tested)
# ---------------------------------------------------------------------------

def _env_canvas() -> tuple[str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, base


def fetch_course_modules(base: str, headers: dict, course_id: int) -> list[dict]:
    """Pull modules with their date fields. Used for --bootstrap-from-canvas."""
    out: list[dict] = []
    url = f"{base}/api/v1/courses/{course_id}/modules"
    params = {"per_page": 100}
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        page = r.json()
        if isinstance(page, list):
            out.extend(page)
        link = r.headers.get("Link", "")
        next_url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
        url = next_url
        params = None
    return out


def fetch_course_info(base: str, headers: dict, course_id: int) -> dict:
    """Fetch the course's name/code for the bootstrap helper."""
    r = requests.get(f"{base}/api/v1/courses/{course_id}", headers=headers, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json() or {}


def bootstrap_schedule_from_canvas(course_id: int) -> dict:
    """Generate a starter schedule.yml dict from the course's modules.

    Output may need hand-editing — Canvas's `unlock_at` / `lock_at` may not
    line up exactly with the semester structure the instructor intends;
    the bootstrap is a *starting point*, not a final spec."""
    tok, base = _env_canvas()
    if not tok or not base:
        raise RuntimeError("Missing CANVAS_API_TOKEN or CANVAS_BASE_URL in .env")
    headers = {"Authorization": f"Bearer {tok}"}

    course = fetch_course_info(base, headers, course_id)
    modules = fetch_course_modules(base, headers, course_id)

    weeks: list[dict] = []
    week_num = 0
    for m in modules:
        name = m.get("name") or ""
        # Skip non-week modules (front matter, resources, etc.)
        lname = name.lower()
        if not any(tok in lname for tok in ("week ", "wk ", "unit ")):
            continue
        week_num += 1
        unlock = m.get("unlock_at")
        # Canvas doesn't expose lock_at on Module; we use the NEXT module's
        # unlock_at as the lock boundary, with a 1-week default at the end.
        weeks.append({
            "week": week_num,
            "module_id": m.get("id"),
            "title": name,
            "_canvas_unlock_at": unlock,  # underscore prefix = operator should clean up
        })

    # Best-effort start/end pass — uses unlock_at where present, leaves
    # placeholders where not.
    for i, w in enumerate(weeks):
        unlock = w.pop("_canvas_unlock_at", None)
        if unlock:
            start = unlock[:10]
            w["start"] = start
            # End = next week's start - 1 day, OR start + 7 days
            if i + 1 < len(weeks):
                next_unlock = weeks[i + 1].get("_canvas_unlock_at") or ""
                if next_unlock:
                    next_start = parse_iso_date(next_unlock[:10])
                    from datetime import timedelta
                    w["end"] = (next_start - timedelta(days=1)).isoformat()
                else:
                    w["end"] = "<EDIT: end date>"
            else:
                w["end"] = "<EDIT: end date>"
        else:
            w["start"] = "<EDIT: start date YYYY-MM-DD>"
            w["end"] = "<EDIT: end date YYYY-MM-DD>"

    return {
        "course": {
            "name": course.get("name", ""),
            "code": course.get("course_code", ""),
            "base_url": base,
            "course_id": course_id,
        },
        "weeks": weeks,
    }


def push_homepage_to_canvas(html: str, course_id: int) -> str:
    """PUT the rendered HTML as the course's front page. Returns the page URL."""
    tok, base = _env_canvas()
    if not tok or not base:
        raise RuntimeError("Missing CANVAS_API_TOKEN or CANVAS_BASE_URL in .env")
    headers = {"Authorization": f"Bearer {tok}"}

    if guard_enforce:
        guard_enforce(base, headers, str(course_id), mode="write")

    # Canvas API: PUT /api/v1/courses/:id/front_page
    r = requests.put(
        f"{base}/api/v1/courses/{course_id}/front_page",
        headers=headers,
        data={
            "wiki_page[body]": html,
            "wiki_page[published]": "true",
            "wiki_page[front_page]": "true",
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return (r.json() or {}).get("html_url", f"{base}/courses/{course_id}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Generate a Canvas course home page from a schedule.yml. "
            "Pure HTML + inline CSS — DesignPLUS-free replacement for the "
            "module-list-on-home-page pattern. See "
            "lib/agents/knowledge/course_homepage_knowledge.md for the design."
        ),
    )
    ap.add_argument("--version", action="version",
                    version=f"%(prog)s {__version__}")
    ap.add_argument("--schedule", help="Path to schedule.yml")
    ap.add_argument("--output", help="Path to write the rendered HTML (default: stdout)")
    ap.add_argument("--date", help="Render the page as if today is this date "
                    "(YYYY-MM-DD; default: today). Useful for previewing.")
    ap.add_argument("--apply", action="store_true",
                    help="PUSH the rendered HTML to the Canvas course's front page. "
                         "Uses CANVAS_COURSE_ID from env unless --course-id is passed. "
                         "Honors canvas_course_guard's enrolled-course write-gate.")
    ap.add_argument("--course-id", type=int,
                    help="Canvas course ID (used by --apply and --bootstrap-from-canvas)")
    ap.add_argument("--bootstrap-from-canvas", action="store_true",
                    help="Generate a starter schedule.yml from the course's modules. "
                         "Requires --course-id and --output.")
    args = ap.parse_args()

    # ---- bootstrap mode ----
    if args.bootstrap_from_canvas:
        if not args.course_id:
            print("--bootstrap-from-canvas requires --course-id", file=sys.stderr)
            return 1
        if not args.output:
            print("--bootstrap-from-canvas requires --output <path>", file=sys.stderr)
            return 1
        try:
            schedule = bootstrap_schedule_from_canvas(args.course_id)
        except (requests.HTTPError, RuntimeError) as e:
            print(f"bootstrap failed: {e}", file=sys.stderr)
            return 1
        Path(args.output).write_text(
            "# Bootstrapped from Canvas — EDIT before using.\n"
            "# Hand-tune week titles, fill in <EDIT> dates, add quick_links + style.\n"
            "# See lib/agents/templates/course_homepage/schedule.example.yml for the schema.\n\n"
            + yaml.dump(schedule, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        print(f"✓ Wrote starter schedule to {args.output}", file=sys.stderr)
        print(f"  {len(schedule.get('weeks', []))} weeks detected. "
              f"Review + edit before using.", file=sys.stderr)
        return 0

    # ---- render mode ----
    if not args.schedule:
        print("--schedule <path> is required (or use --bootstrap-from-canvas)", file=sys.stderr)
        return 1

    sched_path = Path(args.schedule)
    if not sched_path.exists():
        print(f"Schedule file not found: {sched_path}", file=sys.stderr)
        return 1

    try:
        schedule = yaml.safe_load(sched_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"YAML parse error in {sched_path}: {e}", file=sys.stderr)
        return 2

    errors = validate_schedule(schedule)
    if errors:
        print(f"Schedule validation failed ({len(errors)} errors):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    # Resolve the as-of date
    if args.date:
        try:
            today = parse_iso_date(args.date)
        except ValueError as e:
            print(f"--date parse error: {e}", file=sys.stderr)
            return 1
    else:
        today = date.today()

    html = render_homepage(schedule, today)
    current = pick_current_week(schedule["weeks"], today)
    if current:
        print(f"Rendered for {today}; current week = "
              f"#{current.get('week')} ({current.get('title','?')})",
              file=sys.stderr)
    else:
        print(f"Rendered for {today}; NO week matches "
              f"(pre-term, post-term, or gap between weeks). "
              f"All weeks render collapsed.", file=sys.stderr)

    # Write the output
    if args.output:
        Path(args.output).write_text(html, encoding="utf-8")
        print(f"✓ Wrote HTML to {args.output}", file=sys.stderr)
    else:
        print(html)

    # Push to Canvas if --apply
    if args.apply:
        cid = args.course_id or schedule.get("course", {}).get("course_id")
        if not cid:
            cid_env = os.environ.get("CANVAS_COURSE_ID", "").strip()
            try:
                cid = int(cid_env) if cid_env else None
            except ValueError:
                cid = None
        if not cid:
            print("--apply: no course_id resolved. Pass --course-id, "
                  "set CANVAS_COURSE_ID in env, or fill course.course_id "
                  "in schedule.yml.", file=sys.stderr)
            return 1
        print(f"  --apply: pushing to Canvas course {cid}...", file=sys.stderr)
        try:
            url = push_homepage_to_canvas(html, cid)
        except (requests.HTTPError, RuntimeError) as e:
            print(f"  ✗ push failed: {e}", file=sys.stderr)
            return 1
        print(f"  ✓ Pushed. View at: {url}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
