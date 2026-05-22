#!/usr/bin/env python3
import argparse, json, tarfile
from pathlib import Path
import numpy as np
from tqdm import tqdm

def load_patterns(data_dir: Path, exclude=None, speed_mode=None):
    with open(data_dir / 'patterns_db.json') as f:
        meta = json.load(f)
    patterns = {}
    for pid, info in meta.items():
        if speed_mode and info['mode'] != speed_mode:
            continue
        if exclude and pid == exclude:
            continue
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

def simulate_order(entry_type, limit_price, tp_price, sl_price, true_prices, start_idx):
    """Симулирует лимитный ордер: возвращает цену закрытия и флаг срабатывания стопа."""
    # Ждём достижения лимитной цены
    for i in range(start_idx, len(true_prices)):
        if (entry_type == 'LONG' and true_prices[i] <= limit_price) or \
           (entry_type == 'SHORT' and true_prices[i] >= limit_price):
            # Открываем позицию
            entry_price = limit_price  # идеальное исполнение
            # Следим за tp/sl
            for j in range(i+1, len(true_prices)):
                price = true_prices[j]
                if entry_type == 'LONG':
                    if price >= tp_price:
                        return tp_price, False
                    if price <= sl_price:
                        return sl_price, True
                else:  # SHORT
                    if price <= tp_price:
                        return tp_price, False
                    if price >= sl_price:
                        return sl_price, True
            # Закрытие по концу
            return true_prices[-1], False
    # Лимитный ордер не сработал
    return None, False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='private/twin_scout')
    parser.add_argument('--patterns_dir', default='private/twin_scout/patterns_by_mode')
    parser.add_argument('--test_sessions', nargs='+', default=['session_1k_044', 'session_1k_045'])
    parser.add_argument('--min_corr', type=float, default=0.95)
    parser.add_argument('--max_lag', type=int, default=1)
    parser.add_argument('--min_ticks', type=int, default=10, help='Минимум начальных тиков')
    parser.add_argument('--max_ticks', type=int, default=50, help='Максимум начальных тиков для перебора')
    parser.add_argument('--stop_loss_pct', type=float, default=0.03, help='Стоп-лосс (3% = 0.03)')
    parser.add_argument('--speed_mode', help='Ограничиться одним режимом')
    parser.add_argument('--exclude_pattern', help='Исключить паттерн по ID')
    args = parser.parse_args()

    data = Path(args.data_dir)
    patterns = load_patterns(Path(args.patterns_dir),
                             exclude=args.exclude_pattern,
                             speed_mode=args.speed_mode)
    print(f"Загружено паттернов: {len(patterns)}")

    modes = set(p['mode'] for p in patterns.values())
    test_archives = [data / f"{s}.tar.gz" for s in args.test_sessions if (data / f"{s}.tar.gz").exists()]
    tokens = load_tokens_from_archives(test_archives, needed_modes=modes)
    print(f"Загружено тестовых токенов: {len(tokens)}")

    results = []
    skipped = 0
    for tok in tqdm(tokens, desc="Backtesting"):
        mode = tok['mode']
        ticks = normalize(np.array(tok['ticks']))
        total_len = len(ticks)
        best_overall_corr = -1
        best_entry_params = None

        # Перебираем длину начального отрезка для максимальной уверенности
        for n_start in range(args.min_ticks, min(args.max_ticks, total_len - 5)):
            start_segment = ticks[:n_start]
            for pid, pat in patterns.items():
                if pat['mode'] != mode:
                    continue
                curve = pat['avg_curve']
                if len(curve) < n_start + 5:
                    continue
                corr, lag = correlation_with_lag(start_segment, curve[:n_start], max_lag=args.max_lag)
                if corr < args.min_corr:
                    continue
                # Определяем потенциал сделки
                idx = n_start + lag
                if idx >= len(curve):
                    continue
                remaining = curve[idx:]
                if len(remaining) < 5:
                    continue
                pred_min = np.min(remaining)
                pred_max = np.max(remaining)
                pred_final = remaining[-1]
                # Выбираем направление: если финал выше минимума (рост), LONG; если финал ниже максимума (падение), SHORT
                if pred_final > pred_min and pred_final > 1.0:  # ожидаем рост относительно минимума
                    entry_type = 'LONG'
                    limit_price = pred_min
                    tp_price = pred_final
                    sl_price = pred_min * (1 - args.stop_loss_pct)
                elif pred_final < pred_max and pred_final < 1.0:  # ожидаем падение относительно максимума
                    entry_type = 'SHORT'
                    limit_price = pred_max
                    tp_price = pred_final
                    sl_price = pred_max * (1 + args.stop_loss_pct)
                else:
                    continue  # нет выраженного движения

                if corr > best_overall_corr:
                    best_overall_corr = corr
                    best_entry_params = {
                        'entry_type': entry_type,
                        'limit_price': limit_price,
                        'tp_price': tp_price,
                        'sl_price': sl_price,
                        'start_idx': n_start,  # начинаем отслеживать с этого индекса
                        'pattern_id': pid,
                        'corr': corr,
                        'lag': lag
                    }

        if best_entry_params is None:
            skipped += 1
            continue

        # Симуляция сделки
        true_prices = ticks  # уже нормализованы
        exit_price, stop_hit = simulate_order(
            best_entry_params['entry_type'],
            best_entry_params['limit_price'],
            best_entry_params['tp_price'],
            best_entry_params['sl_price'],
            true_prices,
            best_entry_params['start_idx']
        )
        if exit_price is None:
            skipped += 1  # ордер не исполнился
            continue

        entry_price = best_entry_params['limit_price']
        if best_entry_params['entry_type'] == 'LONG':
            pnl = exit_price / entry_price - 1.0
        else:  # SHORT
            pnl = entry_price / exit_price - 1.0  # прибыль от падения

        results.append({
            'token_id': tok['id'],
            'mode': mode,
            'correlation': best_entry_params['corr'],
            'entry_type': best_entry_params['entry_type'],
            'pnl': float(pnl),
            'stop_hit': stop_hit,
            'pattern_id': best_entry_params['pattern_id']
        })

    print(f"\nОтфильтровано: {skipped}, сделок: {len(results)}")
    with open('backtest_v3_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    if results:
        pnls = [r['pnl'] for r in results]
        win_rate = np.mean(np.array(pnls) > 0)
        print("\n=== Результаты Backtesting V3 ===")
        print(f"Сделок: {len(pnls)}")
        print(f"Средний P&L: {np.mean(pnls):.2%}")
        print(f"Выигрышных сделок: {win_rate:.2%}")
        print(f"Максимальная прибыль: {max(pnls):.2%}, максимальный убыток: {min(pnls):.2%}")

if __name__ == '__main__':
    main()