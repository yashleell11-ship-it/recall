"""Remove one hostname's ingress rule from a cloudflared config."""

import sys

path, host = sys.argv[1], sys.argv[2]
lines = open(path).read().splitlines()
out: list[str] = []
i = 0
while i < len(lines):
    if lines[i].strip() == f"- hostname: {host}":
        i += 2  # the hostname line and the service line under it
        continue
    out.append(lines[i])
    i += 1
open(path, "w").write("\n".join(out) + "\n")
print(f"  removed ingress {host}")
