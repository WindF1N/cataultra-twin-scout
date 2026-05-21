#!/usr/bin/env python3
"""
Визуализация всех эталонных паттернов из базы.
Использование:
    python visualize_all_patterns.py --data_dir private/twin_scout [--grid]
"""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

def load_patterns(data_dir: Path) -> dict:
    db_file = data_dir / 'patterns_db.json'
    if not db_file.exists():
        print("База паттернов не найдена. Сначала запустите twin_predictor.py --build")
        exit(1)
    with open(db_file) as f:
        meta = json.load(f)
    patterns = {}
    for pid, info in meta.items():
        npy_file = data_dir / info['file']
        if npy_file.exists():
            avg = np.load(npy_file).tolist()
            patterns[pid] = {
                'id': pid,
                'ticker': info.get('ticker', '?'),
                'num_twins': info['num_twins'],
                'avg_curve': avg
            }
    return patterns

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='private/twin_scout', help='Папка с patterns_db.json и .npy')
    parser.add_argument('--grid', action='store_true', help='Сгенерировать сетку по 25 паттернов на листе (сохранит в all_patterns_plots/)')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    patterns = load_patterns(data_dir)
    print(f"Загружено паттернов: {len(patterns)}")

    # Подготовка данных
    all_curves = []
    lengths = []
    final_prices = []
    min_values = []
    for pid, p in patterns.items():
        curve = p['avg_curve']
        all_curves.append(curve)
        lengths.append(len(curve))
        final_prices.append(curve[-1])
        min_values.append(min(curve))

    # Общий график всех кривых
    plt.figure(figsize=(14, 8))
    for curve in all_curves:
        plt.plot(curve, alpha=0.3, linewidth=0.8)
    plt.axhline(y=1.0, color='black', linestyle=':', alpha=0.5, label='Начальная цена (1.0)')
    plt.title(f'Все эталонные паттерны ({len(all_curves)} шт.)')
    plt.xlabel('Тик (время)')
    plt.ylabel('Нормированная цена')
    plt.legend()
    plt.tight_layout()
    plt.savefig(data_dir / 'all_patterns_overview.png', dpi=150)
    print(f"Общий график сохранён: {data_dir / 'all_patterns_overview.png'}")

    # Статистика
    print("\n=== Статистика по всем паттернам ===")
    print(f"Количество паттернов: {len(patterns)}")
    print(f"Средняя длина: {np.mean(lengths):.1f} тиков")
    print(f"Средняя финальная цена: {np.mean(final_prices):.4f}")
    print(f"Медианная финальная цена: {np.median(final_prices):.4f}")
    print(f"Минимальная финальная цена: {min(final_prices):.4f}, максимальная: {max(final_prices):.4f}")
    up_count = sum(1 for fp in final_prices if fp > 1.0)
    down_count = sum(1 for fp in final_prices if fp < 1.0)
    flat_count = len(final_prices) - up_count - down_count
    print(f"Заканчиваются выше старта: {up_count}, ниже старта: {down_count}, без изменений: {flat_count}")

    # Гистограмма финальных цен
    plt.figure(figsize=(10, 5))
    plt.hist(final_prices, bins=40, edgecolor='white', color='steelblue')
    plt.axvline(x=1.0, color='red', linestyle='--', label='Стартовая цена')
    plt.title('Распределение финальной цены паттернов')
    plt.xlabel('Финальная цена (норм.)')
    plt.ylabel('Количество паттернов')
    plt.legend()
    plt.tight_layout()
    plt.savefig(data_dir / 'pattern_finals_hist.png', dpi=150)
    print(f"Гистограмма финалов: {data_dir / 'pattern_finals_hist.png'}")

    # Гистограмма глобальных минимумов
    plt.figure(figsize=(10, 5))
    plt.hist(min_values, bins=40, edgecolor='white', color='darkorange')
    plt.title('Распределение минимального значения в паттернах')
    plt.xlabel('Минимальная цена (норм.)')
    plt.ylabel('Количество паттернов')
    plt.tight_layout()
    plt.savefig(data_dir / 'pattern_minimums_hist.png', dpi=150)
    print(f"Гистограмма минимумов: {data_dir / 'pattern_minimums_hist.png'}")

    # Если нужна сетка
    if args.grid:
        output_dir = Path('all_patterns_plots')
        output_dir.mkdir(exist_ok=True)
        pat_list = list(patterns.items())
        n_total = len(pat_list)
        ncols = 5
        nrows = 5  # 25 на листе
        for page_start in range(0, n_total, ncols * nrows):
            page_pats = pat_list[page_start:page_start + ncols * nrows]
            if not page_pats:
                break
            fig, axes = plt.subplots(nrows, ncols, figsize=(20, 16))
            axes = axes.flatten()
            for idx, (pid, p) in enumerate(page_pats):
                ax = axes[idx]
                ax.plot(p['avg_curve'], linewidth=0.8)
                ax.set_title(f"{pid}\n({p['num_twins']} близн.)", fontsize=8)
                ax.axhline(y=1.0, color='gray', linestyle=':', alpha=0.5)
            # Скрыть лишние оси
            for j in range(idx + 1, len(axes)):
                axes[j].set_visible(False)
            plt.tight_layout()
            page_num = page_start // (ncols * nrows) + 1
            fname = output_dir / f'patterns_page_{page_num:02d}.png'
            plt.savefig(fname, dpi=100)
            plt.close()
            print(f"  Сохранена страница {page_num}")
        print(f"Сетка сохранена в {output_dir}/")

if __name__ == '__main__':
    main()