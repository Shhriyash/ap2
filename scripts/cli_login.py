from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from urllib import error, request


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI login for agent session creation.")
    parser.add_argument("--agent-url", default="http://localhost:8000", help="Agent base URL")
    parser.add_argument("--email", help="Supabase email")
    parser.add_argument("--password", help="Supabase password")
    parser.add_argument(
        "--output",
        default=".agent_session.json",
        help="Path to write session token and session id",
    )
    args = parser.parse_args()

    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Password: ")

    payload = {"email": email, "password": password}
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{args.agent_url.rstrip('/')}/auth/cli/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        print(f"Login failed ({exc.code}): {text}")
        raise SystemExit(1) from exc

    output_path = Path(args.output)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print("Login successful.")
    print(f"Session file: {output_path.resolve()}")
    print(f"session_id: {data['session_id']}")
    print("Use header: Authorization: Bearer <session_token>")


if __name__ == "__main__":
    main()
