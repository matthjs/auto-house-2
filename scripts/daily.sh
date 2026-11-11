#!/usr/bin/env bash
# Daily job: batch-draft new listings on each site, then email the search's members a
# digest. Sends nothing to landlords. The search comes from AUTO_HOUSE_SEARCH in .env.
#
#   scripts/daily.sh                  # flatfox and email_alerts
#   scripts/daily.sh flatfox woko     # other sites
#   DIGEST_NOTE="Test run" scripts/daily.sh   # extra line at the top of the email
#
# Example crontab line (crontab -e), every day at 07:00:
#   0 7 * * * /path/to/auto-house-2/scripts/daily.sh >> /path/to/auto-house-2/out/daily.log 2>&1
set -u
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:$PATH"   # uv, when started by cron
mkdir -p out

# Never run twice at the same time.
exec 9>out/.daily.lock
if ! flock -n 9; then
    echo "$(date -Is) another run is still going; skipping"
    exit 0
fi

if [ "$#" -eq 0 ]; then
    set -- flatfox email_alerts
fi

echo "$(date -Is) daily run: $*"
status=0
for site in "$@"; do
    uv run python main.py site="$site" command=run || status=1
done
digest_args=(command=digest digest.enabled=true)
if [ -n "${DIGEST_NOTE:-}" ]; then
    digest_args+=("digest.note='${DIGEST_NOTE//\'/}'")
fi
uv run python main.py "${digest_args[@]}" || status=1
echo "$(date -Is) done (exit $status)"
exit "$status"
