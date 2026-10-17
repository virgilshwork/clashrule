#!/usr/bin/env bash
# Isolated conversion + kernel-load acceptance for a generated candidate.
#
# Reproduces the acceptance that was performed manually: serve the freshly generated
# candidates/ tree locally, convert the reference INI with SubConverter using a stub node
# source (six node NAMES, no credentials), then assert on the converted YAML with mihomo.
#
# The candidate INI references snapshot URLs that do not exist in the repository at gate
# time, so the base URL is rewritten to a local file server. Nothing is committed here.
#
# Usage:
#   scripts/run_conversion_acceptance.sh --candidates-dir candidates --work /tmp/acceptance
#
# Optional: --subconverter PATH --mihomo PATH (otherwise pinned releases are downloaded),
#           --cases FILE --port PORT
set -euo pipefail

CANDIDATES_DIR="candidates"
WORK="/tmp/candidate-acceptance"
SUBCONVERTER_TAG="v0.9.0"
MIHOMO_TAG="v1.19.32"
CASES="policy/acceptance-cases.json"
PORT="28501"
SUB_BIN=""
MIHOMO_BIN=""

while [ $# -gt 0 ]; do
  case "$1" in
    --candidates-dir) CANDIDATES_DIR="$2"; shift 2 ;;
    --work) WORK="$2"; shift 2 ;;
    --cases) CASES="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --subconverter) SUB_BIN="$2"; shift 2 ;;
    --mihomo) MIHOMO_BIN="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

INI="$(find "$CANDIDATES_DIR" -maxdepth 1 -name 'virgil-candidate.ini' | head -1)"
if [ -z "$INI" ]; then echo "candidate INI not found under $CANDIDATES_DIR" >&2; exit 2; fi
SNAPSHOT_DIR="$(find "$CANDIDATES_DIR/snapshots" -maxdepth 1 -mindepth 1 -type d | head -1)"
MANIFEST="$SNAPSHOT_DIR/manifest.json"

rm -rf "$WORK"; mkdir -p "$WORK/mihomo-home"
echo "== inputs =="
echo "   INI      : $INI"
echo "   manifest : $MANIFEST"
echo "   cases    : $CASES"

# --- tools -------------------------------------------------------------------
if [ -z "$SUB_BIN" ]; then
  curl -fsSL -o "$WORK/subconverter.tar.gz" \
    "https://github.com/tindy2013/subconverter/releases/download/${SUBCONVERTER_TAG}/subconverter_linux64.tar.gz"
  tar -xzf "$WORK/subconverter.tar.gz" -C "$WORK"
  SUB_BIN="$WORK/subconverter/subconverter"
fi
if [ -z "$MIHOMO_BIN" ]; then
  curl -fsSL -o "$WORK/mihomo.gz" \
    "https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_TAG}/mihomo-linux-amd64-${MIHOMO_TAG}.gz"
  gunzip -c "$WORK/mihomo.gz" > "$WORK/mihomo"
  chmod +x "$WORK/mihomo"
  MIHOMO_BIN="$WORK/mihomo"
fi
chmod +x "$SUB_BIN"
PROF_DIR="$(dirname "$SUB_BIN")/profiles"
mkdir -p "$PROF_DIR"

# --- subconverter preferences -------------------------------------------------
# max_allowed_rulesets is 64 by default in v0.9.0; the candidate needs ~130 lists and the
# overflow is reported only as a WARN while the tool still reports SUCCESS. Raise it and
# fail loudly if the warning appears anyway.
SUB_DIR="$(dirname "$SUB_BIN")"
python3 - "$SUB_DIR" <<'PY'
import re, sys, pathlib
sub_dir = pathlib.Path(sys.argv[1])
pref = sub_dir / 'pref.toml'
if pref.exists():
    text = pref.read_text(encoding='utf-8')
    text = re.sub(r'^api_mode\s*=.*$', 'api_mode = false', text, count=1, flags=re.M)
    text = re.sub(r'^max_allowed_rulesets\s*=.*$', 'max_allowed_rulesets = 512', text, count=1, flags=re.M)
    pref.write_text(text, encoding='utf-8')
    print('pref.toml: api_mode=false, max_allowed_rulesets=512')
