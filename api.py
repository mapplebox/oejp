from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from typing import Any

from zoneinfo import ZoneInfo

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_API_URL

_LOGGER = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


class OEJPAuthError(Exception):
    pass


class OEJPApiError(Exception):
    pass


def _parse_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _jwt_exp(token: str) -> datetime | None:
    try:
        import base64
        import json

        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
        exp = data.get("exp")
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(exp, tz=timezone.utc)
        return None
    except Exception:
        return None


@dataclass
class HHReading:
    start_at: datetime
    end_at: datetime
    version: str | None   # FIX: kann "DAILY" sein
    value: Decimal


AUTH_MUTATION = """
mutation obtainKrakenToken($input: ObtainJSONWebTokenInput!) {
  obtainKrakenToken(input: $input) {
    token
    refreshToken
    refreshExpiresIn
  }
}
"""

GET_ACCOUNT_BODY = """
query accountViewer {
  viewer {
    accounts {
      number
    }
  }
}
"""

GET_HH_BODY = """
query halfHourlyReadings($accountNumber: String!, $fromDatetime: DateTime, $toDatetime: DateTime) {
  account(accountNumber: $accountNumber) {
    properties {
      electricitySupplyPoints {
        halfHourlyReadings(fromDatetime: $fromDatetime, toDatetime: $toDatetime) {
          startAt
          endAt
          version
          value
        }
      }
    }
  }
}
"""


class OEJPApi:
    def __init__(self, hass, email: str, password: str, api_url: str | None = None):
        self._hass = hass
        self._email = email
        self._password = password
        self._api_url = api_url or DEFAULT_API_URL

        self._access_token: str | None = None
        self._access_exp: datetime | None = None
        self._account_number: str | None = None

    async def _post(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        auth: str | None = None,
        tag: str = "graphql",
    ) -> dict[str, Any]:
        session = async_get_clientsession(self._hass)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if auth:
            headers["authorization"] = auth

        payload = {"query": query, "variables": variables or {}}

        _LOGGER.debug("OEJP request %s url=%s", tag, self._api_url)

        async with session.post(self._api_url, json=payload, headers=headers) as resp:
            status = resp.status
            text = await resp.text()

        try:
            import json as _json

            body = _json.loads(text)
        except Exception:
            _LOGGER.error("OEJP %s invalid_json http=%s body=%s", tag, status, text[:1200])
            raise OEJPApiError("Invalid JSON")

        if status >= 400:
            if body.get("errors"):
                _LOGGER.error("OEJP %s http=%s graphql_errors=%s", tag, status, body.get("errors"))
                raise OEJPApiError(f"HTTP {status} GraphQL errors: {body.get('errors')}")
            _LOGGER.error("OEJP %s http=%s body=%s", tag, status, text[:1200])
            raise OEJPApiError(f"HTTP {status}")

        if body.get("errors"):
            msg = str(body.get("errors"))
            _LOGGER.error("OEJP %s graphql_errors=%s", tag, body.get("errors"))
            if "Unauthorized" in msg or "UNAUTHENTICATED" in msg:
                raise OEJPAuthError(msg)
            raise OEJPApiError(msg)

        data = body.get("data")
        if not isinstance(data, dict):
            _LOGGER.error("OEJP %s missing_data body=%s", tag, str(body)[:1200])
            raise OEJPApiError("Missing data")
        return data

    async def _login(self) -> None:
        data = await self._post(
            AUTH_MUTATION,
            variables={"input": {"email": self._email, "password": self._password}},
            tag="login",
        )
        obj = data.get("obtainKrakenToken")
        if not obj or not obj.get("token"):
            raise OEJPAuthError("Login failed")

        token = obj["token"]
        self._access_token = token
        self._access_exp = _jwt_exp(token)

        _LOGGER.debug("OEJP login ok token_exp=%s", self._access_exp)

    async def _ensure_auth(self) -> None:
        if not self._access_token:
            await self._login()

        if self._access_exp:
            now = datetime.now(timezone.utc)
            if now + timedelta(minutes=2) >= self._access_exp:
                _LOGGER.debug("OEJP token near expiry, re-login")
                await self._login()

        if not self._account_number:
            await self._load_account_number()

    async def _load_account_number(self) -> None:
        assert self._access_token
        data = await self._post(
            GET_ACCOUNT_BODY,
            auth=f"JWT {self._access_token}",
            tag="accounts",
        )
        accounts = (data.get("viewer") or {}).get("accounts") or []
        if not accounts:
            raise OEJPAuthError("No accounts found")
        self._account_number = accounts[0].get("number")
        if not self._account_number:
            raise OEJPAuthError("Account number missing")
        _LOGGER.debug("OEJP account selected number=%s", self._account_number)

    @staticmethod
    def _midnight_jst(d: date) -> datetime:
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=JST)

    async def async_test_auth(self) -> None:
        await self._ensure_auth()
        now = datetime.now(tz=JST)
        start = now - timedelta(hours=1)
        _ = await self.async_get_hh_readings(start, now)

    async def async_get_hh_readings(self, start_at: datetime, end_at: datetime) -> list[HHReading]:
        await self._ensure_auth()
        assert self._access_token
        assert self._account_number

        variables: dict[str, Any] = {
            "accountNumber": self._account_number,
            "fromDatetime": start_at.astimezone(timezone.utc).isoformat(),
            "toDatetime": end_at.astimezone(timezone.utc).isoformat(),
        }

        data = await self._post(
            GET_HH_BODY,
            variables=variables,
            auth=f"JWT {self._access_token}",
            tag="hh",
        )

        try:
            props = data["account"]["properties"]
            if not props:
                raise OEJPApiError("No properties returned")
            esp = props[0]["electricitySupplyPoints"]
            if not esp:
                raise OEJPApiError("No electricitySupplyPoints returned")
            raw = esp[0]["halfHourlyReadings"] or []
        except KeyError as e:
            _LOGGER.error("OEJP hh response shape data=%s", str(data)[:1200])
            raise OEJPApiError(f"Unexpected response shape missing {e}") from e

        readings: list[HHReading] = []
        for r in raw:
            ver = r.get("version")
            ver_s = str(ver) if ver is not None else None  # FIX: no int()
            readings.append(
                HHReading(
                    start_at=_parse_dt(r["startAt"]),
                    end_at=_parse_dt(r["endAt"]),
                    version=ver_s,
                    value=Decimal(str(r["value"])),
                )
            )

        readings.sort(key=lambda x: x.start_at)
        return readings

    async def async_get_dashboard(self) -> dict[str, Any]:
        now_jst = datetime.now(tz=JST)
        today_mid = self._midnight_jst(now_jst.date())
        yday_mid = today_mid - timedelta(days=1)

        readings = await self.async_get_hh_readings(yday_mid, now_jst)

        today_kwh = Decimal("0")
        yday_kwh = Decimal("0")
        last_kwh: Decimal | None = None
        last_end: datetime | None = None

        for r in readings:
            st_jst = r.start_at.astimezone(JST)
            if st_jst >= today_mid:
                today_kwh += r.value
            else:
                yday_kwh += r.value

            last_kwh = r.value
            last_end = r.end_at.astimezone(JST)

        return {
            "account_number": self._account_number or "",
            "today_kwh": float(today_kwh),
            "yesterday_kwh": float(yday_kwh),
            "last_half_hour_kwh": float(last_kwh) if last_kwh is not None else None,
            "last_interval_end_jst": last_end.isoformat() if last_end else None,
        }
