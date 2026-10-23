# Who Writes the Exam? — official evaluation replays

This public repository runs the preregistered dynamic grading-impact experiment on standard GitHub-hosted `ubuntu-24.04` runners. It uses the pinned SWE-bench-Live evaluator commit `62d02936a0726fbf4597b05bd07b09fb99eddae6` and preserves official reports, parsed status files, raw post-patch logs, Docker image identifiers/digests, console logs, and generated ablation tasks as workflow artifacts.

The workflow enforces two gates:

1. Each priority Go task runs the unmodified FULL prediction first. TARGETED and SHAM removals run only if that task's published PASS/FAIL verdict is reproduced.
2. The remaining eight FULL replays run only if both priority verdicts reproduce.

No result in this repository should be treated as verified until its uploaded raw artifact and `summary.json` have been inspected.
