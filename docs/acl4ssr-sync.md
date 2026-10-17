# ACL4SSR Ruleset repeatable sync

## Scope

Upstream: https://github.com/ACL4SSR/ACL4SSR

Only upstream `Clash/Ruleset/` is mirrored into `sources/acl4ssr/Clash/Ruleset/`. Files are copied byte-for-byte. Existing active lists and INI files are not changed. Upstream files removed in a later snapshot are removed only inside the managed `sources/acl4ssr/` directory. Do not put custom edits there.

`source-lock.json` records the resolved upstream commit, file count, byte lengths and SHA-256 checksums. No timestamp is included, so repeating the same snapshot produces no content changes.

## First and subsequent syncs

In GitHub Actions, select `Sync ACL4SSR Ruleset`, choose `main`, then Run workflow. There is no schedule or push trigger. Use `master` for the current upstream version, or a full commit SHA for reproducibility. The initially inspected upstream commit was `575637df38884575bfa523e95c17d0ee3be1676c`; use it for the first snapshot if that exact inspected version is desired.

The workflow commits only `sources/acl4ssr/` directly to main. It needs Actions enabled and permission to write repository contents. Branch protection may reject its push; no protection is bypassed. Concurrent external updates to main may also reject the push; inspect and rerun rather than force pushing.

Installing this workflow does not itself download or commit a snapshot. The first manual run is required.

## Local usage

Requires Git and Python 3:

```sh
python3 scripts/sync_acl4ssr.py --ref 575637df38884575bfa523e95c17d0ee3be1676c
git diff --stat
git diff -- sources/acl4ssr/source-lock.json
```

The local script changes only the managed snapshot directory and does not commit or push. Fetching and materialization finish in a staging directory before replacing an existing managed snapshot. Filesystem failure during final replacement is not transactional; use Git to restore if necessary.

## Review and rollback

Review each snapshot commit and its lock manifest. To undo a sync, revert that snapshot commit through the normal reviewed Git procedure. Reverting a snapshot does not modify active routing rules because the snapshot is not referenced by the INI.

Upstream rule names are source labels, not verified business routing decisions. Classification, conflict analysis, licensing review before redistribution, and production rule generation are separate steps. Preserve upstream attribution and applicable license requirements when incorporating these lists into published derivatives.
