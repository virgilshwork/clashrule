#!/usr/bin/env bash
# Regression tests for the candidate acceptance gate.
#
# Covers what the review asked for:
#   A. positive            : fresh candidate converts, kernel-loads and passes every assertion
#   B. multi-snapshot      : an older snapshot directory exists too; the gate must follow
#                            candidates/manifest.json -> publication_id, not directory order
#   C. negative (identity) : INI references a different snapshot than the root manifest -> fail fast
#   D. negative (missing)  : root manifest points at a snapshot that is absent -> fail fast
#   E. negative (assertions): tampered expectations -> the verifier must fail with clear errors
#
# Usage: scripts/tests/acceptance_gate_tests.sh [--work DIR] [--subconverter BIN] [--mihomo BIN]
# Logs and reports are kept under <work>/logs for later inspection.
set -euo pipefail

WORK=""
SUB_BIN=""
MIHOMO_BIN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --work) WORK="$2"; shift 2 ;;
    --subconverter) SUB_BIN="$2"; shift 2 ;;
    --mihomo) MIHOMO_BIN="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
WORK="${WORK:-$(mktemp -d /tmp/gate-tests.XXXXXX)}"
mkdir -p "$WORK/logs"
PY="${PY:-python3}"

echo "== building a fresh candidate locally (no commit, no publish) =="
rm -rf "$WORK/business-output" "$WORK/candidates"
"$PY" scripts/build_business_rules.py --seed policy/business-draft.json --layout policy/business-layout.json \
  --output "$WORK/business-output" > "$WORK/logs/build.log" 2>&1
"$PY" scripts/publish_candidate_references.py --input "$WORK/business-output" --publish-root "$WORK/candidates" \
  > "$WORK/logs/publish.log" 2>&1
NEW_ID="$("$PY" -c "import json;print(json.load(open('$WORK/candidates/manifest.json',encoding='utf-8'))['publication_id'])")"
echo "   new publication_id: $NEW_ID"

# --- B. decoy: an older snapshot must not be selected -------------------------
DECOY="$WORK/candidates/snapshots/0000oldersnapshot0000"
mkdir -p "$DECOY"
echo '{"managed_by":"decoy","publication_id":"0000oldersnapshot0000","ordered_fragments":[],"files":[]}' > "$DECOY/manifest.json"
cp "$WORK/candidates/virgil-candidate.ini" "$DECOY/virgil-candidate.ini"
echo "   decoy snapshot: $(basename "$DECOY") (sorts before the real one)"

run_gate() { # $1=candidates dir, $2=log name, $3=work dir
  local cand="$1" name="$2" wdir="$3"
  mkdir -p "$wdir"
  set +e
  bash scripts/run_conversion_acceptance.sh --candidates-dir "$cand" --work "$wdir" \
       ${SUB_BIN:+--subconverter "$SUB_BIN"} ${MIHOMO_BIN:+--mihomo "$MIHOMO_BIN"} \
       > "$WORK/logs/$name.log" 2>&1
  echo $?
}

