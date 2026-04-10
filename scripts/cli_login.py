from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from urllib import error, request


def _post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        detail = text
        try:
            parsed = json.loads(text)
            detail = parsed.get("detail", text)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _print_agent_response(response: dict, show_next_action: bool) -> None:
    print(f"\nagent> {response.get('response', '')}")
    if show_next_action:
        print(f"next_action: {response.get('next_action', '')}")


def _run_auth_flow(agent_url: str, session_id: str, auth_headers: dict[str, str], preferred_type: str) -> bool:
    try:
        challenge = _post_json(
            f"{agent_url.rstrip('/')}/auth/challenge/start",
            {"session_id": session_id, "preferred_type": preferred_type},
            headers=auth_headers,
        )
    except RuntimeError as exc:
        print(f"Could not start auth challenge: {exc}")
        return False

    challenge_type = challenge.get("challenge_type", preferred_type)
    challenge_id = challenge.get("challenge_id", "")
    if not challenge_id:
        print("Auth challenge response was missing challenge_id.")
        return False

    print(f"Auth challenge started ({challenge_type}).")

    while True:
        value = getpass.getpass(f"Enter {challenge_type.upper()}: ")
        try:
            result = _post_json(
                f"{agent_url.rstrip('/')}/auth/challenge/verify",
                {"challenge_id": challenge_id, "value": value},
                headers=auth_headers,
            )
        except RuntimeError as exc:
            print(f"Challenge verify failed: {exc}")
            return False

        verified = bool(result.get("verified"))
        next_step = result.get("next_step", "retry")
        message = result.get("message", "")
        print(f"Auth result: {message}")

        if verified and next_step == "proceed":
            return True
        if next_step == "retry":
            continue
        if next_step == "otp_fallback":
            challenge_type = "otp"
            print("Switching to OTP challenge.")
            continue
        return False


def _send_agent_message(agent_url: str, session_id: str, auth_headers: dict[str, str], message: str) -> dict:
    return _post_json(
        f"{agent_url.rstrip('/')}/agent/message",
        {"session_id": session_id, "message": message},
        headers=auth_headers,
    )


def _confirm_execution(agent_url: str, session_id: str, auth_headers: dict[str, str], confirmed: bool) -> dict:
    return _post_json(
        f"{agent_url.rstrip('/')}/agent/confirm",
        {"session_id": session_id, "confirmed": confirmed},
        headers=auth_headers,
    )


def _handle_followup_actions(
    agent_url: str,
    session_id: str,
    auth_headers: dict[str, str],
    response: dict,
    preferred_type: str,
    show_next_action: bool,
) -> None:
    current = response
    while True:
        _print_agent_response(current, show_next_action=show_next_action)
        next_action = current.get("next_action")

        if next_action == "auth_challenge":
            verified = _run_auth_flow(agent_url, session_id, auth_headers, preferred_type)
            if not verified:
                print("Authentication not completed.")
                return
            try:
                current = _send_agent_message(agent_url, session_id, auth_headers, "continue")
            except RuntimeError as exc:
                print(f"Could not continue after auth verification: {exc}")
                return
            continue

        if next_action == "ready_to_execute":
            answer = input("Approve transfer? [y/N]: ").strip().lower()
            confirmed = answer in {"y", "yes"}
            try:
                current = _confirm_execution(agent_url, session_id, auth_headers, confirmed)
            except RuntimeError as exc:
                print(f"Could not submit confirmation: {exc}")
                return
            continue

        return


def _run_chat_loop(
    agent_url: str,
    session_id: str,
    auth_headers: dict[str, str],
    preferred_type: str,
    show_next_action: bool,
) -> None:
    print("\nInteractive session started.")
    print("Type your messages. Use /exit to quit.")

    while True:
        message = input("\nyou> ").strip()
        if not message:
            continue
        if message.lower() in {"/exit", "exit", "quit", "/quit"}:
            print("Session ended.")
            return

        try:
            response = _send_agent_message(agent_url, session_id, auth_headers, message)
        except RuntimeError as exc:
            print(f"Message failed: {exc}")
            continue

        _handle_followup_actions(
            agent_url,
            session_id,
            auth_headers,
            response,
            preferred_type,
            show_next_action=show_next_action,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Single CLI script: login with email+password, then run interactive agent loop.")
    parser.add_argument("--agent-url", default="http://localhost:8000", help="Agent base URL")
    parser.add_argument("--email", help="Registered email")
    parser.add_argument("--password", help="Password set during signup")
    parser.add_argument(
        "--preferred-auth",
        choices=["pin", "otp"],
        default="pin",
        help="Preferred challenge type when agent requests authentication",
    )
    parser.add_argument(
        "--output",
        default=".agent_session.json",
        help="Path to write session token and session id",
    )
    parser.add_argument(
        "--show-next-action",
        action="store_true",
        help="Show internal next_action field for debugging",
    )
    args = parser.parse_args()

    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Password: ")

    try:
        data = _post_json(
            f"{args.agent_url.rstrip('/')}/auth/cli/login",
            {"email": email, "password": password},
        )
    except RuntimeError as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1) from exc

    output_path = Path(args.output)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print("Login successful.")
    print(f"Session file: {output_path.resolve()}")
    print(f"session_id: {data['session_id']}")
    print("Use header: Authorization: Bearer <session_token>")

    auth_headers = {"Authorization": f"Bearer {data['session_token']}"}
    _run_chat_loop(
        agent_url=args.agent_url,
        session_id=data["session_id"],
        auth_headers=auth_headers,
        preferred_type=args.preferred_auth,
        show_next_action=args.show_next_action,
    )


if __name__ == "__main__":
    main()
