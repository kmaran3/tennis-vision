"""Run a local command with saved configuration taking priority over the shell.

uv parses the file; this launcher only removes conflicting inherited names.
No secret values are read or printed by the launcher.
"""
from pathlib import Path
import os
import re
import shutil
import sys


def main():
    args=sys.argv[1:]
    path=Path(__file__).resolve().parents[1]/'.env'
    if args[:1]==['--env-file']:
        path=Path(args[1]).resolve();args=args[2:]
    if not args:raise SystemExit('Usage: with_env.py [--env-file PATH] COMMAND [ARGS...]')
    env=dict(os.environ)
    if path.exists():
        for line in path.read_text().splitlines():
            match=re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=',line)
            if match:env.pop(match[1],None)
    uv=shutil.which('uv')
    if not uv:raise SystemExit('Install uv to run configured local commands.')
    os.execve(uv,[uv,'run',*(['--env-file',str(path)] if path.exists() else ['--no-env-file']),*args],env)


if __name__=='__main__':main()
