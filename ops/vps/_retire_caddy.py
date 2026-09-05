"""Remove one vhost block (and the comment directly above it) from a Caddyfile.

Brace-counted rather than regexed, because a vhost body contains nested blocks
and a naive match would eat the rest of the file — which here would take down
minecraft.yashnas.xyz and manhwamaniacs.xyz.
"""

import sys

path, host = sys.argv[1], sys.argv[2]
lines = open(path).read().split("\n")
out: list[str] = []
i = 0
while i < len(lines):
    if lines[i].startswith(f"{host}:80 {{"):
        while out and (out[-1].lstrip().startswith("#") or out[-1].strip() == ""):
            out.pop()
        depth = 0
        while i < len(lines):
            depth += lines[i].count("{") - lines[i].count("}")
            i += 1
            if depth == 0:
                break
        continue
    out.append(lines[i])
    i += 1
open(path, "w").write("\n".join(out).rstrip("\n") + "\n")
print(f"  removed vhost {host}")
