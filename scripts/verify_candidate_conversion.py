#!/usr/bin/env python3
"""Acceptance assertions for a converted Clash candidate config.

Closes the gaps found in the first review round:

  1. conversion warnings are inspected (ruleset-count limit, fetch failures) and the number of
     fetched rulesets is compared with the round's manifest
  2. the rule tail is compared against the inline rules declared by the candidate INI
     (``ruleset=<group>,[]GEOIP,CN`` / ``ruleset=<group>,[]FINAL`` -> ``GEOIP,CN,<group>`` / ``MATCH,<group>``)
  3. required node names and group names are derived from the INI, not from CLI flags
  4. rules that precede the first domain match are reported; only non-``no-resolve`` IP rules,
     process rules and geo rules are treated as potentially preempting a domain decision
  5. cases assert BOTH the business group (chain head) and the terminal node, so two businesses that
     currently share an exit node cannot pass with a wrong classification

Rule counts are derived per round from the manifest (fragments + inline GEOIP + FINAL) and never
hard-coded. No credentials are read or written; the report contains no node connection parameters.

Usage:
  python3 verify_candidate_conversion.py CONFIG.yaml \
      --manifest reference-manifest.json --ini virgil-candidate.ini \
      --cases policy/acceptance-cases.json --conversion-log conversion.log \
      --mihomo /path/to/mihomo [--mihomo-dir DIR] [--allow-conditional-prior]

Exit code 0 = every assertion passed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

import yaml

CONDITIONAL_KINDS = {"PROCESS-NAME", "SRC-IP-CIDR", "GEOIP", "GEOSITE", "MATCH", "FINAL", "IP-CIDR", "IP-CIDR6"}
WARNING_PATTERNS = (
    "exceeded limit",
    "failed to fetch",
    "fetch failed",
    "no ruleset",
    "ruleset count",
)


def load_yaml(path):
    with open(path, encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def resolve(group_map, name):
    chain, seen = [], set()
    while name in group_map:
        if name in seen:
            return chain + ["<cycle>"]
        seen.add(name)
        chain.append(name)
        members = group_map[name].get("proxies") or []
        if not members:
            return chain + ["<empty>"]
        name = members[0]
    chain.append(name)
    return chain


def ini_groups(ini_path):
    """Return (all group names, role/node names from regex selectors, inline tail rules)."""
    names, nodes, tail = [], set(), []
    with open(ini_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            match = re.match(r"custom_proxy_group=([^`]+)`(select|url-test|fallback)`(.*)$", line)
            if match:
                names.append(match.group(1))
                for node in re.findall(r"\(\^([^$|)]+)\$", match.group(3)):
                    nodes.add(node)
                continue
            inline = re.match(r"ruleset=([^,]+),\[\]([A-Z-]+)(?:,([^,]+))?$", line)
            if inline:
                group, kind, value = inline.group(1), inline.group(2), inline.group(3)
                if kind in ("GEOIP", "FINAL"):
                    target = "MATCH" if kind == "FINAL" else kind
                    tail.append("%s,%s,%s" % (target, value or "CN", group) if value or kind == "GEOIP" else "%s,%s" % (target, group))
    return names, nodes, tail


def first_domain_match(rules, host):
    """First domain match plus the rules skipped beforehand (conditional ones flagged)."""
    skipped_conditional, skipped_passive = [], []
    for idx, rule in enumerate(rules):
        text = str(rule)
        parts = [p.strip() for p in text.split(",")]
        kind = parts[0].upper()
        if kind == "DOMAIN" and len(parts) > 1 and parts[1] == host:
            return idx, text, skipped_conditional, skipped_passive
        if kind == "DOMAIN-SUFFIX" and len(parts) > 1 and (host == parts[1] or host.endswith("." + parts[1])):
            return idx, text, skipped_conditional, skipped_passive
        if kind == "DOMAIN-KEYWORD" and len(parts) > 1 and parts[1] in host:
            return idx, text, skipped_conditional, skipped_passive
        if kind in CONDITIONAL_KINDS:
            passive = kind in ("IP-CIDR", "IP-CIDR6") and any(p == "no-resolve" for p in parts)
            (skipped_passive if passive else skipped_conditional).append(text)
    return None, None, skipped_conditional, skipped_passive


def inspect_conversion_log(path, expected_rulesets):
    warnings, fetched = [], set()
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            low = line.lower()
            if any(pattern in low for pattern in WARNING_PATTERNS):
                warnings.append(line.strip()[:200])
            match = re.search(r"updating ruleset url '([^']+)'", low)
            if match:
                fetched.add(match.group(1))
    result = {"warnings": warnings, "rulesets_fetched": len(fetched)}
    if expected_rulesets:
        result["expected_rulesets"] = expected_rulesets
        result["fetch_complete"] = len(fetched) >= expected_rulesets
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--manifest")
    parser.add_argument("--ini")
    parser.add_argument("--cases", help="JSON file with {'cases':[{'host','business','node'}]}")
    parser.add_argument("--conversion-log")
    parser.add_argument("--expect-rules", type=int)
    parser.add_argument("--expect-groups", type=int)
    parser.add_argument("--expect-node", action="append", default=[])
    parser.add_argument("--expect-tail", action="append", default=[])
    parser.add_argument("--mihomo")
    parser.add_argument("--mihomo-dir", default="/tmp/mihomo-home")
    parser.add_argument("--allow-conditional-prior", action="store_true")
    args = parser.parse_args()

    errors, notes = [], []
    document = load_yaml(args.config)
    proxies = document.get("proxies") or []
    groups = document.get("proxy-groups") or []
    rules = [str(r) for r in (document.get("rules") or [])]
    node_names = {p.get("name") for p in proxies if isinstance(p, dict)}
    group_map = {g.get("name"): g for g in groups if isinstance(g, dict)}

    declared_groups, ini_nodes, ini_tail = ([], set(), [])
    if args.ini:
        declared_groups, ini_nodes, ini_tail = ini_groups(args.ini)

    # 1) rule count, dynamic per round
    expected_fragments = None
    expect_rules = args.expect_rules
    if args.manifest:
        manifest = json.load(open(args.manifest, encoding="utf-8"))
        fragments = manifest.get("ordered_fragments") or []
        expected_fragments = len(fragments)
        if expect_rules is None:
            expect_rules = sum(int(f.get("rules") or 0) for f in fragments)
    if expect_rules is not None and args.ini:
        # inline rules are already part of the manifest-derived count; never add them twice
        derived = expect_rules + len(ini_tail)
        if args.expect_rules is not None and args.expect_rules != derived:
            errors.append("explicit --expect-rules %d disagrees with derived %d (manifest fragments + %d inline rules)"
                          % (args.expect_rules, derived, len(ini_tail)))
        else:
            expect_rules = derived
            notes.append("expected rule count = manifest fragments + %d inline rules" % len(ini_tail))
    if expect_rules is not None and len(rules) != expect_rules:
        errors.append("rule count %d != expected %d for this round" % (len(rules), expect_rules))

    # snapshot identity: the INI must reference the snapshot the manifest describes
    snapshot_report = None
    if args.ini and args.manifest:
        manifest_id = json.load(open(args.manifest, encoding="utf-8")).get("publication_id")
        referenced = set(re.findall(r"snapshots/([0-9a-f]{16,})/", open(args.ini, encoding="utf-8").read()))
        snapshot_report = {"manifest_publication_id": manifest_id, "ini_referenced_ids": sorted(referenced)}
        if not referenced:
            errors.append("candidate INI does not reference a snapshot id")
        elif manifest_id not in referenced:
            errors.append("INI references %s but manifest publication_id is %s" % (sorted(referenced), manifest_id))

    # 3) groups / nodes derived from the INI
    if args.expect_groups is not None and len(groups) != args.expect_groups:
        errors.append("group count %d != expected %d (--expect-groups)" % (len(groups), args.expect_groups))
    if declared_groups and len(declared_groups) != len(groups):
        errors.append("group count %d != %d declared by the INI" % (len(groups), len(declared_groups)))
    missing_groups = sorted(set(declared_groups) - set(group_map))
    if missing_groups:
        errors.append("declared groups missing from output: %s" % ", ".join(missing_groups))
    required_nodes = set(args.expect_node) | ini_nodes
    missing_nodes = sorted(required_nodes - node_names)
    if missing_nodes:
        errors.append("missing required node names: %s" % ", ".join(missing_nodes))

    # 1b) conversion log
    log_report = None
    if args.conversion_log:
        log_report = inspect_conversion_log(args.conversion_log, expected_fragments)
        if log_report["warnings"]:
            errors.append("conversion log contains %d warning(s); first: %s" % (len(log_report["warnings"]), log_report["warnings"][0]))
        if log_report.get("fetch_complete") is False:
            errors.append("only %d rulesets fetched, manifest declares %d" % (log_report["rulesets_fetched"], expected_fragments or -1))

    # 2) rule tail against inline INI declarations
    expect_tail = args.expect_tail or ini_tail
    tail_report = {"expected": expect_tail, "actual": rules[-len(expect_tail):] if expect_tail else rules[-2:]}
    if expect_tail:
        if tail_report["actual"] != expect_tail:
            errors.append("rule tail %s != expected %s" % (tail_report["actual"], expect_tail))
    elif not rules or not rules[-1].startswith("MATCH"):
        errors.append("rule tail does not end with MATCH: %s" % tail_report["actual"])
    if rules and not rules[-1].startswith("MATCH"):
        notes.append("last rule is not MATCH: %s" % rules[-1])

    # 5) cases: business AND node
    cases = []
    if args.cases:
        cases = json.load(open(args.cases, encoding="utf-8")).get("cases", [])
    case_results = []
    for case in cases:
        host = case["host"]
        idx, rule, conditional, passive = first_domain_match(rules, host)
        if rule is None:
            case_results.append({"host": host, "ok": False, "reason": "no domain rule matched"})
            errors.append("no domain rule matched for %s" % host)
            continue
        target = [p.strip() for p in rule.split(",")][-1]
        chain = resolve(group_map, target)
        business, node = chain[0], chain[-1]
        ok_node = not case.get("node") or node == case["node"]
        ok_business = not case.get("business") or business == case["business"]
        # 4) a preceding conditional rule means the domain-first-hit is not conclusive
        ok_conditional = not conditional or args.allow_conditional_prior
        entry = {
            "host": host,
            "ok": ok_node and ok_business and ok_conditional,
            "rule_index": idx,
            "rule": rule,
            "business": business,
            "default_chain": chain,
            "expected_business": case.get("business"),
            "expected_node": case.get("node"),
        }
        if conditional:
            entry["preceding_conditional_rules"] = conditional[:5]
        if passive:
            entry["preceding_passive_ip_rules"] = len(passive)
        case_results.append(entry)
        if not ok_business:
            errors.append("%s business %s != expected %s" % (host, business, case.get("business")))
        if not ok_node:
            errors.append("%s node %s != expected %s" % (host, node, case.get("node")))
        if not ok_conditional:
            errors.append("%s has preceding conditional rules; domain-first-hit is not conclusive" % host)

    # kernel load
    mihomo_report = None
    if args.mihomo:
        os.makedirs(args.mihomo_dir, exist_ok=True)
        proc = subprocess.run(
            [args.mihomo, "-t", "-f", args.config, "-d", args.mihomo_dir],
            capture_output=True,
            text=True,
            timeout=300,
        )
        mihomo_report = {"exit_code": proc.returncode, "tail": proc.stdout.strip().splitlines()[-3:]}
        if proc.returncode != 0:
            errors.append("mihomo -t exited %d" % proc.returncode)

    report = {
        "config": os.path.abspath(args.config),
        "rules": len(rules),
        "groups": len(groups),
        "node_count": len(node_names),
        "expected_rules": expect_rules,
        "expected_fragments": expected_fragments,
        "missing_declared_groups": missing_groups,
        "missing_required_nodes": missing_nodes,
        "conversion_log": log_report,
        "snapshot_identity": snapshot_report,
        "rule_tail": tail_report,
        "cases": case_results,
        "mihomo_config_check": mihomo_report,
        "notes": notes,
        "errors": errors,
        "pass": not errors,
        "boundary": "conversion and kernel-load assertions only; runtime selector cache, real connections, node membership of the live subscription and business functionality are NOT covered",
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(args.config)), "verify-report.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"pass": report["pass"], "rules": len(rules), "groups": len(groups), "errors": errors[:5], "report": out_path}, ensure_ascii=False))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
