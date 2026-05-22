#!/usr/bin/env python3
"""
Построение базы паттернов, сгруппированных по speed_mode.
1. Из всех архивов собираются все токены с их speed_mode и тиками.
2. Токены группируются по speed_mode.
3. Внутри группы вычисляются попарные корреляции (оптимизированно).
4. Строится граф связей (корреляция >= 0.95).
5. Находятся компоненты связности, для каждой строится усреднённый паттерн.
Использование:
    python build_patterns_by_mode.py --data_dir private/twin_scout
"""
import argparse
import json
import tarfile
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

import numpy as np
from tqdm import tqdm

# ----------------------------------------------------------------------
def load_all_tokens(data_dir: Path) -> Dict[str, dict]:
    """Извлекает из всех архивов id, speed_mode, ticks для каждого токена.
    Возвращает словарь: token_id -> {'speed_mode': str, 'ticks': List[float]}."""
    archives = sorted(data_dir.glob('session_1k_*.tar.gz'))
    tokens = {}
    for arch_path in tqdm(archives, desc="Сканируем архивы"):
        with tarfile.open(arch_path, 'r:gz') as tar:
            # Сначала собираем ID и speed_mode из metadata
            meta_files = {}
            tick_files = {}
            for member in tar.getmembers():
                parts = member.name.split('/')
                if len(parts) >= 3:
                    token_dir = parts[1]  # token_<id>_<ticker>
                    if token_dir.startswith('token_'):
                        dir_parts = token_dir.split('_')
                        if len(dir_parts) >= 2:
                            token_id = dir_parts[1]
                            if parts[2] == 'token_metadata.json':
                                meta_files[token_id] = member
                            elif parts[2] == 'pure_ticks.json':
                                tick_files[token_id] = member
            for token_id, meta_member in meta_files.items():
                try:
                    meta = json.loads(tar.extractfile(meta_member).read().decode('utf-8'))
                    speed_mode = meta.get('speedMode', meta.get('speed_mode', 'UNKNOWN'))
                    tokens[token_id] = {'speed_mode': speed_mode, 'ticks': None}
                except:
                    pass
            for token_id, tick_member in tick_files.items():
                if token_id in tokens:
                    try:
                        data = json.loads(tar.extractfile(tick_member).read().decode('utf-8'))
                        ticks = data.get('ticksArray', data.get('ticks', [])) if isinstance(data, dict) else data
                        if ticks:
                            tokens[token_id]['ticks'] = [float(t) for t in ticks]
                    except:
                        pass
    # Оставляем только токены с тиками
    tokens = {k: v for k, v in tokens.items() if v['ticks'] is not None}
    print(f"Загружено {len(tokens)} токенов с тиками.")
    return tokens

def normalize_ticks(ticks: List[float]) -> np.ndarray:
    """Нормализация и преобразование в numpy array."""
    arr = np.array(ticks, dtype=np.float32)
    if arr[0] != 0:
        arr = arr / arr[0]
    return arr

def compute_correlation_matrix(ticks_list: List[np.ndarray], min_overlap: int = 10) -> np.ndarray:
    """
    Вычисляет матрицу максимальных корреляций между всеми парами кривых.
    Использует только лаг 0 для скорости.
    """
    n = len(ticks_list)
    corr_matrix = np.zeros((n, n), dtype=np.float32)
    lengths = np.array([len(t) for t in ticks_list])

    for i in tqdm(range(n), desc="Вычисляем корреляции", leave=False):
        len_i = lengths[i]
        for j in range(i + 1, n):
            overlap = min(len_i, lengths[j])
            if overlap < min_overlap:
                continue
            seg_i = ticks_list[i][:overlap]
            seg_j = ticks_list[j][:overlap]
            if np.std(seg_i) < 1e-8 or np.std(seg_j) < 1e-8:
                corr = 0.0
            else:
                corr = np.corrcoef(seg_i, seg_j)[0, 1]
            if corr < 0.95:
                # Если без лага корреляция низкая, пробуем лаг ±1 (быстро)
                for lag in [-1, 1]:
                    if lag < 0:
                        s_i = seg_i[-lag:]
                        s_j = seg_j[:overlap + lag]
                    else:
                        s_i = seg_i[:overlap - lag]
                        s_j = seg_j[lag:overlap]
                    if len(s_i) < min_overlap or len(s_j) < min_overlap:
                        continue
                    if np.std(s_i) < 1e-8 or np.std(s_j) < 1e-8:
                        continue
                    c = np.corrcoef(s_i, s_j)[0, 1]
                    if c > corr:
                        corr = c
            corr_matrix[i, j] = corr
            corr_matrix[j, i] = corr
    return corr_matrix

