from __future__ import annotations

import json
import re
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import FairData, ScoutState, TokenCandidate, TokenMetadata, utc_now_iso


SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True, slots=True)
class StoredToken:
    token_dir: Path
    metadata: TokenMetadata
    ticks: list[float]


class TwinScoutStorage:
    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root_dir / "state.json"

    def load_state(self) -> ScoutState:
        if not self.state_path.exists():
            return ScoutState()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ScoutState()
        return ScoutState.model_validate(payload)

    def save_state(self, state: ScoutState) -> None:
        payload = state.model_copy(update={"updated_at": utc_now_iso()}).to_dict()
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def session_dir(self, session_number: int) -> Path:
        path = self.root_dir / f"session_1k_{session_number:03d}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def token_count(self, session_dir: Path) -> int:
        return sum(1 for path in session_dir.iterdir() if path.is_dir() and path.name.startswith("token_"))

    def archive_count(self) -> int:
        return len(list(self.root_dir.glob("session_1k_*.tar.gz")))

    def write_token(self, session_dir: Path, candidate: TokenCandidate, fair_data: FairData) -> Path:
        token_dir = session_dir / f"token_{candidate.token_id}_{safe_name(candidate.ticker)}"
        token_dir.mkdir(parents=True, exist_ok=True)
        metadata = TokenMetadata(
            token_id=candidate.token_id,
            ticker=candidate.ticker,
            name=candidate.name,
            speed_mode=candidate.speed_mode,
            start_price=candidate.start_price,
            final_price=candidate.final_price or (fair_data.ticks_array[-1] if fair_data.ticks_array else None),
            fair_hash=fair_data.fair_hash,
            fair_salt=fair_data.fair_salt,
            speed_ticks_in_second=fair_data.speed_ticks_in_second,
            created_at=candidate.start_date,
            ended_at=candidate.end_date,
        )
        _write_json(token_dir / "raw_fair_data.json", fair_data.raw)
        _write_json(token_dir / "pure_ticks.json", fair_data.ticks_array)
        _write_json(token_dir / "token_metadata.json", metadata.to_dict())
        return token_dir

    def load_session_tokens(self, session_dir: Path) -> list[StoredToken]:
        tokens: list[StoredToken] = []
        for token_dir in sorted(session_dir.glob("token_*")):
            if not token_dir.is_dir():
                continue
            metadata_path = token_dir / "token_metadata.json"
            ticks_path = token_dir / "pure_ticks.json"
            if not metadata_path.exists() or not ticks_path.exists():
                continue
            metadata = TokenMetadata.model_validate(_read_json(metadata_path))
            ticks = [float(value) for value in _read_json(ticks_path)]
            tokens.append(StoredToken(token_dir=token_dir, metadata=metadata, ticks=ticks))
        return tokens

    def archive_and_remove(self, session_dir: Path) -> Path:
        archive_path = self.root_dir / f"{session_dir.name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(session_dir, arcname=session_dir.name)
        shutil.rmtree(session_dir)
        return archive_path


def safe_name(value: str) -> str:
    cleaned = SAFE_NAME.sub("_", value.strip())[:32].strip("_")
    return cleaned or "UNKNOWN"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

