#!/usr/bin/env python3
"""
Анализ токена-хаба: сбор всех близнецов, нормализация тиков,
построение усреднённого профиля и статистики финала.
Использование:
    python analyze_hub.py --hub_id 16393224 --data_dir private/twin_scout
"""
import argparse
import json
import tarfile
import re
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def parse_twins_report(content: str) -> List[dict]:
    """Извлекает все пары из twins_report.md."""
    pairs = []
    pattern = (
        r'### (.+?) / (.+?)\s*\n'
        r'- Класс: `(.+?)`\s*\n'
        r'- Корреляция: `([\d.]+)`\s*\n'
        r'- Lag: `(-?\d+)`\s*\n'
        r'- Overlap: `(\d+)`\s*\n'
        r'- Left: `(\d+)`.*?\n'
        r'- Right: `(\d+)`'
    )
    for match in re.finditer(pattern, content, re.MULTILINE):
        ticker1, ticker2, classification, corr, lag, overlap, left_id, right_id = match.groups()
        pairs.append({
            'token1_id': left_id,
            'token2_id': right_id,
            'token1_ticker': ticker1.strip(),
            'token2_ticker': ticker2.strip(),
            'correlation': float(corr),
            'lag': int(lag),
            'overlap': int(overlap),
            'classification': classification.strip()
        })
    return pairs


def load_ticks_from_archive(archive_path: Path, token_id: str) -> Tuple[List[float], dict]:
    """Извлекает pure_ticks.json для заданного token_id из архива сессии."""
    try:
        with tarfile.open(archive_path, 'r:gz') as tar:
            prefix = f'token_{token_id}/'
            ticks_file = None
            meta_file = None
            for member in tar.getmembers():
                if member.name.startswith(prefix):
                    if member.name.endswith('pure_ticks.json'):
                        ticks_file = member
                    elif member.name.endswith('token_metadata.json'):
                        meta_file = member
            if ticks_file is None:
                return [], {}
            ticks_data = json.loads(tar.extractfile(ticks_file).read().decode('utf-8'))
            meta_data = {}
            if meta_file:
                meta_data = json.loads(tar.extractfile(meta_file).read().decode('utf-8'))
            if isinstance(ticks_data, dict):
                ticks = ticks_data.get('ticksArray', ticks_data.get('ticks', []))
            else:
                ticks = ticks_data
            return ticks, meta_data
    except Exception as e:
        print(f'  Ошибка чтения архива {archive_path}: {e}')
        return [], {}


