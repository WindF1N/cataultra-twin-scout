#!/usr/bin/env python3
import argparse, json, tarfile
from pathlib import Path
import numpy as np
from tqdm import tqdm

def load_patterns(data_dir: Path) -> dict:
    with open(data_dir / 'patterns_db.json') as f:
        meta = json.load(f)
    patterns = {}
    for pid, info in meta.items():
        npy = data_dir / info['file']
        if npy.exists():
            patterns[pid] = {
                'mode': info['mode'],
                'num_twins': info['num_twins'],
                'avg_curve': np.load(npy)
            }
    return patterns

def load_tokens_from_archives(archive_paths, needed_modes=None):
    tokens = []
    for arch in tqdm(archive_paths, desc="Загрузка тестовых токенов"):
        with tarfile.open(arch, 'r:gz') as tar:
            meta_map = {}
            tick_map = {}
            for m in tar.getmembers():
                parts = m.name.split('/')
                if len(parts) >= 3 and parts[1].startswith('token_'):
                    tid = parts[1].split('_')[1]
                    if parts[2] == 'token_metadata.json':
                        raw = tar.extractfile(m).read().decode('utf-8')
                        meta = json.loads(raw)
                        mode = meta.get('speedMode', meta.get('speed_mode', 'UNKNOWN'))
                        if needed_modes is None or mode in needed_modes:
                            meta_map[tid] = mode
                    elif parts[2] == 'pure_ticks.json':
                        tick_map[tid] = m
            for tid, mode in meta_map.items():
                if tid in tick_map:
                    try:
                        raw = tar.extractfile(tick_map[tid]).read().decode('utf-8')
                        data = json.loads(raw)
                        ticks = data if isinstance(data, list) else data.get('ticksArray', data.get('ticks', []))
                        if ticks:
                            tokens.append({
                                'id': tid,
                                'mode': mode,
                                'ticks': [float(t) for t in ticks]
                            })
                    except:
                        continue
    return tokens

def normalize(arr):
    return arr / arr[0]