def build_graph(corr_matrix: np.ndarray, threshold: float = 0.95) -> Dict[int, Set[int]]:
    """Строит граф связей по матрице корреляций."""
    n = corr_matrix.shape[0]
    graph = defaultdict(set)
    for i in range(n):
        for j in range(i + 1, n):
            if corr_matrix[i, j] >= threshold:
                graph[i].add(j)
                graph[j].add(i)
    return graph

def find_components(graph: Dict[int, Set[int]], min_size: int = 3) -> List[Set[int]]:
    """Возвращает список компонент связности с размером >= min_size."""
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
            if len(comp) >= min_size:
                components.append(comp)
    return components

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='private/twin_scout', help='Папка с архивами сессий')
    parser.add_argument('--min_corr', type=float, default=0.95, help='Порог корреляции для близнецов')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    # 1. Загрузка всех токенов
    tokens = load_all_tokens(data_dir)
    if not tokens:
        print("Нет данных.")
        return

    # 2. Группировка по speed_mode
    modes = defaultdict(list)
    for token_id, info in tokens.items():
        mode = info['speed_mode']
        modes[mode].append((token_id, info['ticks']))

    print(f"\nТокенов по режимам:")
    for mode, items in sorted(modes.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {mode}: {len(items)}")

    # 3. Для каждого режима строим паттерны
    output_dir = data_dir / 'patterns_by_mode'
    output_dir.mkdir(exist_ok=True)
    all_patterns = {}

    for mode, items in modes.items():
        if len(items) < 10:
            print(f"\nРежим {mode}: слишком мало токенов, пропускаем.")
            continue
        print(f"\n{'='*50}\nОбрабатываем режим {mode} ({len(items)} токенов)")

        ids = [item[0] for item in items]
        ticks_raw = [item[1] for item in items]

        # Нормализуем
        ticks_norm = [normalize_ticks(t) for t in ticks_raw]

        # Вычисляем корреляционную матрицу
        print("  Вычисляем попарные корреляции...")
        corr_mat = compute_correlation_matrix(ticks_norm)

        # Строим граф
        graph = build_graph(corr_mat, threshold=args.min_corr)
        # Переводим индексы в ID токенов
        id_graph = defaultdict(set)
        for i, neighbors in graph.items():
            for j in neighbors:
                id_graph[ids[i]].add(ids[j])

        # Находим компоненты
        components = find_components(id_graph, min_size=3)
        print(f"  Найдено компонент: {len(components)}")

        # Для каждой компоненты строим усреднённый паттерн
        for comp_idx, comp in enumerate(components, 1):
            comp_ticks = [tokens[tid]['ticks'] for tid in comp if tid in tokens]
            # Нормализуем
            comp_norm = [normalize_ticks(t) for t in comp_ticks]
            min_len = min(len(c) for c in comp_norm)
            trimmed = [c[:min_len] for c in comp_norm]
            avg = np.mean(trimmed, axis=0)

            first_id = next(iter(comp))
            pattern_id = f"{mode}_cluster_{first_id}"
            all_patterns[pattern_id] = {
                'mode': mode,
                'num_twins': len(comp),
                'avg_curve': avg.tolist()
            }
            np.save(output_dir / f'pattern_{pattern_id}.npy', avg)

        print(f"  Создано паттернов для {mode}: {len([p for p in all_patterns if all_patterns[p]['mode'] == mode])}")

    # Сохраняем мета-базу
    meta = {pid: {'mode': p['mode'], 'num_twins': p['num_twins'],
                  'file': f'pattern_{pid}.npy'}
            for pid, p in all_patterns.items()}
    with open(output_dir / 'patterns_db.json', 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"\n{'='*50}")
    print(f"Всего создано паттернов: {len(all_patterns)}")
    print(f"База сохранена в {output_dir}")

if __name__ == '__main__':
    main()