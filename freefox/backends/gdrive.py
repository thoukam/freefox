"""Google Drive storage backend with persisted resumable uploads."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession, Request
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from freefox.backends import ProgressCallback, SessionCallback, StorageBackend

logger = logging.getLogger(__name__)

# drive.file is enough for files created by this app.
_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_TOKEN_PATH = Path(
    os.environ.get("FREEFOX_TOKEN_PATH")
    or os.environ.get("ROSBAG_COLLECTOR_TOKEN_PATH", "/var/lib/freefox/token.json")
)


def _build_credentials(credentials_file: Path):
    creds = None

    with open(credentials_file) as fh:
        import json

        raw = json.load(fh)

    if raw.get("type") == "service_account":
        creds = service_account.Credentials.from_service_account_file(
            str(credentials_file), scopes=_SCOPES
        )
        logger.info("Authenticated via service account: %s", raw.get("client_email"))
    else:
        if _TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_file), _SCOPES
                )
                creds = flow.run_local_server(port=0)

            _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            _TOKEN_PATH.write_text(creds.to_json())
            logger.info("OAuth2 token saved to %s", _TOKEN_PATH)

    return creds


def _build_service(credentials_file: Path):
    creds = _build_credentials(credentials_file)
    return build("drive", "v3", credentials=creds, cache_discovery=False), creds


def _uploaded_from_range(value: str | None) -> int:
    """Parse a Drive resumable Range header, e.g. 'bytes=0-1048575'."""
    if not value:
        return 0
    try:
        _, end = value.split("-", maxsplit=1)
        return int(end) + 1
    except (TypeError, ValueError):
        return 0


class GoogleDriveBackend(StorageBackend):
    """Upload bags to a Google Drive folder, organised as remote_path hierarchy."""

    def __init__(
        self,
        credentials_file: Path,
        target_folder_id: str,
    ) -> None:
        self._credentials_file = credentials_file
        self._root_folder_id = target_folder_id
        self._service, creds = _build_service(credentials_file)
        self._http = AuthorizedSession(creds)
        self._folder_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Folder helpers
    # ------------------------------------------------------------------

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        cache_key = f"{parent_id}/{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        q = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        resp = (
            self._service.files()
            .list(
                q=q,
                fields="files(id)",
                pageSize=1,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        files = resp.get("files", [])
        if files:
            folder_id = files[0]["id"]
        else:
            meta = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = (
                self._service.files()
                .create(body=meta, fields="id", supportsAllDrives=True)
                .execute()
            )
            folder_id = folder["id"]
            logger.debug("Created Drive folder '%s' (%s)", name, folder_id)

        self._folder_cache[cache_key] = folder_id
        return folder_id

    def _resolve_folder_path(self, remote_path: str) -> tuple[str, str]:
        parts = Path(remote_path).parts
        parent_id = self._root_folder_id or "root"
        for part in parts[:-1]:
            parent_id = self._get_or_create_folder(part, parent_id)
        return parent_id, parts[-1]

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

    def exists(self, remote_path: str) -> bool:
        parent_id, filename = self._resolve_folder_path(remote_path)
        q = f"name='{filename}' and '{parent_id}' in parents and trashed=false"
        resp = (
            self._service.files()
            .list(
                q=q,
                fields="files(id)",
                pageSize=1,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        return bool(resp.get("files"))

    def upload(
        self,
        local_path: Path,
        remote_path: str,
        chunk_size: int = 2 * 1024 * 1024,
        progress_callback: ProgressCallback | None = None,
        session_uri: str = "",
        session_callback: SessionCallback | None = None,
    ) -> str:
        parent_id, filename = self._resolve_folder_path(remote_path)
        file_size = local_path.stat().st_size

        logger.info(
            "Uploading %s -> Drive:%s  (%.1f MiB)",
            local_path.name,
            remote_path,
            file_size / 1024 / 1024,
        )

        if session_uri:
            logger.info("Resuming Drive upload session for %s", filename)
            try:
                uploaded = self._query_resumable_session(session_uri, file_size)
            except RuntimeError as exc:
                if "session expired" in str(exc) and session_callback:
                    session_callback("")
                raise
        else:
            meta = {"name": filename, "parents": [parent_id]}
            session_uri = self._start_resumable_session(meta, file_size)
            if session_callback:
                session_callback(session_uri)
            uploaded = 0

        if uploaded and progress_callback:
            progress_callback((uploaded / file_size) * 100, uploaded)

        result: dict[str, str] | None = None
        with local_path.open("rb") as fh:
            while uploaded < file_size:
                start = uploaded
                end = min(start + chunk_size, file_size) - 1
                length = end - start + 1
                fh.seek(start)
                chunk = fh.read(length)

                response = self._http.put(
                    session_uri,
                    data=chunk,
                    headers={
                        "Content-Length": str(length),
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                    },
                )

                if response.status_code == 308:
                    uploaded = _uploaded_from_range(response.headers.get("Range"))
                    if progress_callback:
                        progress_callback((uploaded / file_size) * 100, uploaded)
                    continue

                if response.status_code in {200, 201}:
                    uploaded = file_size
                    if progress_callback:
                        progress_callback(100.0, uploaded)
                    result = response.json()
                    break

                if response.status_code in {404, 410}:
                    if session_callback:
                        session_callback("")
                    raise RuntimeError("Drive resumable upload session expired")

                if response.status_code in {500, 502, 503, 504}:
                    raise RuntimeError(
                        f"transient Drive upload error: HTTP {response.status_code}"
                    )

                raise RuntimeError(
                    f"Drive upload failed: HTTP {response.status_code}: {response.text}"
                )

        if result is None:
            result = self._query_completed_session(session_uri, file_size)

        file_id = result["id"]
        link = result.get("webViewLink", f"https://drive.google.com/file/d/{file_id}")
        logger.info("Upload complete: %s -> %s", filename, link)
        return link

    def _start_resumable_session(self, meta: dict[str, object], file_size: int) -> str:
        response = self._http.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            params={
                "uploadType": "resumable",
                "fields": "id,webViewLink",
                "supportsAllDrives": "true",
            },
            json=meta,
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
                "X-Upload-Content-Length": str(file_size),
            },
        )
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"Could not start Drive resumable upload: "
                f"HTTP {response.status_code}: {response.text}"
            )
        session_uri = response.headers.get("Location", "")
        if not session_uri:
            raise RuntimeError("Drive did not return a resumable upload session URI")
        return session_uri

    def _query_resumable_session(self, session_uri: str, file_size: int) -> int:
        response = self._http.put(
            session_uri,
            headers={
                "Content-Length": "0",
                "Content-Range": f"bytes */{file_size}",
            },
        )
        if response.status_code == 308:
            return _uploaded_from_range(response.headers.get("Range"))
        if response.status_code in {200, 201}:
            return file_size
        if response.status_code in {404, 410}:
            raise RuntimeError("Drive resumable upload session expired")
        raise RuntimeError(
            f"Could not query Drive upload session: "
            f"HTTP {response.status_code}: {response.text}"
        )

    def _query_completed_session(
        self, session_uri: str, file_size: int
    ) -> dict[str, str]:
        response = self._http.put(
            session_uri,
            headers={
                "Content-Length": "0",
                "Content-Range": f"bytes */{file_size}",
            },
        )
        if response.status_code in {200, 201}:
            return response.json()
        raise RuntimeError(
            f"Drive upload completed but final metadata was unavailable: "
            f"HTTP {response.status_code}: {response.text}"
        )
