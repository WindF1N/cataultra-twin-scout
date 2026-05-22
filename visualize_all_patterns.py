#!/usr/bin/env python3
"""
Визуализация всех эталонных паттернов из базы patterns_by_mode/.
Использование:
    python visualize_all_patterns.py --data_dir private/twin_scout/patterns_by_mode [--grid]
"""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

def load_patterns(data_dir: Path) -> dict:
    db_file = data_dir / 'patterns_db.json'
    if not db_file.exists():
        print(f"База не найдена: {db_file}")
        exit(1)
    with open(db_file) as f:
        meta = json.load(f)
    patterns = {}
    for pid, info in meta.items():
        npy_file = data_dir / info['file']
        if npy_file.exists():
            avg = np.load(npy_file)
            patterns[pid] = {
                'id': pid,
                'mode': info['mode'],
                'num_twins': info['num_twins'],
                'avg_curve': avg
            }
    return patterns

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='private/twin_scout/patterns_by_mode', 
                        help='Папка с patterns_db.json и .npy файлами')
    parser.add_argument('--grid', action='store_true', 
                        help='Показать сетку по каждому режиму')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    patterns = load_patterns(data_dir)
    print(f"Загружено паттернов: {len(patterns)}")

    # Группировка по режимам
    mode_patterns = {}
    for pid, p in patterns.items():
        mode = p['mode']
        mode_patterns.setdefault(mode, []).append(p)

    # Цвета для режимов
    mode_colors = {
        'NORMAL': 'green',
        'FAST': 'blue',
        'FLASH': 'orange',
        'CRACK': 'red',
        'MAYHEM': 'purple'
    }

    # 1. Общий график: все паттерны, цвет по режиму
    plt.figure(figsize=(14, 8))
    for mode, pats in mode_patterns.items():
        color = mode_colors.get(mode, 'gray')
        for p in pats:
            plt.plot(p['avg_curve'], alpha=0.4, linewidth=0.8, color=color)
    plt.axhline(y=1.0, color='black', linestyle=':', alpha=0.5, label='Старт (1.0)')
    plt.title(f'Все эталонные паттерны ({len(patterns)} шт.) по speed_mode')
    plt.xlabel('Тик')
    plt.ylabel('Норм. цена')
    # Легенда по режимам
    from matplotlib.lines import Line2D
    legend_elements = [Line2D([0], [0], color=mode_colors.get(m, 'gray'), lw=2, label=m) 
                       for m in sorted(mode_patterns.keys())]
    plt.legend(handles=legend_elements, title='Режим')
    plt.tight_layout()
    plt.savefig(data_dir / 'all_patterns_overview.png', dpi=150)
    print(f"Общий график сохранён: {data_dir / 'all_patterns_overview.png'}")

    # 2. Отдельные графики по каждому режиму
    for mode, pats in sorted(mode_patterns.items()):
        plt.figure(figsize=(12, 6))
        for p in pats:
            plt.plot(p['avg_curve'], alpha=0.7, linewidth=0.8)
        plt.axhline(y=1.0, color='black', linestyle=':', alpha=0.5)
        plt.title(f'Режим {mode} ({len(pats)} паттернов)')
        plt.xlabel('Тик')
        plt.ylabel('Норм. цена')
        plt.tight_layout()
        fname = data_dir / f'patterns_{mode}.png'
        plt.savefig(fname, dpi=150)
        plt.close()
        print(f"График режима {mode}: {fname}")

    # 3. Если нужна сетка (по каждому режиму на отдельной странице)
    if args.grid:
        import math
        for mode, pats in sorted(mode_patterns.items()):
            n = len(pats)
            cols = 5
            rows = math.ceil(n / cols)
            fig, axes = plt.subplots(rows, cols, figsize=(cols*4, rows*3))
            axes = axes.flatten() if n > 1 else [axes]
            for i, p in enumerate(pats):
                ax = axes[i]
                ax.plot(p['avg_curve'], linewidth=0.8)
                ax.set_title(f"{p['id']}\n({p['num_twins']} близн.)", fontsize=7)
                ax.axhline(y=1.0, color='gray', linestyle=':', alpha=0.5)
            for j in range(i+1, len(axes)):
                axes[j].set_visible(False)
            plt.tight_layout()
            fname = data_dir / f'patterns_{mode}_grid.png'
            plt.savefig(fname, dpi=120)
            plt.close()
            print(f"Сетка режима {mode}: {fname}")

    # 4. Статистика по режимам
    print("\n=== Статистика по режимам ===")
    for mode, pats in sorted(mode_patterns.items()):
        finals = [p['avg_curve'][-1] for p in pats]
        mins = [min(p['avg_curve']) for p in pats]
        print(f"{mode}: паттернов {len(pats)}, "
              f"средняя финальная цена {np.mean(finals):.3f}, "
              f"мин.финал {min(finals):.3f}, макс.финал {max(finals):.3f}")

if __name__ == '__main__':
    main()