declare -A RESULT
RESULT[A_positive]="$(run_gate "$WORK/candidates" A_positive "$WORK/run-a")"
RESULT[C_identity_mismatch]=$(
  # a valid candidates layout whose INI points at a snapshot the root manifest does not name
  mkdir -p "$WORK/cand-badid"
  cp -a "$WORK/candidates" "$WORK/cand-badid/candidates"
  mkdir -p "$WORK/cand-badid/candidates/snapshots/ffffffffffffffffffffffffffffffff"
  cp -a "$WORK/candidates/snapshots/$NEW_ID/." "$WORK/cand-badid/candidates/snapshots/ffffffffffffffffffffffffffffffff/"
  sed -i "s/snapshots\/$NEW_ID\//snapshots\/ffffffffffffffffffffffffffffffff\//g" "$WORK/cand-badid/candidates/virgil-candidate.ini"
  run_gate "$WORK/cand-badid/candidates" C_identity_mismatch "$WORK/run-c"
)
RESULT[D_missing_snapshot]=$(
  mkdir -p "$WORK/cand-missing"
  cp -a "$WORK/candidates" "$WORK/cand-missing/candidates"
  "$PY" - "$WORK/cand-missing/candidates/manifest.json" <<'PY'
import json, sys
path = sys.argv[1]
doc = json.load(open(path, encoding='utf-8'))
doc['publication_id'] = 'deadbeefdeadbeefdeadbeefdeadbeef'
json.dump(doc, open(path, 'w', encoding='utf-8'))
PY
  run_gate "$WORK/cand-missing/candidates" D_missing_snapshot "$WORK/run-d"
)
RESULT[E_tampered_assertions]=$(
  set +e
  # deliberately wrong expectations: rule count, node and business for a host that resolves fine
  cat > "$WORK/bad-cases.json" <<'JSON'
{"cases": [{"host": "youtube.com", "business": "🌐 普通海外业务", "node": "HK_Evoxt"},
           {"host": "auth0.com", "business": "🤖 OpenAI-Anthropic", "node": "OSAKA_Premium"}]}
JSON
  "$PY" scripts/verify_candidate_conversion.py "$WORK/run-a/candidate.yaml" \
     --manifest "$WORK/candidates/snapshots/$NEW_ID/manifest.json" \
     --ini "$WORK/candidates/virgil-candidate.ini" \
     --expect-groups 41 --expect-rules 1 --cases "$WORK/bad-cases.json" \
     > "$WORK/logs/E_tampered_assertions.log" 2>&1
  echo $?
)

RESULT[F_workdir_guards]=$(
  set +e
  local_ok=0
  bash scripts/run_conversion_acceptance.sh --candidates-dir "$WORK/candidates" --work "$REPO_ROOT" >/dev/null 2>&1 || local_ok=$((local_ok+1))
  bash scripts/run_conversion_acceptance.sh --candidates-dir "$WORK/candidates" --work relative-work >/dev/null 2>&1 || local_ok=$((local_ok+1))
  bash scripts/run_conversion_acceptance.sh --candidates-dir "$WORK/candidates" --work "$WORK/logs" >/dev/null 2>&1 || local_ok=$((local_ok+1))
  # all three must be refused: report 0 only when every guard fired
  if [ "$local_ok" = "3" ]; then echo 0; else echo 99; fi
)

echo
echo "== results (0 = pass, non-zero = correctly refused) =="
printf '   A positive (multi-snapshot present)      exit=%s (expect 0)\n' "${RESULT[A_positive]}"
printf '   C snapshot identity mismatch            exit=%s (expect non-zero)\n' "${RESULT[C_identity_mismatch]}"
printf '   D manifest points at missing snapshot   exit=%s (expect non-zero)\n' "${RESULT[D_missing_snapshot]}"
printf '   E tampered expectations (verifier)      exit=%s (expect non-zero)\n' "${RESULT[E_tampered_assertions]}"
printf '   F work-dir guards (repo/relative/used)  exit=%s (expect 0 = all refused)\n' "${RESULT[F_workdir_guards]}"
echo
echo "== key log lines =="
grep -h "snapshot identity" "$WORK/logs/A_positive.log" | sed 's/^/   A: /' || true
grep -h "FAIL" "$WORK/logs/C_identity_mismatch.log" | head -2 | sed 's/^/   C: /' || true
grep -h "FAIL\|not found" "$WORK/logs/D_missing_snapshot.log" | head -2 | sed 's/^/   D: /' || true
echo
echo "   logs: $WORK/logs"

STATUS=0
[ "${RESULT[A_positive]}" = "0" ] || STATUS=1
[ "${RESULT[C_identity_mismatch]}" != "0" ] || STATUS=1
[ "${RESULT[D_missing_snapshot]}" != "0" ] || STATUS=1
[ "${RESULT[E_tampered_assertions]}" != "0" ] || STATUS=1
[ "${RESULT[F_workdir_guards]}" = "0" ] || STATUS=1
exit $STATUS
