#!/usr/bin/env python3
"""Coordinate independent AI harness peers through the Riff skill."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from riff_core import Coordinator, RunRequest, ValidationError
from riff_core.state import RunStore


def _read_json(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).expanduser().read_text()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValidationError("request must be a JSON object")
    return value


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt is not None and args.prompt_file is not None:
        raise ValidationError("use only one of --prompt and --prompt-file")
    if args.prompt is not None:
        prompt = args.prompt
    elif args.prompt_file is not None:
        prompt = Path(args.prompt_file).expanduser().read_text()
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read()
    else:
        raise ValidationError("provide --prompt, --prompt-file, or prompt text on stdin")
    if not prompt.strip():
        raise ValidationError("prompt must not be empty")
    return prompt


def _coordinator(args: argparse.Namespace) -> Coordinator:
    root = Path(args.state_dir).expanduser().resolve() if args.state_dir else None
    return Coordinator(store=RunStore(root))


def command_run(args: argparse.Namespace) -> dict[str, Any]:
    request = RunRequest.from_dict(_read_json(args.request))
    coordinator = _coordinator(args)
    coordinator.validate(request)
    run_id = args.run_id or str(uuid.uuid4())
    if args.detach:
        return _detach(coordinator, request, run_id)
    # Announce the run before blocking so a driver can inspect it from another call
    # instead of searching the state directory for the newest run.
    print(
        json.dumps(
            {
                "event": "started",
                "run_id": run_id,
                "progress": f"{coordinator.script_invocation()} progress --run-id {run_id}",
            }
        ),
        file=sys.stderr,
        flush=True,
    )
    return coordinator.run(request, run_id=run_id)


def _detach(coordinator: Coordinator, request: RunRequest, run_id: str) -> dict[str, Any]:
    """Start the run in its own process group and return at once; follow it with wait."""
    folder = coordinator.store.root / "detached"
    folder.mkdir(parents=True, exist_ok=True)
    request_file = folder / f"{run_id}.request.json"
    request_file.write_text(json.dumps(request.to_dict()))
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--state-dir",
        str(coordinator.store.root),
        "run",
        "--request",
        str(request_file),
        "--run-id",
        run_id,
    ]
    with (folder / f"{run_id}.out").open("w") as out, (folder / f"{run_id}.err").open("w") as err:
        process = subprocess.Popen(
            command, stdout=out, stderr=err, stdin=subprocess.DEVNULL, start_new_session=True
        )
    (folder / f"{run_id}.pid").write_text(str(process.pid))
    return {
        "ok": True,
        "run_id": run_id,
        "status": "running",
        "warnings": coordinator.warnings(request),
        "next_steps": [
            (
                f"Follow it with {coordinator.script_invocation()} wait --run-id {run_id} "
                "(returns within about nine minutes; call again while it reports running)."
            )
        ],
    }


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    request = RunRequest.from_dict(_read_json(args.request))
    coordinator = _coordinator(args)
    validated = coordinator.validate(request)
    return {
        "ok": True,
        "warnings": coordinator.warnings(validated),
        "request": validated.to_dict(),
    }


def command_reply(args: argparse.Namespace) -> dict[str, Any]:
    return _coordinator(args).reply(
        args.run_id,
        args.participant,
        _read_prompt(args),
        timeout_seconds=args.timeout_seconds,
    )


def command_wait(args: argparse.Namespace) -> dict[str, Any]:
    return _coordinator(args).wait(args.run_id, timeout_seconds=args.timeout_seconds)


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    return _coordinator(args).status(args.run_id)


def command_capabilities(args: argparse.Namespace) -> dict[str, Any]:
    return _coordinator(args).capabilities()


def command_progress(args: argparse.Namespace) -> dict[str, Any]:
    return _coordinator(args).progress(
        args.run_id,
        participant_id=args.participant,
        include_previews=args.previews,
    )


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    return _coordinator(args).verify(
        args.run_id,
        verifier=args.verifier,
        result=args.result,
        checks=args.check,
        integrated=args.integrated,
        note=args.note,
        commands=args.run,
        cwd=args.cwd,
        command_timeout_seconds=args.run_timeout_seconds,
        view_changed=None if args.view_changed is None else args.view_changed == "yes",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        help="Override Riff state root (default: $RIFF_STATE_DIR or XDG state)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def accept_state_dir(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--state-dir",
            default=argparse.SUPPRESS,
            help="Override Riff state root for this command",
        )

    run = commands.add_parser("run", help="start a consult, discussion, or delegation")
    accept_state_dir(run)
    run.add_argument("--request", required=True, help="request JSON file, or - for stdin")
    run.add_argument("--run-id", help="optional preallocated canonical UUID")
    run.add_argument(
        "--detach",
        action="store_true",
        help="start the run in the background and return its id; follow with wait",
    )
    run.set_defaults(handler=command_run)

    wait = commands.add_parser("wait", help="block until a run settles, within a bound")
    accept_state_dir(wait)
    wait.add_argument("--run-id", required=True)
    wait.add_argument("--timeout-seconds", type=int, default=540)
    wait.set_defaults(handler=command_wait)

    validate = commands.add_parser("validate", help="validate and normalize a request")
    accept_state_dir(validate)
    validate.add_argument("--request", required=True, help="request JSON file, or - for stdin")
    validate.set_defaults(handler=command_validate)

    reply = commands.add_parser("reply", help="continue one participant's native session")
    accept_state_dir(reply)
    reply.add_argument("--run-id", required=True)
    reply.add_argument("--participant", required=True)
    reply.add_argument("--prompt")
    reply.add_argument("--prompt-file")
    reply.add_argument(
        "--timeout-seconds",
        type=int,
        help="override the prior turn timeout for this reply",
    )
    reply.set_defaults(handler=command_reply)

    status = commands.add_parser("status", help="show a run and participant session state")
    accept_state_dir(status)
    status.add_argument("--run-id", required=True)
    status.set_defaults(handler=command_status)

    capabilities = commands.add_parser(
        "capabilities", help="show installed harness adapter capabilities"
    )
    accept_state_dir(capabilities)
    capabilities.set_defaults(handler=command_capabilities)

    progress = commands.add_parser(
        "progress", help="inspect participant progress, including live Pi traces"
    )
    accept_state_dir(progress)
    progress.add_argument("--run-id", required=True)
    progress.add_argument("--participant")
    progress.add_argument(
        "--previews",
        action="store_true",
        help="include short thinking/text previews (may reveal sensitive content)",
    )
    progress.set_defaults(handler=command_progress)

    verify = commands.add_parser("verify", help="record driver verification and integration")
    accept_state_dir(verify)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--verifier", required=True)
    verify.add_argument(
        "--result",
        choices=("passed", "partial", "failed", "not_performed"),
        help="derived from --run exit codes when omitted; required otherwise",
    )
    verify.add_argument(
        "--run",
        action="append",
        default=[],
        help="shell command to execute as a check; its exit code is recorded",
    )
    verify.add_argument(
        "--cwd", help="directory for --run commands (default: first participant's cwd)"
    )
    verify.add_argument("--run-timeout-seconds", type=int, default=600)
    verify.add_argument(
        "--check",
        action="append",
        default=[],
        help="free-text check the driver performed; recorded as asserted, not executed",
    )
    verify.add_argument(
        "--view-changed",
        choices=("yes", "no"),
        help="whether the peers changed the driver's recorded prediction or view",
    )
    verify.add_argument("--integrated", action="store_true")
    verify.add_argument("--note")
    verify.set_defaults(handler=command_verify)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except (ValidationError, RuntimeError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
