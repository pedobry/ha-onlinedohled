"""HTTP client for the Online Dohled ASP.NET portal."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp

from .portal import (
    ParsedCsv,
    PortalError,
    assign_series,
    decode_csv,
    export_form_data,
    login_form_data,
    parse_consumption_csv,
    parse_consumption_form,
    parse_login_form,
)

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class AuthFailed(PortalError):
    """Username or password was rejected, or the session expired."""


class PortalConnectionError(PortalError):
    """The portal could not be reached."""


class ExportError(PortalError):
    """Login worked, but a consumption export did not."""


@dataclass(frozen=True)
class _Response:
    status: int
    url: str
    content_type: str
    content_disposition: str
    body: bytes

    def text(self) -> str:
        content_type = self.content_type.lower()
        if "1250" in content_type:
            return self.body.decode("cp1250", "replace")
        return self.body.decode("utf-8", "replace")


async def async_fetch_series(
    username: str,
    password: str,
    page_url: str,
) -> dict[str, ParsedCsv]:
    """Open a short-lived session and download all three series."""
    timeout = aiohttp.ClientTimeout(total=90, connect=20, sock_read=60)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "cs,en;q=0.8"}
    async with aiohttp.ClientSession(
        headers=headers,
        timeout=timeout,
        cookie_jar=aiohttp.CookieJar(),
        trust_env=True,
    ) as session:
        client = OnlineDohledClient(session, username, password, page_url)
        return await client.async_fetch()


class OnlineDohledClient:
    """Log in and download one CSV per consumption series."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        page_url: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._page_url = page_url
        parts = urlsplit(page_url)
        origin = f"{parts.scheme}://{parts.netloc}"
        self._origin = origin
        self._login_url = f"{origin}/Dispecink.aspx"

    async def async_fetch(self) -> dict[str, ParsedCsv]:
        """Return heat, cold water and hot water exports."""
        await self._login()
        exports: list[tuple[int, ParsedCsv]] = []
        for index in (0, 1, 2):
            form = parse_consumption_form(await self._get_consumption_page())
            result = await self._post_form(self._page_url, export_form_data(form, index))
            parsed = self._parse_export(result, index)
            exports.append((index, parsed))
            _LOGGER.info(
                "Export Chck%s: %s (%s)",
                index,
                parsed.header,
                result.content_disposition,
            )
        return assign_series(exports)

    async def _login(self) -> None:
        page = await self._get(self._login_url)
        if page.status >= 400:
            raise PortalConnectionError(f"Přihlašovací stránka vrátila {page.status}")
        try:
            form = parse_login_form(page.text())
        except PortalError as err:
            raise ExportError("Přihlašovací stránka nemá očekávaný formulář") from err
        result = await self._post_form(
            self._login_url,
            login_form_data(form, self._username, self._password),
        )
        if result.status >= 400:
            raise PortalConnectionError(f"Přihlášení vrátilo {result.status}")
        if "Login1_Password" in result.text() and "Dispecink.aspx" in result.url:
            raise AuthFailed("Přihlášení selhalo")

    async def _get_consumption_page(self) -> str:
        page = await self._get(self._page_url)
        if page.status >= 400:
            raise PortalConnectionError(f"Stránka spotřeby vrátila {page.status}")
        if "Dispecink.aspx" in page.url or "Login1_Password" in page.text():
            raise AuthFailed("Přihlášení selhalo")
        return page.text()

    def _parse_export(self, result: _Response, index: int) -> ParsedCsv:
        disposition = result.content_disposition.lower()
        looks_like_csv = (
            "text/csv" in result.content_type.lower()
            or "attachment" in disposition
            or b"Datum" in result.body[:200]
        )
        if result.status >= 400 or not looks_like_csv:
            raise ExportError(
                f"Export Chck{index} nevrátil CSV. "
                "Zkontrolujte, že adresa vede na stránku spotřeby."
            )
        try:
            return parse_consumption_csv(decode_csv(result.body, result.content_type))
        except PortalError as err:
            raise ExportError(str(err)) from err

    async def _get(self, url: str) -> _Response:
        try:
            async with self._session.get(url, allow_redirects=True) as response:
                return await self._capture(response)
        except TimeoutError as err:
            raise PortalConnectionError("Online Dohled neodpověděl včas") from err
        except aiohttp.ClientError as err:
            raise PortalConnectionError("Nelze se spojit s Online Dohledem") from err

    async def _post_form(self, url: str, data: dict[str, str]) -> _Response:
        headers = {"Referer": url, "Origin": self._origin}
        try:
            async with self._session.post(
                url,
                data=data,
                headers=headers,
                allow_redirects=True,
            ) as response:
                return await self._capture(response)
        except TimeoutError as err:
            raise PortalConnectionError("Online Dohled neodpověděl včas") from err
        except aiohttp.ClientError as err:
            raise PortalConnectionError("Nelze se spojit s Online Dohledem") from err

    async def _capture(self, response: aiohttp.ClientResponse) -> _Response:
        return _Response(
            status=response.status,
            url=str(response.url),
            content_type=response.headers.get("Content-Type", ""),
            content_disposition=response.headers.get("Content-Disposition", ""),
            body=await response.read(),
        )
