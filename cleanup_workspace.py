#!/usr/bin/env python3
"""
Safely clean workspace by archiving common clutter (logs, temp outputs).

By default this script performs a dry-run and shows what would be moved.
Pass `--apply` to actually move files into a timestamped `.trash/` folder.

Examples:
  python cleanup_workspace.py        # dry-run
  python cleanup_workspace.py --apply  # perform archive
  python cleanup_workspace.py --apply --include-output  # also archive ./output/*
"""
import argparse
import os
import shutil
import glob
from datetime import datetime


DEFAULT_PATTERNS = [
    'build_log*.txt',
    'run_log*.txt',
    'run_log*.log',
    'run_log*',
    '*.log',
    'test.mp4',
    'test_predictions.png',
    'training_curves.png',
    'test_predictions.png',
    'build_log3.txt',
    'build_log2.txt',
    'build_log.txt',
    'run_log.txt',
    'run_log2.txt',
    'run_log3.txt',
    'run_log4.txt',
]


def find_matches(root, patterns, include_output=False):
    matches = set()
    for p in patterns:
        for path in glob.glob(os.path.join(root, p)):
            matches.add(os.path.normpath(path))

    if include_output:
        out_dir = os.path.join(root, 'output')
        if os.path.isdir(out_dir):
            for path in glob.glob(os.path.join(out_dir, '*')):
                matches.add(os.path.normpath(path))

    return sorted(matches)


def archive_paths(paths, root, apply=False):
    if not paths:
        print('No files matched. Nothing to do.')
        return

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    trash_dir = os.path.join(root, '.trash', ts)
    if apply:
        os.makedirs(trash_dir, exist_ok=True)

    for p in paths:
        rel = os.path.relpath(p, root)
        dest = os.path.join(trash_dir, rel) if apply else os.path.join('.trash', rel)
        print(f"{('MOVE' if apply else 'DRY')}: {rel} -> {os.path.relpath(dest, root)}")
        if apply:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                if os.path.isdir(p):
                    shutil.move(p, dest)
                else:
                    shutil.move(p, dest)
            except Exception as e:
                print(f"  ERROR moving {p}: {e}")

    if apply:
        print(f'Archived {len(paths)} items into: {trash_dir}')
    else:
        print('Dry-run complete. No files were moved. Re-run with --apply to archive.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Actually move files to .trash/')
    parser.add_argument('--include-output', action='store_true', help='Include files under ./output in the cleanup')
    parser.add_argument('--patterns', nargs='*', help='Additional glob patterns to match (project-root relative)')
    args = parser.parse_args()

    root = os.getcwd()
    patterns = DEFAULT_PATTERNS.copy()
    if args.patterns:
        patterns.extend(args.patterns)

    matches = find_matches(root, patterns, include_output=args.include_output)

    print('\nWorkspace cleanup summary:')
    print(f'  Project root: {root}')
    print(f'  Patterns: {patterns}')
    print(f'  Include output/: {args.include_output}')
    print(f'  Matched items: {len(matches)}')
    for p in matches:
        print('   -', os.path.relpath(p, root))

    archive_paths(matches, root, apply=args.apply)


if __name__ == '__main__':
    main()
