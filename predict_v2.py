#!/usr/bin/env python3
"""
Twin Predictor v2 — SHORT-only, мультирежим (CRACK, FLASH, MAYHEM...).
Использует patterns_crash/ — по одному падающему эталону на режим.
"""
import argparse, json, os, sys, time
from pathlib import Path
import numpy as np
import requests

# ------------------------------------------------------------
def load_patterns(data_dir: Path):
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

def find_best_pattern(ticks, patterns, speed_mode, min_corr, max_lag, max_ticks):
    norm = np.array(ticks) / ticks[0]
    best = None
    for n_start in range(10, min(max_ticks, len(norm)-5)):
        seg = norm[:n_start]
        for pid, pat in patterns.items():
            if pat['mode'] != speed_mode:
                continue
            curve = pat['avg_curve']
            if len(curve) < n_start + 5:
                continue
            corr, lag = correlation_with_lag(seg, curve[:n_start], max_lag)
            if corr < min_corr:
                continue
            idx = n_start + lag
            if idx >= len(curve):
                continue
            remaining = curve[idx:]
            pred_min = np.min(remaining)
            pred_final = remaining[-1]
            # SHORT: ждём, что цена упадёт
            if pred_final < 1.0 and pred_final < pred_min:
                # limit sell на уровне pred_max (наивысшая точка оставшейся части)
                pred_max = np.max(remaining)
                entry_price = pred_max
                tp_price = pred_final
                # стоп: на X% выше входа (по умолчанию 0.5 = 50%)
                sl_price = entry_price * (1 + 0.5)
                if corr > (best['corr'] if best else -1):
                    best = {
                        'corr': corr,
                        'pattern': pid,
                        'n_start': n_start,
                        'lag': lag,
                        'entry': entry_price,
                        'tp': tp_price,
                        'sl': sl_price,
                        'pred_min': pred_min,
                        'pred_final': pred_final,
                        'mode': speed_mode
                    }
    return best

# ------------------------------------------------------------
class CatapultAPI:
    def __init__(self, api_key=None):
        self.url = "https://graphql.catapult.trade/graphql"
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def list_tokens(self, limit=50, speed_modes=None):
        query = """
        query TurboTokenList($input: TurboTokenListInput!) {
            turboTokenList(input: $input) {
                items {
                    id
                    symbol
                    price
                    initialPrice
                    speedMode
                    endDate
                }
            }
        }
        """
        variables = {"input": {"limit": limit, "rank": 0, "speedModes": speed_modes}}
        resp = requests.post(self.url, json={"query": query, "variables": variables}, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()['data']['turboTokenList']['items']

# ------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patterns_dir', default='private/twin_scout/patterns_crash')
    parser.add_argument('--speed_mode', default='CRACK,FLASH,MAYHEM', help='Режимы через запятую')
    parser.add_argument('--min_corr', type=float, default=0.95)
    parser.add_argument('--max_lag', type=int, default=1)
    parser.add_argument('--max_ticks', type=int, default=30, help='Макс. число начальных тиков для анализа')
    parser.add_argument('--live_interval', type=int, default=3, help='Интервал опроса API, сек')
    parser.add_argument('--live', action='store_true', help='Запустить live-наблюдение')
    args = parser.parse_args()

    patterns = load_patterns(Path(args.patterns_dir))
    print(f"Загружено паттернов: {len(patterns)} (режимы: {set(p['mode'] for p in patterns.values())})")

    if not args.live:
        print("Используйте --live для запуска наблюдения")
        return

    speed_modes = [m.strip() for m in args.speed_mode.split(',')]
    # Оставляем только те режимы, что есть в базе
    active_modes = [m for m in speed_modes if any(p['mode']==m for p in patterns.values())]
    print(f"Режимы для мониторинга: {active_modes}")

    api = CatapultAPI(api_key=os.environ.get('CATAULTRA_API_KEY'))
    tracked = {}  # token_id -> {'prices': [...], 'speed_mode': ..., 'symbol': ..., 'initialPrice': ...}

    print("Запущено live-наблюдение. Сигналы сохраняются в live_predictions.json. Ctrl+C для остановки.")
    try:
        while True:
            try:
                tokens = api.list_tokens(limit=100, speed_modes=active_modes)
            except Exception as e:
                print(f"[Ошибка API] {e}")
                time.sleep(args.live_interval)
                continue

            for tok in tokens:
                tid = tok['id']
                mode = tok.get('speedMode', 'UNKNOWN')
                if mode not in active_modes:
                    continue
                if tid in tracked:
                    tracked[tid]['prices'].append(tok['price'])
                else:
                    tracked[tid] = {
                        'prices': [tok['price']],
                        'speed_mode': mode,
                        'initialPrice': tok['initialPrice'],
                        'symbol': tok.get('symbol', '?')
                    }

            # Проверяем накопленные тики
            for tid, data in list(tracked.items()):
                if len(data['prices']) >= 10:
                    prediction = find_best_pattern(
                        data['prices'], patterns, data['speed_mode'],
                        min_corr=args.min_corr, max_lag=args.max_lag, max_ticks=args.max_ticks
                    )
                    if prediction:
                        print(f"\n[SHORT сигнал] {tid} ({data['symbol']}) режим {data['speed_mode']}")
                        print(f"  Корреляция: {prediction['corr']:.4f}, паттерн: {prediction['pattern']}")
                        print(f"  Тейк-профит (норм): {prediction['tp']:.4f}, стоп-лосс: {prediction['sl']:.2f}")
                        with open('live_predictions.json', 'a') as f:
                            json.dump({
                                'token_id': tid,
                                'symbol': data['symbol'],
                                'mode': data['speed_mode'],
                                'timestamp': time.time(),
                                **prediction
                            }, f)
                            f.write('\n')
                        del tracked[tid]
                    elif len(data['prices']) >= args.max_ticks * 2:
                        # Долго нет сигнала — удаляем
                        del tracked[tid]
            time.sleep(args.live_interval)
    except KeyboardInterrupt:
        print("Наблюдение остановлено.")

if __name__ == '__main__':
    main()