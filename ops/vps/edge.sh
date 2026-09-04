#!/usr/bin/env bash
# Wire Recall into the SHARED Caddy + cloudflared that also serve the Minecraft
# bots and manhwamaniacs. Idempotent: safe to re-run. Backs up both files first,
# and validates the Caddy config BEFORE reloading, because a syntax error here
# takes down minecraft.yashnas.xyz and manhwamaniacs.xyz too.
set -euo pipefail

HOST="${RECALL_HOST:-recall.yashnas.xyz}"
CADDYFILE=/opt/mcbots/edge/Caddyfile
CFCONF=/opt/mcbots/edge/cloudflared/config.yml
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "==> host: $HOST"

# ---------- Caddy ----------
if sudo grep -q "^${HOST}:80 {" "$CADDYFILE"; then
  echo "==> Caddy vhost already present, leaving it alone"
else
  sudo cp "$CADDYFILE" "${CADDYFILE}.bak-recall-${STAMP}"
  sudo tee -a "$CADDYFILE" >/dev/null <<EOF

# Recall — study app. API and web under ONE hostname so the browser never makes
# a cross-origin request: /api/* goes to the backend, everything else to Next.
${HOST}:80 {
	import sec
	import zip
	import logroll recall
	@insecure header X-Forwarded-Proto http
	redir @insecure https://${HOST}{uri} 308
	header Strict-Transport-Security "max-age=300"

	handle /api/* {
		reverse_proxy recall-backend:8000
	}
	handle {
		reverse_proxy recall-frontend:3000
	}
}
EOF
  echo "==> Caddy vhost appended (backup: ${CADDYFILE}.bak-recall-${STAMP})"
fi

echo "==> validating Caddy config before touching the running server"
if ! docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  echo "!! Caddy config INVALID — restoring backup and aborting without reloading" >&2
  sudo cp "${CADDYFILE}.bak-recall-${STAMP}" "$CADDYFILE" 2>/dev/null || true
  docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile || true
  exit 1
fi
echo "==> config valid; reloading Caddy (graceful, no dropped connections)"
docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile

# ---------- cloudflared ----------
if grep -q "hostname: ${HOST}" "$CFCONF"; then
  echo "==> cloudflared ingress already present, leaving it alone"
else
  cp "$CFCONF" "${CFCONF}.bak-recall-${STAMP}"
  # Insert before the catch-all 404 rule, which must stay last.
  python3 - "$CFCONF" "$HOST" <<'PY'
import sys
path, host = sys.argv[1], sys.argv[2]
lines = open(path).read().splitlines()
out, inserted = [], False
for line in lines:
    if not inserted and line.strip().startswith("- service: http_status:404"):
        out.append(f"  - hostname: {host}")
        out.append("    service: http://caddy:80")
        inserted = True
    out.append(line)
assert inserted, "catch-all 404 rule not found; refusing to guess where to insert"
open(path, "w").write("\n".join(out) + "\n")
PY
  echo "==> cloudflared ingress added (backup: ${CFCONF}.bak-recall-${STAMP})"
  echo "==> restarting cloudflared (~2s; briefly interrupts the other tunnelled hosts)"
  docker restart cloudflared >/dev/null
fi

echo
echo "==> done. Remaining step is DNS, which is yours to do:"
echo "    In Cloudflare, add a CNAME for '${HOST%%.*}' on ${HOST#*.}"
echo "    pointing to e40ede74-c9c0-454d-9983-3a6ce2866a47.cfargotunnel.com, Proxied."
