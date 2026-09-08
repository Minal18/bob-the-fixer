# Bob the Fixer — Product Requirements

## Problem Statement

Engineering teams spend significant reviewer time on repetitive, low-judgment PR feedback — missing null checks, inconsistent error handling, obvious security gaps, style deviations — before a human reviewer ever gets to the parts of a PR that actually need their judgment. This slows down review turnaround and makes review quality inconsistent across teams, since it depends on who happens to review a given PR.

## Goal

Give every team a self-service, AI-powered first-pass reviewer that catches common issues automatically, using standards *that team* defines — without requiring a central team to configure or maintain it per repo.

## Non-Goals

- Not a replacement for human review — Bob supplements, doesn't approve or block merges by default.
- Not a one-size-fits-all linter — review instructions are configurable per repo, not globally fixed.
- Not enabled by default — teams opt in explicitly, repo by repo.

## Target Users

| User | Need |
|---|---|
| Engineer opening a PR | Fast, relevant first-pass feedback before requesting human review |
| Human reviewer | Fewer repetitive comments to write themselves |
| Team lead | Ability to enable/configure Bob for their repos without depending on a platform team |

## Scope — v1

- Install once per org; teams opt in per repo via a bot command, not on by default.
- Per-repo config file controls what Bob checks for (focus areas, ignored paths, custom instructions).
- Bob posts inline, line-level comments on the relevant diff lines — no summary comment.
- Basic feedback capture (👍/👎 on Bob's comments) to gauge usefulness.

## Out of Scope — v1 (future consideration)

- Auto-blocking merge based on severity.
- Dashboard/UI for enabling repos (v1 uses a bot comment command).

## Success Metrics

| Category | Metric | Why it matters |
|---|---|---|
| Adoption | # repos enabled, # teams onboarded | Are teams choosing to turn this on? |
| Quality | 👍/👎 ratio on Bob's comments | Is the feedback actually useful? |
| Quality | Comment acted-upon rate (line changed after Bob's comment) | Stronger signal than reactions — feedback that changes behavior |
| Operational | Review latency (PR opened → comment posted) | Is it fast enough to be useful before human review starts? |

## Open Questions

- What's the right default review focus for a repo with no config file — skip entirely, or apply a sane org-wide default?

---
Tech doc (architecture, data model, implementation approach) follows separately.
