from __future__ import annotations

import math
from pathlib import Path

from .models import TokenMetadata, TwinPair
from .storage import StoredToken, TwinScoutStorage


def pearson_correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 3:
        return 0.0
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    left_var = sum((a - mean_left) ** 2 for a in left)
    right_var = sum((b - mean_right) ** 2 for b in right)
    denominator = math.sqrt(left_var * right_var)
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def sliding_pearson(left: list[float], right: list[float], max_lag: int = 8) -> tuple[float, int, int]:
    best = -1.0
    best_lag = 0
    best_overlap = 0
    for lag in range(-max_lag, max_lag + 1):
        left_slice, right_slice = _align_by_lag(left, right, lag)
        overlap = min(len(left_slice), len(right_slice))
        if overlap < 5:
            continue
        corr = pearson_correlation(_normalize(left_slice), _normalize(right_slice))
        if corr > best:
            best = corr
            best_lag = lag
            best_overlap = overlap
    return round(max(best, 0.0), 6), best_lag, best_overlap


def analyze_session(
    storage: TwinScoutStorage,
    session_dir: Path,
    twin_threshold: float,
    perfect_threshold: float,
    max_lag: int,
) -> list[TwinPair]:
    tokens = storage.load_session_tokens(session_dir)
    pairs: list[TwinPair] = []
    for left_index, left in enumerate(tokens):
        for right in tokens[left_index + 1:]:
            corr, lag, overlap = sliding_pearson(left.ticks, right.ticks, max_lag=max_lag)
            if corr >= twin_threshold:
                pairs.append(_pair_from_tokens(left, right, corr, lag, overlap, perfect_threshold))
    pairs.sort(key=lambda pair: pair.correlation, reverse=True)
    return pairs


def write_twins_report(session_dir: Path, tokens_count: int, pairs: list[TwinPair], perfect_threshold: float) -> Path:
    perfect = [pair for pair in pairs if pair.correlation >= perfect_threshold]
    ordinary = [pair for pair in pairs if pair.correlation < perfect_threshold]
    lines = [
        "# Twin Scout Report",
        "",
        f"- Проанализировано токенов: **{tokens_count}**",
        f"- Perfect twins: **{len(perfect)}**",
        f"- Twins: **{len(ordinary)}**",
        "",
        "## Пары",
        "",
    ]
    if not pairs:
        lines.append("Близнецы по заданному порогу не обнаружены.")
    for pair in pairs:
        lines.extend([
            f"### {pair.left_ticker} / {pair.right_ticker}",
            "",
            f"- Класс: `{pair.classification}`",
            f"- Корреляция: `{pair.correlation:.6f}`",
            f"- Lag: `{pair.lag}`",
            f"- Overlap: `{pair.overlap}`",
            f"- Left: `{pair.left_token_id}` hash=`{pair.left_fair_hash}` salt=`{pair.left_fair_salt}`",
            f"- Right: `{pair.right_token_id}` hash=`{pair.right_fair_hash}` salt=`{pair.right_fair_salt}`",
            "",
        ])
    lines.extend([
        "## Математический вывод",
        "",
        _conclusion(pairs),
        "",
    ])
    path = session_dir / "twins_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _align_by_lag(left: list[float], right: list[float], lag: int) -> tuple[list[float], list[float]]:
    if lag > 0:
        return left[lag:], right[: len(left) - lag]
    if lag < 0:
        shift = abs(lag)
        return left[: len(right) - shift], right[shift:]
    limit = min(len(left), len(right))
    return left[:limit], right[:limit]


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    first = values[0]
    if first == 0:
        return values
    return [value / first for value in values]


def _pair_from_tokens(
    left: StoredToken,
    right: StoredToken,
    correlation: float,
    lag: int,
    overlap: int,
    perfect_threshold: float,
) -> TwinPair:
    classification = "perfect_twin" if correlation >= perfect_threshold else "twin"
    return TwinPair(
        left_token_id=left.metadata.token_id,
        left_ticker=left.metadata.ticker,
        left_fair_hash=left.metadata.fair_hash,
        left_fair_salt=left.metadata.fair_salt,
        right_token_id=right.metadata.token_id,
        right_ticker=right.metadata.ticker,
        right_fair_hash=right.metadata.fair_hash,
        right_fair_salt=right.metadata.fair_salt,
        correlation=correlation,
        lag=lag,
        overlap=overlap,
        classification=classification,
    )


def _conclusion(pairs: list[TwinPair]) -> str:
    cross_seed = [
        pair for pair in pairs
        if pair.left_fair_hash != pair.right_fair_hash or pair.left_fair_salt != pair.right_fair_salt
    ]
    if cross_seed:
        return (
            "Обнаружены высококоррелированные траектории при разных hash/salt. "
            "Это не доказывает идентичность генератора, но требует отдельного replay-анализа чистых тиков."
        )
    if pairs:
        return "Все найденные близнецы имеют совпадающие hash/salt либо неполные fairness-поля."
    return "В текущей пачке статистически значимых близнецов не найдено."
