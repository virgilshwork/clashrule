#!/usr/bin/env bash
# Isolated conversion + kernel-load acceptance for a generated candidate.
#
# Deterministic inputs: candidates/manifest.json -> publication_id -> snapshots/<id>/manifest.json.
# The snapshot is NEVER chosen by directory order (candidates/snapshots/ keeps history, so
# `find ... | head -1` could validate a new INI against an old manifest).
#
# Safety properties:
#   * the work directory must be an absolute path outside the repository; an existing non-empty
#     --work directory is refused instead of deleted
#   * SubConverter always runs from a copy inside the work directory; no external tree is modified
#   * the local file server binds 127.0.0.1 only
#   * the stub node source carries six node NAMES and no credentials
#
# Usage:
#   scripts/run_conversion_acceptance.sh [--candidates-dir DIR] [--work DIR] [--cases FILE]
#                                        [--subconverter BIN] [--mihomo BIN] [--port PORT]
set -euo pipefail

CANDIDATES_DIR="candidates"
WORK=""
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

# --- work directory guards ----------------------------------------------------
if [ -z "$WORK" ]; then
  WORK="$(mktemp -d /tmp/candidate-acceptance.XXXXXX)"
else
  case "$WORK" in
    /*) : ;;
    *) echo "work directory must be absolute: $WORK" >&2; exit 2 ;;
  esac
  if [ "$WORK" = "/" ] || [ "$WORK" = "$HOME" ] || [ "$WORK" = "$REPO_ROOT" ]; then
    echo "refusing to use $WORK as a work directory" >&2; exit 2
  fi
  case "$WORK" in
    "$REPO_ROOT"/*) echo "work directory must live outside the repository" >&2; exit 2 ;;
  esac
  if [ -e "$WORK" ] && [ -n "$(ls -A "$WORK" 2>/dev/null)" ]; then
    echo "work directory already exists and is not empty: $WORK (choose a fresh path)" >&2
    exit 2
  fi
fi
mkdir -p "$WORK/mihomo-home"

# --- deterministic snapshot resolution ---------------------------------------
if [ -z "$CANDIDATES_DIR" ] || [ "$CANDIDATES_DIR" = "/" ]; then
  echo "invalid candidates directory: $CANDIDATES_DIR" >&2; exit 2
fi
CAND_ABS="$(cd "$CANDIDATES_DIR" && pwd)"
CAND_NAME="$(basename "$CAND_ABS")"
SERVE_ROOT="$(dirname "$CAND_ABS")"
if [ "$CAND_NAME" != "candidates" ]; then
  echo "the candidates directory must be named 'candidates' (rewritten URLs use that prefix)" >&2
  exit 2
fi
ROOT_MANIFEST="$CAND_ABS/manifest.json"
INI="$CAND_ABS/virgil-candidate.ini"
[ -f "$ROOT_MANIFEST" ] || { echo "missing $ROOT_MANIFEST; cannot resolve the snapshot deterministically" >&2; exit 2; }
[ -f "$INI" ] || { echo "candidate INI not found: $INI" >&2; exit 2; }
PUBLICATION_ID="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get('publication_id',''))" "$ROOT_MANIFEST")"
[ -n "$PUBLICATION_ID" ] || { echo "$ROOT_MANIFEST has no publication_id" >&2; exit 2; }
MANIFEST="$CAND_ABS/snapshots/$PUBLICATION_ID/manifest.json"
[ -f "$MANIFEST" ] || { echo "snapshot manifest not found for publication_id=$PUBLICATION_ID: $MANIFEST" >&2; exit 2; }
python3 - "$INI" "$PUBLICATION_ID" <<'PY'
import pathlib, re, sys
ini, publication_id = pathlib.Path(sys.argv[1]), sys.argv[2]
ids = set(re.findall(r'snapshots/([0-9a-f]{16,})/', ini.read_text(encoding='utf-8')))
if not ids:
    raise SystemExit('FAIL: candidate INI references no snapshot id')
if ids != {publication_id}:
    raise SystemExit('FAIL: INI references %s but root manifest publication_id is %s' % (sorted(ids), publication_id))
print('snapshot identity: %s (INI and root manifest agree)' % publication_id)
PY

echo "== inputs =="
echo "   candidates : $CAND_ABS"
echo "   snapshot   : $PUBLICATION_ID"
echo "   manifest   : $MANIFEST"
echo "   cases      : $CASES"
echo "   work       : $WORK"

# --- tools: SubConverter is always used from a copy inside the work dir -------
if [ -n "$SUB_BIN" ]; then
  [ -x "$SUB_BIN" ] || { echo "subconverter not executable: $SUB_BIN" >&2; exit 2; }
  cp -a "$(dirname "$SUB_BIN")" "$WORK/subconverter-tree"
  SUB_DIR="$WORK/subconverter-tree"
  SUB_BIN="$SUB_DIR/$(basename "$SUB_BIN")"
else
  curl -fsSL -o "$WORK/subconverter.tar.gz" \
    "https://github.com/tindy2013/subconverter/releases/download/${SUBCONVERTER_TAG}/subconverter_linux64.tar.gz"
  tar -xzf "$WORK/subconverter.tar.gz" -C "$WORK"
  SUB_DIR="$WORK/subconverter"
  SUB_BIN="$SUB_DIR/subconverter"
fi
chmod +x "$SUB_BIN"
if [ -z "$MIHOMO_BIN" ]; then
  curl -fsSL -o "$WORK/mihomo.gz" \
    "https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_TAG}/mihomo-linux-amd64-${MIHOMO_TAG}.gz"
  gunzip -c "$WORK/mihomo.gz" > "$WORK/mihomo"
  chmod +x "$WORK/mihomo"
  MIHOMO_BIN="$WORK/mihomo"
else
  [ -x "$MIHOMO_BIN" ] || { echo "mihomo not executable: $MIHOMO_BIN" >&2; exit 2; }
fi

# --- preferences, on the copy only -------------------------------------------
python3 - "$SUB_DIR" <<'PY'
import pathlib, re, sys
sub_dir = pathlib.Path(sys.argv[1])
pref = sub_dir / 'pref.toml'
if not pref.exists():
    raise SystemExit('FAIL: no pref.toml in the SubConverter copy; cannot raise max_allowed_rulesets safely')
text = pref.read_text(encoding='utf-8')
text = re.sub(r'^api_mode\s*=.*$', 'api_mode = false', text, count=1, flags=re.M)
text = re.sub(r'^max_allowed_rulesets\s*=.*$', 'max_allowed_rulesets = 512', text, count=1, flags=re.M)
pref.write_text(text, encoding='utf-8')
print('pref.toml (work copy): api_mode=false, max_allowed_rulesets=512')
PY

# --- profiles (SubConverter reads them relative to its own directory) ---------
PROF_DIR="$SUB_DIR/profiles"
mkdir -p "$PROF_DIR"
cp policy/stub-subscription.txt "$PROF_DIR/stub.txt"
python3 - "$PROF_DIR/stub.txt" "$PROF_DIR/stub.b64" <<'PY'
import base64, pathlib, sys
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
links = [l.strip() for l in src.read_text(encoding='utf-8').splitlines()
         if l.strip() and not l.strip().startswith((';', '#'))]
if not links:
    raise SystemExit('FAIL: stub subscription contains no node links')
dst.write_text(base64.b64encode('\n'.join(links).encode()).decode(), encoding='utf-8')
print('stub subscription: %d node links (no credentials)' % len(links))
PY
python3 - "$INI" "$PROF_DIR/candidate.local.ini" "$PORT" <<'PY'
import pathlib, sys
ini, out, port = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
replaced = 0
lines = []
for line in ini.read_text(encoding='utf-8').splitlines():
    if line.startswith('ruleset=') and 'raw.githubusercontent.com' in line:
        group, _, url = line[len('ruleset='):].partition(',')
        idx = url.find('/main/')
        if idx != -1:
            url = 'http://127.0.0.1:%s/' % port + url[idx + len('/main/'):]
            replaced += 1
        lines.append('ruleset=%s,%s' % (group, url))
    else:
        lines.append(line)
out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('rewrote %d ruleset URLs to the loopback server' % replaced)
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

# --- loopback-only file server ------------------------------------------------
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$SERVE_ROOT" > "$WORK/http.log" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
sleep 2
FIRST_FRAGMENT="$(python3 -c "
import pathlib, re
urls = re.findall(r'ruleset=[^,]+,(http://[^\s]+)', pathlib.Path('$PROF_DIR/candidate.local.ini').read_text(encoding='utf-8'))
print(urls[0] if urls else '')")"
[ -n "$FIRST_FRAGMENT" ] || { echo "FAIL: no rewritten ruleset URL found" >&2; exit 1; }
curl -fsS -o /dev/null "$FIRST_FRAGMENT" || { echo "FAIL: loopback server cannot serve $FIRST_FRAGMENT" >&2; exit 1; }

# --- conversion ---------------------------------------------------------------
echo "== conversion =="
( cd "$SUB_DIR" && "$SUB_BIN" -g ) > "$WORK/conversion.log" 2>&1 || true
if grep -qi 'exceeded limit' "$WORK/conversion.log"; then
  echo "FAIL: external ruleset limit exceeded; the output would be the built-in default" >&2
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
set +e
python3 scripts/verify_candidate_conversion.py "$WORK/candidate.yaml" \
  --manifest "$MANIFEST" --ini "$INI" --cases "$CASES" \
  --conversion-log "$WORK/conversion.log" --mihomo "$MIHOMO_BIN" \
  --mihomo-dir "$WORK/mihomo-home"
STATUS=$?
set -e
echo "== report: $WORK/verify-report.json =="
exit $STATUS
