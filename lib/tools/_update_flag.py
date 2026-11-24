"""`--update` is the flag that updates Canvas; `--push` is its old spelling (#493).

Both spellings are one argparse option, read as `args.update`, so no code path
can tell them apart: every gate sees the same value.
`--push` keeps working, with a one-line note on stderr. It stays on 2.x: 3.0 is
reserved for the desktop version, so the old spelling is not removed.
"""
import sys

NOTE = "`--push` is now `--update`; both work."


def add_update_flag(parser, **kwargs):
    """Add `--update` (and `--push`, its old spelling) to a parser, as `args.update`."""
    return parser.add_argument("--update", "--push", **kwargs)


def note_old_flag(argv=None) -> bool:
    """Print NOTE on stderr if the old spelling was used. Returns whether it was."""
    argv = sys.argv[1:] if argv is None else argv
    used = any(a == "--push" or a.startswith("--push=") for a in argv)
    if used:
        print(NOTE, file=sys.stderr)
    return used
