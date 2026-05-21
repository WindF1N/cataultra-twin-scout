#!/usr/bin/env python3
"""
Поиск супер-близнецов по всем архивированным сессиям Twin Scout.
Использование:
    python find_super_twins.py --data_dir private/twin_scout [--min_corr 0.999] [--top_n 20]
"""
import argparse
import re
import tarfile
from pathlib import Path
from collections import defaultdict
from typing import List


def parse_twins_report(content: str) -> List[dict]:
    """Извлекает список пар из текста twins_report.md."""
    pairs = []
    # Регулярное выражение для блока пары
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
            'classification': classification.strip(),
            'correlation': float(corr),
            'lag': int(lag),
            'overlap': int(overlap),
            'token1_id': left_id,
            'token1_ticker': ticker1.strip(),
            'token2_id': right_id,
            'token2_ticker': ticker2.strip(),
        })
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='private/twin_scout', help='Папка с архивами .tar.gz')
    parser.add_argument('--min_corr', type=float, default=0.999, help='Минимальная корреляция для супер-близнецов')
    parser.add_argument('--top_n', type=int, default=30, help='Сколько топ-пар показать')
    args = parser.parse_args()

    data_path = Path(args.data_dir)
    archives = sorted(data_path.glob('session_1k_*.tar.gz'))
    if not archives:
        print('Не найдено архивов сессий в', data_path)
        return

    all_pairs = []
    token_pair_count = defaultdict(int)
    pair_occurrences = defaultdict(list)

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
                    p['session'] = session_name
                    all_pairs.append(p)
                    token_pair_count[p['token1_id']] += 1
                    token_pair_count[p['token2_id']] += 1
                    pair_key = tuple(sorted([p['token1_id'], p['token2_id']]))
                    pair_occurrences[pair_key].append(session_name)
        except Exception as e:
            print(f'Ошибка при обработке {arch_path}: {e}')

    if not all_pairs:
        print('Пары не найдены ни в одном архиве.')
        return

    all_pairs.sort(key=lambda x: x['correlation'], reverse=True)
    super_pairs = [p for p in all_pairs if p['correlation'] >= args.min_corr]

    top_tokens = sorted(token_pair_count.items(), key=lambda x: x[1], reverse=True)[:args.top_n]
    recurring_pairs = {k: v for k, v in pair_occurrences.items() if len(v) > 1}
    recurring_pairs = dict(sorted(recurring_pairs.items(), key=lambda x: len(x[1]), reverse=True)[:args.top_n])

    print(f'Всего обработано сессий: {len(archives)}')
    print(f'Всего пар: {len(all_pairs)}')
    print(f'Из них супер-близнецов (corr >= {args.min_corr}): {len(super_pairs)}\n')

    print(f'=== Топ-{args.top_n} пар по корреляции ===')
    for i, p in enumerate(all_pairs[:args.top_n], 1):
        print(f"{i}. {p['classification']} | corr={p['correlation']:.4f} | lag={p['lag']} | overlap={p['overlap']}")
        print(f"   [{p['token1_ticker']}] ID:{p['token1_id']} <-> [{p['token2_ticker']}] ID:{p['token2_id']}  ({p['session']})")

    print(f'\n=== Топ-{args.top_n} токенов по числу связей (суммарно во всех сессиях) ===')
    for i, (tid, cnt) in enumerate(top_tokens, 1):
        print(f"{i}. ID:{tid}  связей: {cnt}")

    print(f'\n=== Пары, встречающиеся в нескольких сессиях (топ-{args.top_n}) ===')
    for (id1, id2), sessions in recurring_pairs.items():
        print(f"ID:{id1} <-> ID:{id2}  (сессий: {len(sessions)}) {sessions[:3]}...")

    # Сохраняем отчёт
    report_lines = []
    report_lines.append('# 🧬 Супер-близнецы CATAULTRA\n')
    report_lines.append(f'Обработано сессий: {len(archives)} | Всего пар: {len(all_pairs)} | Супер-близнецов (corr >= {args.min_corr}): {len(super_pairs)}\n')
    report_lines.append(f'## Топ-{args.top_n} пар по корреляции\n')
    for i, p in enumerate(all_pairs[:args.top_n], 1):
        report_lines.append(f"{i}. {p['classification']} | corr={p['correlation']:.4f} | lag={p['lag']} | overlap={p['overlap']}")
        report_lines.append(f"   [{p['token1_ticker']}] ID:{p['token1_id']} <-> [{p['token2_ticker']}] ID:{p['token2_id']}  ({p['session']})\n")
    report_lines.append(f'## Топ-{args.top_n} токенов-хабов\n')
    for i, (tid, cnt) in enumerate(top_tokens, 1):
        report_lines.append(f"{i}. ID:{tid}  связей: {cnt}\n")
    report_lines.append(f'## Пары, повторяющиеся в нескольких сессиях\n')
    for (id1, id2), sessions in recurring_pairs.items():
        report_lines.append(f"- ID:{id1} <-> ID:{id2}  (сессий: {len(sessions)})\n")

    out_path = data_path / 'super_twins_report.md'
    out_path.write_text('\n'.join(report_lines), encoding='utf-8')
    print(f'\nПодробный отчёт сохранён в {out_path}')

if __name__ == '__main__':
    main()