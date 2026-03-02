"""Buttondown API client for email newsletter delivery."""

from __future__ import annotations

import os

import httpx

BASE_URL = "https://api.buttondown.com/v1"


class ButtondownError(Exception):
    """Raised when a Buttondown API call fails."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"Buttondown API error {status_code}: {detail}")


class ButtondownClient:
    """Minimal client for the Buttondown email API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("BUTTONDOWN_API_KEY", "")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.api_key}"}

    def _raise_for_error(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise ButtondownError(resp.status_code, resp.text)

    async def create_draft(self, subject: str, body: str) -> dict:
        """Create a draft email in Buttondown."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BASE_URL}/emails",
                headers=self._headers(),
                json={"subject": subject, "body": body, "status": "draft"},
            )
        self._raise_for_error(resp)
        return resp.json()

    async def send_email(self, email_id: str) -> dict:
        """Promote a draft to sending."""
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{BASE_URL}/emails/{email_id}",
                headers=self._headers(),
                json={"status": "about_to_send"},
            )
        self._raise_for_error(resp)
        return resp.json()

    async def get_email(self, email_id: str) -> dict:
        """Fetch current state of an email."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/emails/{email_id}",
                headers=self._headers(),
            )
        self._raise_for_error(resp)
        return resp.json()
