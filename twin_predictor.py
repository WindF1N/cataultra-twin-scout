#!/usr/bin/env python3
"""
Twin Predictor: построение базы эталонных паттернов (оптимизированная версия).
Режимы:
  --build             Только топ-30 хабов (быстро, 30 эталонов)
  --build --all-clusters   Все компоненты связности (сотни эталонов, дольше)
Использование:
    python twin_predictor.py --data_dir private/twin_scout --build
    python twin_predictor.py --data_dir private/twin_scout --build --all-clusters
"""
import argparse
import json
import tarfile
import re
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, List, Set

import numpy as np

# ----------------------------------------------------------------------
def parse_twins_report(content: str) -> List[dict]:
    pattern = (
        r'### (.+?) / (.+?)\s*\n'
        r'- Класс: `(.+?)`\s*\n'
        r'- Корреляция: `([\d.]+)`\s*\n'
        r'- Lag: `(-?\d+)`\s*\n'
        r'- Overlap: `(\d+)`\s*\n'
        r'- Left: `(\d+)`.*?\n'
        r'- Right: `(\d+)`'
    )
    pairs = []
    for m in re.finditer(pattern, content, re.MULTILINE):
        t1, t2, cls, corr, lag, overlap, left_id, right_id = m.groups()
        pairs.append({
            't1': left_id, 't2': right_id,
            'corr': float(corr), 'lag': int(lag), 'overlap': int(overlap),
            'class': cls.strip()
        })
    return pairs

def normalize_ticks(ticks: List[float]) -> List[float]:
    if not ticks or ticks[0] == 0:
        return ticks
    return [t / ticks[0] for t in ticks]

def load_all_ticks_from_archives(archives: List[Path], needed_ids: Set[str]) -> Dict[str, List[float]]:
    """Загружает тики для заданного множества ID, возвращает словарь id -> normalized list."""
    all_ticks = {}
    for i, arch_path in enumerate(archives, 1):
        with tarfile.open(arch_path, 'r:gz') as tar:
            id_to_member = {}
            for member in tar.getmembers():
                parts = member.name.split('/')
                if len(parts) >= 3 and parts[2] == 'pure_ticks.json':
                    token_dir = parts[1]
                    if token_dir.startswith('token_'):
                        dir_parts = token_dir.split('_')
                        if len(dir_parts) >= 2:
                            token_id = dir_parts[1]
                            if token_id in needed_ids:
                                id_to_member[token_id] = member
            for token_id, member in id_to_member.items():
                data = json.loads(tar.extractfile(member).read().decode('utf-8'))
                ticks = data.get('ticksArray', data.get('ticks', [])) if isinstance(data, dict) else data
                if ticks:
                    all_ticks[token_id] = normalize_ticks([float(t) for t in ticks])
        # Не печатаем прогресс для каждого архива, чтобы не засорять вывод, но можно включить при желании
    return all_ticks

def find_connected_components(graph: Dict[str, Set[str]]) -> List[Set[str]]:
    """Возвращает список компонент связности (каждая компонента — множество ID)."""
    visited = set()
    components = []
    for node in graph:
        if node not in visited:
            comp = set()
            queue = deque([node])
            visited.add(node)
            while queue:
                cur = queue.popleft()
                comp.add(cur)
                for neighbor in graph[cur]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(comp) >= 3:  # минимум 3 токена, чтобы был смысл усреднять
                components.append(comp)
    return components

