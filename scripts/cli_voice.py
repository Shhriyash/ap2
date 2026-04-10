from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
from urllib import error, request


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=40) as resp:
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


def _login(agent_url: str, email: str, password: str, output: Path) -> dict:
    data = _post_json(
        f"{agent_url.rstrip('/')}/auth/cli/login",
        {"email": email, "password": password},
    )
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _build_agent_voice_assistant_class():
    from fastrtc_real_local import RealFastRTCVoiceAssistant

    class AgentVoiceAssistant(RealFastRTCVoiceAssistant):
        def __init__(
            self,
            *,
            agent_url: str,
            session_id: str,
            auth_headers: dict[str, str],
            preferred_auth: str,
        ) -> None:
            super().__init__()
            self.agent_url = agent_url.rstrip("/")
            self.session_id = session_id
            self.auth_headers = auth_headers
            self.preferred_auth = preferred_auth

        def _send_agent_message(self, message: str) -> dict:
            return _post_json(
                f"{self.agent_url}/agent/message",
                {"session_id": self.session_id, "message": message, "channel": "voice"},
                headers=self.auth_headers,
            )

        def _confirm_execution(self, confirmed: bool) -> dict:
            return _post_json(
                f"{self.agent_url}/agent/confirm",
                {"session_id": self.session_id, "confirmed": confirmed},
                headers=self.auth_headers,
            )

        def _speak_inline(self, text: str) -> None:
            text = text.strip()
            if not text:
                return
            print(f"agent> {text}")
            try:
                speech_file = self.text_to_speech(text)
                if speech_file and speech_file.exists():
                    self.play_audio(speech_file)
            except Exception as exc:  # pragma: no cover - best effort for audio rendering
                print(f"Voice playback warning: {exc}")

        def _run_auth_flow(self, preferred_type: str) -> bool:
            try:
                challenge = _post_json(
                    f"{self.agent_url}/auth/challenge/start",
                    {"session_id": self.session_id, "preferred_type": preferred_type},
                    headers=self.auth_headers,
                )
            except RuntimeError as exc:
                print(f"Could not start auth challenge: {exc}")
                return False

            challenge_type = challenge.get("challenge_type", preferred_type)
            challenge_id = challenge.get("challenge_id", "")
            if not challenge_id:
                print("Auth challenge response did not include challenge_id.")
                return False

            while True:
                prompt_label = "PIN" if challenge_type == "pin" else challenge_type.upper()
                entered_value = getpass.getpass(f"Enter {prompt_label}: ")
                try:
                    result = _post_json(
                        f"{self.agent_url}/auth/challenge/verify",
                        {"challenge_id": challenge_id, "value": entered_value},
                        headers=self.auth_headers,
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

        async def get_llm_response(self, text):
            try:
                response = self._send_agent_message(text)
            except RuntimeError as exc:
                return f"I couldn't reach the agent service: {exc}"

            while True:
                current_text = str(response.get("response", "")).strip()
                next_action = str(response.get("next_action", "")).strip()

                if next_action == "auth_challenge":
                    if current_text:
                        self._speak_inline(current_text)
                    self._speak_inline("Please enter your PIN to verify the transaction.")
                    verified = self._run_auth_flow(self.preferred_auth)
                    if not verified:
                        return "Authentication was not completed. No transaction was executed."
                    try:
                        response = self._send_agent_message("continue")
                    except RuntimeError as exc:
                        return f"Verification succeeded, but I could not continue: {exc}"
                    continue

                if next_action == "ready_to_execute":
                    if current_text:
                        self._speak_inline(current_text)
                    answer = input("Approve transfer? [y/N]: ").strip().lower()
                    try:
                        response = self._confirm_execution(answer in {"y", "yes"})
                    except RuntimeError as exc:
                        return f"I could not submit confirmation: {exc}"
                    continue

                return current_text or "I did not get a response from the agent."

    return AgentVoiceAssistant


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "CLI voice mode for Agent2Pay. "
            "Enforces typed login first, then voice interaction (STT -> agent -> TTS)."
        )
    )
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
        "--env-file",
        default=str(ROOT_DIR / ".env.agent"),
        help="Environment file to load before startup",
    )
    parser.add_argument(
        "--output",
        default=".agent_session.json",
        help="Path to write session token and session id",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Password: ")
    output_path = Path(args.output)

    try:
        login_data = _login(args.agent_url, email=email, password=password, output=output_path)
    except RuntimeError as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1) from exc

    print("Login successful.")
    print(f"Session file: {output_path.resolve()}")
    print(f"session_id: {login_data['session_id']}")
    print("Voice session is now enabled.")

    auth_headers = {"Authorization": f"Bearer {login_data['session_token']}"}
    try:
        assistant_class = _build_agent_voice_assistant_class()
    except ModuleNotFoundError as exc:
        print(f"Missing dependency for voice mode: {exc}.")
        print("Install/update agent dependencies with: .\\.venv-agent\\Scripts\\pip.exe install -r .\\agent_service\\requirements.txt")
        raise SystemExit(1) from exc

    assistant = assistant_class(
        agent_url=args.agent_url,
        session_id=login_data["session_id"],
        auth_headers=auth_headers,
        preferred_auth=args.preferred_auth,
    )

    try:
        assistant.run_console_mode_with_fastrtc_vad()
    finally:
        try:
            assistant.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