def normalize_ticks(ticks: List[float]) -> List[float]:
    """Нормализация: делим на начальную цену, чтобы все кривые начинались с 1."""
    if not ticks or ticks[0] == 0:
        return ticks
    start_price = ticks[0]
    return [t / start_price for t in ticks]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hub_id', required=True, help='ID токена-хаба')
    parser.add_argument('--data_dir', default='private/twin_scout', help='Папка с архивами .tar.gz')
    parser.add_argument('--output_dir', default='hub_analysis', help='Папка для сохранения графиков')
    args = parser.parse_args()

    hub_id = args.hub_id
    data_path = Path(args.data_dir)
    archives = sorted(data_path.glob('session_1k_*.tar.gz'))

    # Собираем всех близнецов хаба
    twin_ids = set()
    hub_ticker = None
    pair_info = []

    for arch_path in archives:
        session_name = arch_path.stem
        try:
            with tarfile.open(arch_path, 'r:gz') as tar:
                report_file = None
                for member in tar.getmembers():
                    if 'twins_report.md' in member.name:
                        report_file = member
                        break
                if report_file is None:
                    continue
                content = tar.extractfile(report_file).read().decode('utf-8')
                pairs = parse_twins_report(content)
                for p in pairs:
                    if p['token1_id'] == hub_id:
                        twin_ids.add(p['token2_id'])
                        if hub_ticker is None:
                            hub_ticker = p['token1_ticker']
                        pair_info.append({
                            'twin_id': p['token2_id'],
                            'ticker': p['token2_ticker'],
                            'correlation': p['correlation'],
                            'lag': p['lag'],
                            'session': session_name
                        })
                    elif p['token2_id'] == hub_id:
                        twin_ids.add(p['token1_id'])
                        if hub_ticker is None:
                            hub_ticker = p['token2_ticker']
                        pair_info.append({
                            'twin_id': p['token1_id'],
                            'ticker': p['token1_ticker'],
                            'correlation': p['correlation'],
                            'lag': p['lag'],
                            'session': session_name
                        })
        except Exception as e:
            print(f'Ошибка при обработке {arch_path}: {e}')

    print(f'Найдено {len(twin_ids)} уникальных близнецов для хаба {hub_id} ({hub_ticker})')
    if not twin_ids:
        print('Нет данных для анализа.')
        return

    # Составляем маппинг ID близнеца -> сессия, где он был найден
    id_to_session = {p['twin_id']: p['session'] for p in pair_info}

    # Попытаемся найти сессию с самим хабом, чтобы загрузить его тики
    hub_ticks_raw = []
    hub_session = None
    for arch_path in archives:
        with tarfile.open(arch_path, 'r:gz') as tar:
            if any(member.name.startswith(f'token_{hub_id}/') for member in tar.getmembers()):
                hub_session = arch_path.stem
                break
    if hub_session:
        hub_arch = data_path / f'{hub_session}.tar.gz'
        if hub_arch.exists():
            hub_ticks_raw, _ = load_ticks_from_archive(hub_arch, hub_id)
            if hub_ticks_raw:
                print(f'Тики хаба загружены из сессии {hub_session}')
            else:
                print(f'Тики хаба не найдены в сессии {hub_session}')
        else:
            print(f'Архив {hub_session}.tar.gz не существует')
    else:
        print(f'Архив с токеном {hub_id} не найден ни в одной сессии')
    hub_ticks_norm = normalize_ticks(hub_ticks_raw) if hub_ticks_raw else []

    # Загружаем тики всех близнецов
    twin_ticks = {}
    for twin_id in twin_ids:
        session = id_to_session.get(twin_id)
        if not session:
            continue
        arch_path = data_path / f'{session}.tar.gz'
        if not arch_path.exists():
            continue
        ticks_raw, meta = load_ticks_from_archive(arch_path, twin_id)
        if ticks_raw:
            twin_ticks[twin_id] = normalize_ticks(ticks_raw)

    print(f'Загружены тики для {len(twin_ticks)} близнецов.')

    # Если нет данных для анализа – выход
    if not twin_ticks:
        print('Нет тиков ни у одного близнеца.')
        return

    # Для усреднения обрезаем все до минимальной длины
    lengths = [len(v) for v in twin_ticks.values()]
    min_len = min(lengths) if lengths else 0
    if min_len < 5:
        print('Слишком короткие тики.')
        return
    twins_arrays = [v[:min_len] for v in twin_ticks.values() if len(v) >= min_len]
    if not twins_arrays:
        print('Нет подходящих кривых.')
        return

    twins_matrix = np.array(twins_arrays)
    mean_curve = np.mean(twins_matrix, axis=0)
    std_curve = np.std(twins_matrix, axis=0)
    final_prices = [arr[-1] for arr in twins_arrays]

    # Графики
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    plt.style.use('seaborn-v0_8-darkgrid')
    fig = plt.figure(figsize=(14, 10))
    gs = gridspec.GridSpec(2, 2, height_ratios=[2, 1])

    ax1 = fig.add_subplot(gs[0, :])
    x = np.arange(min_len)
    for curve in twins_arrays:
        ax1.plot(x, curve, alpha=0.15, color='gray')
    ax1.plot(x, mean_curve, 'r-', linewidth=2, label='Среднее')
    ax1.fill_between(x, mean_curve - std_curve, mean_curve + std_curve,
                     alpha=0.2, color='red', label='±1σ')
    if hub_ticks_norm:
        # обрежем хаб до min_len
        hub_short = hub_ticks_norm[:min_len]
        ax1.plot(x[:len(hub_short)], hub_short, 'b-', linewidth=2, label=f'Хаб {hub_id}')
    ax1.set_title(f'Нормализованные тики близнецов хаба {hub_id} ({hub_ticker})\nКоличество близнецов: {len(twins_arrays)}')
    ax1.set_xlabel('Тик (время)')
    ax1.set_ylabel('Цена (норм.)')
    ax1.legend()

    ax2 = fig.add_subplot(gs[1, 0])
    ax2.hist(final_prices, bins=30, color='steelblue', edgecolor='white')
    ax2.axvline(x=np.mean(final_prices), color='red', linestyle='--', label=f'Среднее: {np.mean(final_prices):.3f}')
    ax2.set_title('Распределение финальной цены')
    ax2.set_xlabel('Цена (относительно старта)')
    ax2.set_ylabel('Частота')
    ax2.legend()

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.boxplot(final_prices, vert=True)
    ax3.set_title('Боксплот финальной цены')
    ax3.set_ylabel('Цена (норм.)')
    ax3.set_xticklabels([])

    plt.tight_layout()
    plot_path = output_dir / f'hub_{hub_id}_profile.png'
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f'График сохранён: {plot_path}')

    # Статистика
    print('\n=== Статистика близнецов хаба ===')
    print(f'Количество близнецов (с тиками): {len(twins_arrays)}')
    print(f'Средняя финальная цена: {np.mean(final_prices):.4f} (от стартовой)')
    print(f'Медианная финальная цена: {np.median(final_prices):.4f}')
    print(f'Стд. откл. финала: {np.std(final_prices):.4f}')
    print(f'Минимум финала: {np.min(final_prices):.4f}, максимум: {np.max(final_prices):.4f}')
    min_idx = np.argmin(mean_curve)
    print(f'Глобальный минимум средней кривой: тик {min_idx}, значение {mean_curve[min_idx]:.4f}')
    if min_idx < len(mean_curve) - 5:
        post_min = mean_curve[min_idx:]
        if post_min[-1] > mean_curve[min_idx] * 1.01:
            print(f'Обнаружен отскок: после тика {min_idx} цена растёт к финалу ({mean_curve[-1]:.4f})')
    if pair_info:
        avg_corr = np.mean([p['correlation'] for p in pair_info])
        print(f'Средняя корреляция с хабом: {avg_corr:.4f}')

if __name__ == '__main__':
    main()