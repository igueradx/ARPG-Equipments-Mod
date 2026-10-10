#!/usr/bin/env python3
"""Validate the ARPG chest item pools against the pinned rAthena database.

Checks, in order:
  1. every `Item:` resolves to an AegisName that exists in the era's item tables
  2. no duplicate `Item:` inside a subgroup
  3. `Index:` values are unique inside a subgroup
  4. the renewal and pre-renewal files agree on subgroups 2-4

Usage: python3 tools/validate_pool.py [--check names|duplicates|indices|era-parity]
Exit code 0 = clean, 1 = problems found.
"""

import argparse
import os
import re
import sys
import urllib.request

RATHENA = "https://raw.githubusercontent.com/Flux159/rathena/8ff133fb8296fbec98d85b0bb970d78f176ef0a7"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "arpg-pool-validate")

# rAthena AegisName lines are indented, and at least one upstream entry has two
# spaces after the colon (id 490049, Sin_Necklace_T), so match a run of whitespace.
AEGIS = re.compile(r"^\s+AegisName:\s+(\S+)\s*$")
ITEM = re.compile(r"^\s+Item:\s*(\S+)\s*$")
INDEX = re.compile(r"^\s+- Index:\s*(\d+)\s*$")
SUBGROUP = re.compile(r"^\s+- SubGroup:\s*(\d+)\s*$")

TABLES = ("item_db_equip.yml", "item_db_etc.yml", "item_db_usable.yml")
POOLS = {
    "re": ["db/item_group_db.yml"],
    "pre-re": ["pre-renewal/db/item_group_db.yml"],
}
# Subgroups 2-4 exist in both era files and must match; 5-7 are renewal only.
SHARED_SUBGROUPS = (2, 3, 4)


def fetch(era, name):
    path = os.path.join(CACHE, era, name)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        url = "{0}/db/{1}/{2}".format(RATHENA, era, name)
        with urllib.request.urlopen(url, timeout=60) as response, open(path, "wb") as handle:
            handle.write(response.read())
    return path


def aegis_names(era):
    names = set()
    for name in TABLES:
        for line in open(fetch(era, name), encoding="utf-8", errors="replace"):
            match = AEGIS.match(line)
            if match:
                names.add(match.group(1))
    return names


def parse_pool(path):
    """Return {subgroup: [(index, item), ...]} for one pool file."""
    groups = {}
    subgroup = None
    for line in open(path, encoding="utf-8", errors="replace"):
        match = SUBGROUP.match(line)
        if match:
            subgroup = int(match.group(1))
            groups.setdefault(subgroup, [])
            continue
        match = INDEX.match(line)
        if match and subgroup is not None:
            groups[subgroup].append([int(match.group(1)), None])
            continue
        match = ITEM.match(line)
        if match and subgroup is not None and groups[subgroup]:
            groups[subgroup][-1][1] = match.group(1)
    return groups


def duplicates(values):
    seen = set()
    repeated = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        choices=["names", "duplicates", "indices", "era-parity"],
        help="run a single check instead of all of them",
    )
    parser.add_argument(
        "--root",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="repository root (default: parent of this script's folder)",
    )
    args = parser.parse_args()

    def wanted(check):
        return args.check in (None, check)

    problems = 0
    pools = {
        era: parse_pool(os.path.join(args.root, paths[0]))
        for era, paths in POOLS.items()
    }
    for era in sorted(pools):
        groups = pools[era]
        names = aegis_names(era) if wanted("names") else None
        for subgroup in sorted(groups):
            entries = groups[subgroup]
            label = "{0} SG{1}".format(POOLS[era][0], subgroup)
            items = [entry[1] for entry in entries]
            if names is not None:
                invalid = sorted({item for item in items if item not in names})
                if invalid:
                    print("INVALID {0}: {1}".format(label, invalid))
                    problems += 1
            if wanted("duplicates"):
                repeated = duplicates(items)
                if repeated:
                    print("DUPLICATE {0}: {1}".format(label, repeated))
                    problems += 1
            if wanted("indices"):
                repeated = duplicates([entry[0] for entry in entries])
                if repeated:
                    print("INDEX COLLISION {0}: {1}".format(label, repeated))
                    problems += 1
            print("{0}: {1} entries".format(label, len(entries)))

    if wanted("era-parity"):
        renewal = pools["re"]
        pre_renewal = pools["pre-re"]
        for subgroup in SHARED_SUBGROUPS:
            if [e[1] for e in renewal[subgroup]] != [e[1] for e in pre_renewal[subgroup]]:
                print("ERA MISMATCH SG{0}".format(subgroup))
                problems += 1
        unexpected = sorted(set(pre_renewal) - set(SHARED_SUBGROUPS))
        if unexpected:
            print("UNEXPECTED subgroups in the pre-renewal file: {0}".format(unexpected))
            problems += 1
        else:
            print("SG2/SG3/SG4 identical across era files: OK")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