else:
    print('pref.toml not found; defaults will be used and the ruleset limit may apply')
PY

cp policy/stub-subscription.txt "$PROF_DIR/stub.txt"
# subconverter parses comments poorly: feed it the base64 form of the link list
python3 - "$PROF_DIR/stub.txt" "$PROF_DIR/stub.b64" <<'PY'
import base64, pathlib, sys
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
links = [l.strip() for l in src.read_text(encoding='utf-8').splitlines()
         if l.strip() and not l.strip().startswith((';', '#'))]
dst.write_text(base64.b64encode('\n'.join(links).encode()).decode(), encoding='utf-8')
print('stub subscription: %d node links' % len(links))
PY
CAND_ABS="$(cd "$CANDIDATES_DIR" && pwd)"
CAND_NAME="$(basename "$CAND_ABS")"
SERVE_ROOT="$(dirname "$CAND_ABS")"
if [ "$CAND_NAME" != "candidates" ]; then echo "candidates dir must be named candidates (served path uses that prefix)" >&2; exit 2; fi
python3 - "$INI" "$PROF_DIR/candidate.local.ini" "$CAND_NAME" "$PORT" <<'PY'
import pathlib, sys
ini, out, cand_name, port = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4]
base = 'https://raw.githubusercontent.com/'
lines = []
replaced = 0
for line in ini.read_text(encoding='utf-8').splitlines():
    if line.startswith('ruleset=') and base in line:
        head, _, rest = line.partition('ruleset=')
        group, _, url = rest.partition(',')
        marker = '/main/'
        idx = url.find(marker)
        if idx != -1:
            url = 'http://127.0.0.1:%s/' % port + url[idx + len(marker):]
            replaced += 1
        lines.append('ruleset=%s,%s' % (group, url))
    else:
        lines.append(line)
out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('rewrote %d ruleset URLs to the local server' % replaced)
PY

cat > "$PROF_DIR/acceptance.profile" <<EOF
[Profile]
target=clash
emoji=false
url=profiles/stub.b64
config=profiles/candidate.local.ini
EOF
cat > "$SUB_DIR/generate.ini" <<EOF
[acceptance]
path=$WORK/candidate.yaml
profile=profiles/acceptance.profile
EOF

# --- local file server --------------------------------------------------------
python3 -m http.server "$PORT" --directory "$SERVE_ROOT" > "$WORK/http.log" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
sleep 2

# --- conversion --------------------------------------------------------------
echo "== conversion =="
( cd "$SUB_DIR" && "$SUB_BIN" -g ) > "$WORK/conversion.log" 2>&1 || true
if grep -qi 'exceeded limit' "$WORK/conversion.log"; then
  echo "FAIL: external ruleset limit exceeded; conversion output would be the built-in default" >&2
  exit 1
fi
if [ ! -s "$WORK/candidate.yaml" ]; then
  echo "FAIL: no YAML produced; tail of conversion log:" >&2
  tail -20 "$WORK/conversion.log" >&2
  exit 1
fi
echo "   produced $(wc -c < "$WORK/candidate.yaml") bytes"

# --- assertions ---------------------------------------------------------------
echo "== assertions =="
python3 scripts/verify_candidate_conversion.py "$WORK/candidate.yaml" \
  --manifest "$MANIFEST" --ini "$INI" --cases "$CASES" \
  --conversion-log "$WORK/conversion.log" --mihomo "$MIHOMO_BIN" \
  --mihomo-dir "$WORK/mihomo-home"
STATUS=$?
echo "== report: $WORK/verify-report.json =="
exit $STATUS
