from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from .api import CatapultReadApi
from .config import load_config, require_cookie
from .daemon import TwinScoutDaemon
from .storage import TwinScoutStorage
from .transport import GraphQLClient

try:
    import questionary
    from questionary import Style
except ImportError:  # pragma: no cover
    questionary = None
    Style = None


console = Console()

LOGO = r"""
 ██████╗ █████╗ ████████╗ █████╗ ██╗   ██╗██╗  ████████╗██████╗  █████╗ ██╗
██╔════╝██╔══██╗╚══██╔══╝██╔══██╗██║   ██║██║  ╚══██╔══╝██╔══██╗██╔══██╗██║
██║     ███████║   ██║   ███████║██║   ██║██║     ██║   ██████╔╝███████║██║
██║     ██╔══██║   ██║   ██╔══██║██║   ██║██║     ██║   ██╔══██╗██╔══██║╚═╝
╚██████╗██║  ██║   ██║   ██║  ██║╚██████╔╝███████╗██║   ██║  ██║██║  ██║██╗
 ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝
                         CATAULTR[AI] TWIN SCOUT
"""

MENU_STYLE = Style(
    [
        ("qmark", "fg:#7dd3fc bold"),
        ("question", "fg:#ffffff bold"),
        ("answer", "fg:#facc15 bold"),
        ("pointer", "fg:#67e8f9 bold"),
        ("highlighted", "fg:#facc15 bold"),
        ("selected", "fg:#34d399 bold"),
        ("instruction", "fg:#94a3b8"),
        ("text", "fg:#e5e7eb"),
    ]
) if Style is not None else None


def main() -> int:
    while True:
        _banner()
        choice = _select(
            "Twin Scout меню",
            [
                ("🧬 Запустить Twin Scout Daemon (Поиск близнецов 24/7)", "daemon"),
                ("🔁 Один цикл сбора", "once"),
                ("📊 Проанализировать текущую сессию", "analyze"),
                ("⚙️ Показать конфиг", "config"),
                ("❌ Выход", "exit"),
            ],
        )
        try:
            if choice == "exit":
                return 0
            daemon = _build_daemon()
            if choice == "daemon":
                daemon.run_forever()
            elif choice == "once":
                result = daemon.run_once()
                console.print(Panel(Pretty(result), title="🔁 Collect Step", border_style="bold cyan"))
                _pause()
            elif choice == "analyze":
                report = daemon.analyze_current_session()
                console.print(Panel(f"Отчет создан: [bold cyan]{report}[/]", title="📊 Twin Analysis", border_style="bold green"))
                _pause()
            elif choice == "config":
                console.print(Panel(Pretty(load_config().to_dict()), title="⚙️ Config", border_style="bold magenta"))
                _pause()
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Остановлено оператором.[/]")
            _pause()
        except Exception as exc:
            console.print(Panel(str(exc), title="Ошибка", border_style="bold red"))
            _pause()


def _build_daemon() -> TwinScoutDaemon:
    config = load_config()
    cookie = require_cookie()
    api = CatapultReadApi(
        GraphQLClient(
            cookie,
            retry_max_attempts=config.retry_max_attempts,
            retry_backoff_base_sec=config.retry_backoff_base_sec,
            retry_backoff_max_sec=config.retry_backoff_max_sec,
        )
    )
    storage = TwinScoutStorage(config.root_dir)
    return TwinScoutDaemon(api, storage, config)


def _banner() -> None:
    print("\033[2J\033[H", end="")
    console.print(LOGO, style="bold cyan")
    console.print("by bunker", style="bold yellow")
    console.print(Panel(
        "Read-only daemon: TurboTokenFairData -> pure ticks -> correlation report -> archive.",
        title="🧬 Twin Graph Matcher",
        border_style="bold magenta",
    ))


def _select(message: str, choices: list[tuple[str, str]]) -> str:
    labels = [label for label, _ in choices]
    mapping = {label: value for label, value in choices}
    if questionary is not None and sys.stdin.isatty():
        picked = questionary.select(message, choices=labels, style=MENU_STYLE).ask()
        return mapping[picked] if picked else "exit"
    for index, (label, _) in enumerate(choices, start=1):
        print(f"{index}. {label}")
    raw = input("> ").strip()
    if raw.isdigit() and 1 <= int(raw) <= len(choices):
        return choices[int(raw) - 1][1]
    return "exit"


def _pause() -> None:
    if questionary is not None and sys.stdin.isatty():
        questionary.press_any_key_to_continue("Нажмите Enter для возврата в меню...").ask()
    else:
        input("Нажмите Enter для возврата в меню...")