def correlation_with_lag(seg, pattern_start, max_lag=1):
    best_corr, best_lag = -1, 0
    for lag in range(-max_lag, max_lag+1):
        if lag < 0:
            s = seg[-lag:]
            p = pattern_start[:len(seg)+lag]
        elif lag > 0:
            s = seg[:len(pattern_start)-lag]
            p = pattern_start[lag:]
        else:
            s, p = seg, pattern_start
        if len(s) < 5 or len(p) < 5:
            continue
        if np.std(s) > 1e-6 and np.std(p) > 1e-6:
            c = np.corrcoef(s, p)[0,1]
            if c > best_corr:
                best_corr, best_lag = c, lag
    return best_corr, best_lag

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='private/twin_scout')
    parser.add_argument('--patterns_dir', default='private/twin_scout/patterns_by_mode')
    parser.add_argument('--test_sessions', nargs='+', default=['session_1k_044', 'session_1k_045'])
    parser.add_argument('--start_fraction', type=float, default=0.3)
    parser.add_argument('--min_corr', type=float, default=0.95)
    parser.add_argument('--max_lag', type=int, default=1)
    parser.add_argument('--stop_loss', type=float, default=0.05, help='Стоп-лосс ниже дна (например, 0.05 = 5%)')
    args = parser.parse_args()

    data = Path(args.data_dir)
    patterns = load_patterns(Path(args.patterns_dir))
    print(f"Загружено паттернов: {len(patterns)}")

    modes = set(p['mode'] for p in patterns.values())
    test_archives = [data / f"{s}.tar.gz" for s in args.test_sessions if (data / f"{s}.tar.gz").exists()]
    if not test_archives:
        print("Тестовые архивы не найдены.")
        return
    tokens = load_tokens_from_archives(test_archives, needed_modes=modes)
    print(f"Загружено тестовых токенов: {len(tokens)}")

    results = []
    skipped = 0
    for tok in tqdm(tokens, desc="Backtesting"):
        mode = tok['mode']
        ticks = normalize(np.array(tok['ticks']))
        n_start = max(10, int(len(ticks) * args.start_fraction))
        start_segment = ticks[:n_start]
        true_remain = ticks[n_start:]

        best_corr = -1
        best_pat = None
        best_lag = 0
        for pid, pat in patterns.items():
            if pat['mode'] != mode:
                continue
            curve = pat['avg_curve']
            if len(curve) < n_start + 5:
                continue
            corr, lag = correlation_with_lag(start_segment, curve[:n_start], max_lag=args.max_lag)
            if corr > best_corr:
                best_corr, best_pat, best_lag = corr, pat, lag

        if best_pat is None or best_corr < args.min_corr:
            skipped += 1
            continue

        idx = n_start + best_lag
        if idx >= len(best_pat['avg_curve']):
            skipped += 1
            continue
        pred_remain = best_pat['avg_curve'][idx:]
        min_len = min(len(pred_remain), len(true_remain))
        if min_len < 2:
            skipped += 1
            continue
        pred = pred_remain[:min_len]
        true = true_remain[:min_len]

        pred_min = np.min(pred)
        pred_min_idx = np.argmin(pred)
        if pred_min_idx >= len(true):
            skipped += 1
            continue

        entry_price = true[pred_min_idx]
        exit_price = true[-1]

        # Проверка стоп-лосса: если после входа цена падает ещё ниже
        stop_loss_price = pred_min * (1 - args.stop_loss)
        stop_hit = False
        for i in range(pred_min_idx, len(true)):
            if true[i] < stop_loss_price:
                exit_price = entry_price * (1 - args.stop_loss)  # фиксируем убыток
                stop_hit = True
                break

        magnet_pnl = exit_price / entry_price - 1.0

        pred_final = pred[-1]
        true_final = true[-1]
        pred_dir = np.sign(pred_final - 1.0)
        true_dir = np.sign(true_final - 1.0)
        dir_correct = (pred_dir == true_dir)

        results.append({
            'token_id': tok['id'],
            'mode': mode,
            'correlation': best_corr,
            'lag': best_lag,
            'dir_correct': bool(dir_correct),
            'pred_final': float(pred_final),
            'true_final': float(true_final),
            'magnet_pnl': float(magnet_pnl),
            'stop_loss_hit': stop_hit
        })

    print(f"\nОтфильтровано: {skipped}, прогнозов: {len(results)}")
    with open('backtest_results_stoploss.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("Результаты сохранены в backtest_results_stoploss.json")

    if results:
        corrs = [r['correlation'] for r in results]
        dir_acc = np.mean([r['dir_correct'] for r in results])
        final_errors = [abs(r['pred_final'] - r['true_final']) for r in results]
        magnet_pnls = [r['magnet_pnl'] for r in results]
        win_rate = np.mean(np.array(magnet_pnls) > 0)
        print("\n=== Результаты Backtesting (со стоп-лоссом) ===")
        print(f"Токенов: {len(results)}")
        print(f"Средняя корреляция: {np.mean(corrs):.3f}")
        print(f"Точность направления: {dir_acc:.2%}")
        print(f"Средняя ошибка финала: {np.mean(final_errors):.4f}")
        print(f"Средний P&L Magnet: {np.mean(magnet_pnls):.2%}")
        print(f"Выигрышных сделок: {win_rate:.2%}")
        print(f"Стоп-лосс сработал: {sum(1 for r in results if r['stop_loss_hit'])} раз")

        import matplotlib.pyplot as plt
        plt.figure(figsize=(10,5))
        plt.hist(magnet_pnls, bins=40, edgecolor='white')
        plt.title('P&L Magnet со стоп-лоссом 5%')
        plt.xlabel('P&L')
        plt.ylabel('Число токенов')
        plt.savefig('magnet_backtest_stoploss.png', dpi=150)
        print("Гистограмма сохранена в magnet_backtest_stoploss.png")

if __name__ == '__main__':
    main()