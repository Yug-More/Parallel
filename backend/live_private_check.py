"""Explicit operator-only live check for one already-connected test repository.

Does not register an App, authorize new repositories, obtain GitHub tokens, or
reuse CLI credentials. Never run against an original project as a test fixture.
"""

import argparse
import getpass
import http.cookiejar
import json
import re
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        choices=["http://127.0.0.1:8000", "http://localhost:8000"],
    )
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--connection-id", required=True)
    parser.add_argument("--test-repository", required=True)
    parser.add_argument("--allow-live-selected-test-repository", action="store_true", required=True)
    args = parser.parse_args()
    if not all(
        re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value)
        for value in [args.workspace_id, args.connection_id]
    ):
        parser.error("Invalid immutable resource identifier")
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar), NoRedirect()
    )

    def call(path, body=None):
        request = urllib.request.Request(
            args.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": args.base_url},
        )
        with client.open(request, timeout=30) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("response_limit")
            return json.loads(raw)

    logged_in = False
    try:
        call(
            "/auth/login",
            {
                "email": input("Parallel owner email: ").strip(),
                "password": getpass.getpass("Parallel password (never stored): "),
            },
        )
        logged_in = True
        base = f"/workspaces/{args.workspace_id}"
        connection = next(
            row for row in call(base + "/connections")["items"] if row["id"] == args.connection_id
        )
        if (
            connection["repository"] != args.test_repository
            or connection["auth_mode"] != "github_app_user"
            or not connection["active"]
        ):
            raise ValueError("selected_test_connection_required")
        selected = []
        for row in call(base + "/knowledge?kind=external&limit=100")["items"]:
            source = call(base + "/sources/external/" + row["id"])
            if source["connection_id"] == args.connection_id:
                selected.append(row["id"])
        if not selected:
            raise ValueError("Sync the selected test connection first")
        verified = call(
            base + f"/connections/{args.connection_id}/verify", {"version": connection["version"]}
        )
        if not verified["active"]:
            raise ValueError("permission_check_failed")
        print("Initial selected-repository access verified. No source text was printed.")
        if (
            input("Remove ONLY this test repository from the App installation, then type REMOVED: ")
            != "REMOVED"
        ):
            raise ValueError("revocation_observation_required")
        try:
            call(
                base + f"/connections/{args.connection_id}/verify",
                {"version": connection["version"]},
            )
            raise ValueError("revoked_access_was_accepted")
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
        denied = 0
        for source_id in selected:
            try:
                call(base + "/sources/external/" + source_id)
                raise ValueError("source_remained_visible")
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                denied += 1
        print(
            json.dumps(
                {
                    "live_operator_check": "passed",
                    "selected_sources_denied_after_revalidation": denied,
                    "model_quality": "not_tested",
                    "external_writes": "none",
                }
            )
        )
    except Exception:
        raise SystemExit(
            "Live verification failed or was cancelled; no credentials or source bodies logged."
        ) from None
    finally:
        if logged_in:
            try:
                call("/auth/logout", {})
            except Exception:
                pass


if __name__ == "__main__":
    main()