def build_pattern_db(data_dir: Path, use_all_clusters: bool = False) -> dict:
    archives = sorted(data_dir.glob('session_1k_*.tar.gz'))
    if not archives:
        print("Архивы не найдены.")
        return {}

    print("Сканируем отчёты twins_report.md во всех архивах...")
    graph = defaultdict(set)
    for i, arch_path in enumerate(archives, 1):
        try:
            with tarfile.open(arch_path, 'r:gz') as tar:
                report_file = None
                for m in tar.getmembers():
                    if 'twins_report.md' in m.name:
                        report_file = m
                        break
                if not report_file:
                    continue
                content = tar.extractfile(report_file).read().decode('utf-8')
                pairs = parse_twins_report(content)
                for p in pairs:
                    graph[p['t1']].add(p['t2'])
                    graph[p['t2']].add(p['t1'])
        except Exception as e:
            print(f"Ошибка в {arch_path.name}: {e}")
    print(f"Граф содержит {len(graph)} узлов.")

    if use_all_clusters:
        # Режим всех компонент
        components = find_connected_components(graph)
        print(f"Найдено компонент связности (размер >=3): {len(components)}")
        # Собираем все уникальные ID из всех компонент
        all_needed_ids = set()
        for comp in components:
            all_needed_ids.update(comp)
        print(f"Всего токенов для загрузки: {len(all_needed_ids)}")
        print("Загружаем тики...")
        all_ticks = load_all_ticks_from_archives(archives, all_needed_ids)
        print(f"Загружено тиков для {len(all_ticks)} токенов.")

        patterns = {}
        for comp_idx, comp in enumerate(components, 1):
            # Собираем тики для токенов этой компоненты
            comp_ticks = [all_ticks[tid] for tid in comp if tid in all_ticks]
            if len(comp_ticks) < 3:
                continue
            min_len = min(len(c) for c in comp_ticks)
            trimmed = [c[:min_len] for c in comp_ticks]
            avg = np.mean(trimmed, axis=0).tolist()
            # Идентификатор паттерна — первый ID в компоненте для воспроизводимости
            first_id = next(iter(comp))
            pattern_id = f"cluster_{first_id}"
            patterns[pattern_id] = {
                'hub_id': pattern_id,
                'ticker': '?',
                'num_twins': len(comp_ticks),
                'avg_curve': avg
            }
            np.save(data_dir / f'pattern_{pattern_id}.npy', np.array(avg))
        print(f"Создано паттернов: {len(patterns)}")

    else:
        # Режим топ-30 хабов (старый)
        degrees = {k: len(v) for k, v in graph.items()}
        top_hubs = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:30]
        top_hubs = [(hub, deg) for hub, deg in top_hubs if deg >= 5]
        print(f"Выбрано {len(top_hubs)} хабов.")
        all_needed_ids = set()
        for hub_id, _ in top_hubs:
            all_needed_ids.add(hub_id)
            all_needed_ids.update(graph[hub_id])
        print(f"Всего ID для загрузки: {len(all_needed_ids)}")
        all_ticks = load_all_ticks_from_archives(archives, all_needed_ids)
        print(f"Загружено тиков: {len(all_ticks)}")

        patterns = {}
        for hub_id, _ in top_hubs:
            twin_ticks = [all_ticks[tid] for tid in graph[hub_id] if tid in all_ticks]
            if len(twin_ticks) < 3:
                continue
            min_len = min(len(c) for c in twin_ticks)
            trimmed = [c[:min_len] for c in twin_ticks]
            avg = np.mean(trimmed, axis=0).tolist()
            patterns[hub_id] = {
                'hub_id': hub_id,
                'ticker': '?',
                'num_twins': len(twin_ticks),
                'avg_curve': avg
            }
            np.save(data_dir / f'pattern_{hub_id}.npy', np.array(avg))

    # Сохраняем мета-базу
    meta = {pid: {'ticker': '?', 'num_twins': p['num_twins'], 'file': f'pattern_{pid}.npy'}
            for pid, p in patterns.items()}
    with open(data_dir / 'patterns_db.json', 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"База паттернов сохранена: {len(patterns)} эталонов")
    return patterns

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='private/twin_scout', help='Папка с архивами сессий')
    parser.add_argument('--build', action='store_true', help='Построить базу паттернов')
    parser.add_argument('--all-clusters', action='store_true', help='Использовать все компоненты связности, а не только топ-хабы')
    args = parser.parse_args()

    if args.build:
        build_pattern_db(Path(args.data_dir), use_all_clusters=args.all_clusters)
    else:
        print("Используйте --build [--all-clusters] для создания базы эталонов.")

if __name__ == '__main__':
    main()