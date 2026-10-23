#!/usr/bin/env python3
"""Run one pinned SWE-bench-Live replay and preserve machine-readable evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys
import time
import traceback
from typing import Any


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def capture(cmd: list[str], *, cwd: pathlib.Path | None = None) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    return {"command": cmd, "returncode": p.returncode, "output": p.stdout}


def stream(cmd: list[str], log: pathlib.Path, *, cwd: pathlib.Path) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8", errors="replace") as out:
        out.write("COMMAND: " + json.dumps(cmd) + "\n")
        out.flush()
        p = subprocess.Popen(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, bufsize=1)
        assert p.stdout is not None
        for line in p.stdout:
            sys.stdout.write(line)
            out.write(line)
        return p.wait()


def find_one(root: pathlib.Path, name: str) -> pathlib.Path | None:
    hits = sorted(root.rglob(name))
    return hits[0] if hits else None


def exact_string(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle
    if isinstance(value, dict):
        return any(k == needle or exact_string(v, needle) for k, v in value.items())
    if isinstance(value, list):
        return any(exact_string(v, needle) for v in value)
    return False


def analyze_condition(out_dir: pathlib.Path, instance_id: str,
                      required_tests: list[str], linked_test: str | None) -> dict[str, Any]:
    report_path = find_one(out_dir, "report.json")
    status_path = find_one(out_dir, "status.json")
    post_log_path = find_one(out_dir, "post_patch_log.txt")
    result: dict[str, Any] = {
        "output_dir": str(out_dir),
        "report_path": str(report_path) if report_path else None,
        "status_path": str(status_path) if status_path else None,
        "post_patch_log_path": str(post_log_path) if post_log_path else None,
    }
    report = json.loads(report_path.read_text()) if report_path else None
    status = json.loads(status_path.read_text()) if status_path else None
    raw = post_log_path.read_text(errors="replace") if post_log_path else ""
    result["resolved"] = report.get("resolved") if isinstance(report, dict) else None
    result["required_test_execution"] = {
        test: {
            "exact_in_status": exact_string(status, test) if status is not None else False,
            "substring_in_status_json": test in json.dumps(status, ensure_ascii=False) if status is not None else False,
            "substring_in_post_patch_log": test in raw,
        }
        for test in required_tests
    }
    if linked_test:
        result["linked_test_execution"] = result["required_test_execution"].get(
            linked_test,
            {
                "exact_in_status": exact_string(status, linked_test) if status is not None else False,
                "substring_in_status_json": linked_test in json.dumps(status, ensure_ascii=False) if status is not None else False,
                "substring_in_post_patch_log": linked_test in raw,
            },
        )
    return result


def official_eval(evaluator: pathlib.Path, dataset: pathlib.Path, prediction: pathlib.Path,
                  output_dir: pathlib.Path, log_path: pathlib.Path) -> int:
    cmd = [
        str(evaluator / ".venv" / "bin" / "python"), "-m", "evaluation.evaluation",
        "--dataset", str(dataset), "--platform", "linux",
        "--patch_dir", str(prediction), "--output_dir", str(output_dir),
        "--workers", "1", "--overwrite", "1",
    ]
    return stream(cmd, log_path, cwd=evaluator)


def write_summary(path: pathlib.Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--mode", choices=["priority", "full-only"], required=True)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--evaluator", required=True)
    ap.add_argument("--results-root", required=True)
    args = ap.parse_args()

    repo_root = pathlib.Path(args.repo_root).resolve()
    replay = repo_root / "replay"
    evaluator = pathlib.Path(args.evaluator).resolve()
    result_root = pathlib.Path(args.results_root).resolve() / args.instance_id
    result_root.mkdir(parents=True, exist_ok=True)
    summary_path = result_root / "summary.json"
    manifest = json.loads((replay / "replay_manifest.json").read_text())
    cases = {x["instance_id"]: x for x in manifest["cases"]}
    case = cases[args.instance_id]
    expected = case["reported_status"] == "resolved"
    task_path = replay / case["task_path"]
    prediction = replay / case["prediction_path"]
    task = json.loads(task_path.read_text().splitlines()[0])
    prediction_object = json.loads(prediction.read_text())
    prediction_record = prediction_object[args.instance_id]
    model_patch_hash = sha256_text(prediction_record["model_patch"])
    required_tests = list(dict.fromkeys(task.get("FAIL_TO_PASS", []) + task.get("PASS_TO_PASS", [])))
    plan = json.loads((replay / "ablation_plan.json").read_text()).get(args.instance_id, {})
    linked_test = plan.get("targeted", {}).get("test_id")
    summary: dict[str, Any] = {
        "schema_version": 1,
        "instance_id": args.instance_id,
        "mode": args.mode,
        "expected_published_resolved": expected,
        "reported_status": case["reported_status"],
        "evaluator_commit": manifest["evaluator_commit"],
        "submission_commit": manifest["submission_commit"],
        "dataset_revision": manifest["dataset_revision"],
        "started_utc_epoch": int(time.time()),
        "runner": {
            "platform": platform.platform(),
            "python": sys.version,
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "runner_image": os.environ.get("ImageOS"),
            "runner_image_version": os.environ.get("ImageVersion"),
        },
        "input_hashes": {
            "full_task_jsonl_sha256": sha256(task_path),
            "full_prediction_json_sha256": sha256(prediction),
            "model_patch_sha256_observed": model_patch_hash,
            "model_patch_sha256_expected": case["model_patch_sha256"],
            "model_patch_sha256_matches_manifest": model_patch_hash == case["model_patch_sha256"],
        },
        "docker_image": task["docker_image"],
        "required_tests": required_tests,
        "linked_test_id": linked_test,
        "conditions": {},
        "full_verdict_reproduced": False,
        "ablation_gate_opened": False,
        "errors": [],
    }
    write_summary(summary_path, summary)

    try:
        env = {
            "docker_version": capture(["docker", "version"]),
            "docker_info": capture(["docker", "info"]),
            "disk_before": capture(["df", "-h"]),
        }
        (result_root / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
        pull = stream(["docker", "pull", task["docker_image"]], result_root / "docker_pull.log", cwd=repo_root)
        if pull != 0:
            raise RuntimeError(f"docker pull failed with exit code {pull}")
        inspect = capture(["docker", "image", "inspect", task["docker_image"]])
        (result_root / "docker_image_inspect.json").write_text(inspect["output"])
        image_obj = json.loads(inspect["output"])[0]
        summary["image_evidence"] = {
            "image_id": image_obj.get("Id"),
            "repo_digests": image_obj.get("RepoDigests", []),
            "created": image_obj.get("Created"),
            "architecture": image_obj.get("Architecture"),
            "os": image_obj.get("Os"),
        }

        full_out = result_root / "full"
        rc = official_eval(evaluator, task_path, prediction, full_out, result_root / "full_console.log")
        summary["conditions"]["full"] = analyze_condition(full_out, args.instance_id, required_tests, linked_test)
        summary["conditions"]["full"]["evaluator_exit_code"] = rc
        actual = summary["conditions"]["full"]["resolved"]
        summary["full_verdict_reproduced"] = (rc == 0 and actual is expected)
        write_summary(summary_path, summary)

        if args.mode == "priority" and summary["full_verdict_reproduced"]:
            summary["ablation_gate_opened"] = True
            for condition in ("targeted", "sham"):
                spec = plan[condition]
                generated = result_root / f"{condition}_task.jsonl"
                prep_cmd = [
                    sys.executable, str(replay / "prepare_go_ablation.py"),
                    "--task", str(task_path), "--test-name", spec["test_name"],
                    "--test-id", spec["test_id"], "--output", str(generated),
                ]
                prep = capture(prep_cmd, cwd=repo_root)
                (result_root / f"{condition}_prepare.log").write_text(prep["output"])
                if prep["returncode"] != 0:
                    raise RuntimeError(f"{condition} preparation failed: {prep['output'][-2000:]}")
                generated_task = json.loads(generated.read_text().splitlines()[0])
                list_removed = all(spec["test_id"] not in generated_task.get(k, []) for k in ("FAIL_TO_PASS", "PASS_TO_PASS"))
                function_still_in_patch = f"func {spec['test_name']}(" in generated_task.get("test_patch", "")
                cond_out = result_root / condition
                cond_rc = official_eval(evaluator, generated, prediction, cond_out, result_root / f"{condition}_console.log")
                data = analyze_condition(cond_out, args.instance_id, required_tests, linked_test)
                data.update({
                    "evaluator_exit_code": cond_rc,
                    "removed_test_id": spec["test_id"],
                    "removed_test_function": spec["test_name"],
                    "removed_from_scoring_lists": list_removed,
                    "function_signature_still_in_test_patch": function_still_in_patch,
                    "generated_task_sha256": sha256(generated),
                    "verdict_changed_from_full": data.get("resolved") != actual if data.get("resolved") is not None else None,
                })
                summary["conditions"][condition] = data
                write_summary(summary_path, summary)

        summary["disk_after"] = capture(["df", "-h"])
        summary["completed_utc_epoch"] = int(time.time())
        write_summary(summary_path, summary)
        return 0
    except Exception as exc:
        summary["errors"].append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        summary["completed_utc_epoch"] = int(time.time())
        write_summary(summary_path, summary)
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
