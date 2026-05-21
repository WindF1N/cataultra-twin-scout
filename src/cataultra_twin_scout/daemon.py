from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .analysis import analyze_session, write_twins_report
from .api import CatapultReadApi, is_completed
from .models import FairData, ScoutState, TokenCandidate, TwinScoutConfig
from .storage import TwinScoutStorage


console = Console()


@dataclass(frozen=True, slots=True)
class CollectStepResult:
    session_name: str
    collected_count: int
    added_count: int
    scanned_count: int
    error_count: int
    last_token_id: str | None
    last_ticker: str | None
    archived: bool
    archive_path: str | None
    twin_pairs_found: int
    pending_count: int = 0


@dataclass(frozen=True, slots=True)
class FairFetchResult:
    candidate: TokenCandidate | None
    token_id: str
    fair_data: FairData | None
    error: str | None = None


class TwinScoutDaemon:
    def __init__(self, api: CatapultReadApi, storage: TwinScoutStorage, config: TwinScoutConfig):
        self.api = api
        self.storage = storage
        self.config = config

    def run_once(self) -> CollectStepResult:
        console.log("[bold blue]Начало нового цикла сбора[/]")
        state = self.storage.load_state()
        processed = set(state.processed_token_ids)
        pending_fair = set(state.pending_fair_ids)            # ждут раскрытия fair‑данных
        pending_completion = set(state.pending_completion_ids) # ждут завершения токена

        session_dir = self.storage.session_dir(state.current_session_number)
        added = 0
        errors = 0
        scanned = 0

        tokens = self.api.list_tokens(self.config.speed_modes, limit=self.config.market_limit, rank=self.config.rank)
        # Новые кандидаты: ещё не обработаны и не в очередях
        candidates = [
            c for c in tokens
            if c.token_id and c.token_id not in processed
            and c.token_id not in pending_fair
            and c.token_id not in pending_completion
        ]
        console.log(f"[bold]Всего токенов в выдаче:[/] {len(tokens)}, новых кандидатов: {len(candidates)}")

        # Собираем все задачи в один список
        new_tasks = [(c.token_id, True, c) for c in candidates]
        pending_fair_tasks = [(pid, False, None) for pid in pending_fair]
        pending_comp_tasks = [(pid, False, None) for pid in pending_completion]
        all_tasks = new_tasks + pending_fair_tasks + pending_comp_tasks
        random.shuffle(all_tasks)

        task_iter = iter(all_tasks)
        new_pending_fair = set()
        new_pending_completion = set()

        with ThreadPoolExecutor(max_workers=self.config.worker_count, thread_name_prefix="twin-scout") as executor:
            active = {}

            def submit_next() -> bool:
                nonlocal scanned
                try:
                    token_id, is_new, candidate = next(task_iter)
                except StopIteration:
                    return False
                future = executor.submit(self._fetch_with_delay, token_id)
                active[future] = (token_id, is_new, candidate)
                scanned += 1
                return True

            while len(active) < self.config.worker_count and submit_next():
                pass

            while active:
                future = next(as_completed(active))
                token_id, is_new, candidate = active.pop(future)
                result = future.result()

                if result.error:
                    errors += 1
                    console.log(f"[red]Ошибка для {token_id}:[/] {result.error}")
                    new_pending_completion.add(token_id)  # попробуем позже
                    continue

                fair_data = result.fair_data
                completed = is_completed(candidate) if candidate is not None else True

                if not completed:
                    console.log(f"[dim]Токен {token_id} ещё не завершён – отложен[/]")
                    new_pending_completion.add(token_id)
                    continue

                if fair_data is not None and fair_data.is_revealed:
                    if token_id not in processed:
                        if candidate is None:
                            candidate = TokenCandidate(
                                token_id=token_id, ticker="", icon_url="", mode="",
                                is_completed=True, start_date="", end_date=""
                            )
                        self.storage.write_token(session_dir, candidate, fair_data)
                        processed.add(token_id)
                        state.last_token_id = token_id
                        state.last_ticker = candidate.ticker
                        added += 1
                        console.log(f"[green]Сохранили токен {token_id}[/] ({candidate.ticker or 'N/A'})")
                    # убираем из всех очередей
                    new_pending_fair.discard(token_id)
                    new_pending_completion.discard(token_id)
                else:
                    console.log(f"[dim]Токен {token_id} завершён, но fair_data не раскрыт – отложен[/]")
                    new_pending_fair.add(token_id)

                if self.storage.token_count(session_dir) >= self.config.batch_size:
                    for pending in active:
                        pending.cancel()
                    active.clear()
                    console.log("[bold yellow]Достигнут лимит пачки, прерываем цикл[/]")
                    break
                submit_next()

        state.processed_token_ids = sorted(processed)
        state.pending_fair_ids = sorted(new_pending_fair)
        state.pending_completion_ids = sorted(new_pending_completion)
        collected_count = self.storage.token_count(session_dir)

        archived = False
        archive_path: Path | None = None
        pairs_found = 0
        if collected_count >= self.config.batch_size:
            console.log("[bold magenta]Запускаем анализ сессии[/]")
            pairs = analyze_session(
                self.storage,
                session_dir,
                twin_threshold=self.config.twin_correlation_threshold,
                perfect_threshold=self.config.perfect_correlation_threshold,
                max_lag=self.config.max_correlation_lag,
            )
            write_twins_report(session_dir, collected_count, pairs, self.config.perfect_correlation_threshold)
            archive_path = self.storage.archive_and_remove(session_dir)
            archived = True
            pairs_found = len(pairs)
            state.total_twin_pairs_found += pairs_found
            state.archived_sessions += 1
            state.current_session_number += 1
            self.storage.session_dir(state.current_session_number)
            console.log(
                f"[bold green]Сессия заархивирована:[/] {archive_path}, найдено пар близнецов: {pairs_found}"
            )

        self.storage.save_state(state)
        console.log(
            f"[bold blue]Цикл завершён: добавлено {added}, ошибок {errors}, "
            f"в очереди fair={len(new_pending_fair)}, завершения={len(new_pending_completion)}[/]"
        )

        return CollectStepResult(
            session_name=f"session_1k_{state.current_session_number:03d}",
            collected_count=0 if archived else collected_count,
            added_count=added,
            scanned_count=scanned,
            error_count=errors,
            last_token_id=state.last_token_id,
            last_ticker=state.last_ticker,
            archived=archived,
            archive_path=str(archive_path) if archive_path else None,
            twin_pairs_found=pairs_found,
            pending_count=len(new_pending_fair) + len(new_pending_completion),
        )

    def _fetch_with_delay(self, token_id: str) -> FairFetchResult:
        delay = random.uniform(self.config.request_delay_min_sec, self.config.request_delay_max_sec)
        if delay > 0:
            time.sleep(delay)
        try:
            fair_data = self.api.fetch_token_fair_data(token_id)
        except Exception as exc:
            return FairFetchResult(candidate=None, token_id=token_id, fair_data=None, error=str(exc))
        return FairFetchResult(candidate=None, token_id=token_id, fair_data=fair_data)

    def analyze_current_session(self) -> Path:
        state = self.storage.load_state()
        session_dir = self.storage.session_dir(state.current_session_number)
        pairs = analyze_session(
            self.storage,
            session_dir,
            twin_threshold=self.config.twin_correlation_threshold,
            perfect_threshold=self.config.perfect_correlation_threshold,
            max_lag=self.config.max_correlation_lag,
        )
        report = write_twins_report(
            session_dir,
            self.storage.token_count(session_dir),
            pairs,
            self.config.perfect_correlation_threshold,
        )
        state.total_twin_pairs_found += len(pairs)
        self.storage.save_state(state)
        return report

    def run_forever(self) -> None:
        with Live(self._hud(self.storage.load_state(), None), refresh_per_second=2, console=console) as live:
            while True:
                try:
                    result = self.run_once()
                except Exception as exc:
                    console.log(f"[bold red]Критическая ошибка цикла:[/] {exc}")
                    time.sleep(self.config.scan_interval_sec)
                    continue
                live.update(self._hud(self.storage.load_state(), result))
                time.sleep(self.config.scan_interval_sec)

    def _hud(self, state: ScoutState, result: CollectStepResult | None) -> Panel:
        current_dir = self.storage.session_dir(state.current_session_number)
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan")
        table.add_column(style="white")
        table.add_row("Текущая сессия", current_dir.name)
        table.add_row("Собрано токенов", f"{self.storage.token_count(current_dir)} / {self.config.batch_size}")
        table.add_row("Последний токен", f"[{state.last_ticker or 'N/A'}] ID: {state.last_token_id or 'N/A'}")
        table.add_row("Архивированных сессий", str(state.archived_sessions))
        table.add_row("Всего пар близнецов", str(state.total_twin_pairs_found))
        if result is not None:
            table.add_row("Добавлено за цикл", str(result.added_count))
            table.add_row("Кандидатов в работе", str(result.scanned_count))
            table.add_row("Ошибок за цикл", str(result.error_count))
            table.add_row("В очереди (всего)", str(result.pending_count))
            if result.archived:
                table.add_row("Архив", result.archive_path or "N/A")
        return Panel(table, title="[bold cyan]🧬 TWIN SCOUT DAEMON ACTIVE[/]", border_style="bold magenta")