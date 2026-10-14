# Decisions

1. Adopt owner BUILD_SPEC.md as implementation contract; retain old plan as history.
2. Base new branch on PR #2 because main is an ancestor. No merge of PR #2.
3. Test current stable, not old CI claims. Python 3.14 for current host dependencies.
4. No owner runtime/home/config access. Fail-closed test network fence.
5. Random event IDs cannot order equal timestamps; preserve segment append order.
   Cross-process timestamp ties are not proof of chronological ordering.
6. Never claim all-HTTP budget enforcement around the current generation-only API.
7. No UI-shaped JSON or renderer boolean is trusted approval. Missing capabilities
   stay visible while independent closed projection/collector work continues.
8. Core 3425846 adds opt-in raw bounds and one exact probe preview. Do not enable
   other probes until their full request scope can be reviewed.
9. Fixture services accept explicit loopback targets; no runtime discovery.
10. Contribution restart resets LOCAL_ONLY and purges unsent packages, sacrificing
    convenience to avoid ambiguous consent. Native production bridge is incomplete.
11. Workbench aggregates are recomputed from retained packages; no additional
    long-lived aggregate store or backup-erasure promise. Suppression is not anonymity.
12. Retain broad failures/skips. Narrow passes cannot substitute for full acceptance.
