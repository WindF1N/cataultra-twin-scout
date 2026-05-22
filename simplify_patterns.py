#!/usr/bin/env python3
import json, shutil
from pathlib import Path

src_dir = Path('private/twin_scout/patterns_by_mode')
dst_dir = Path('private/twin_scout/patterns_crash')
dst_dir.mkdir(exist_ok=True)

with open(src_dir / 'patterns_db.json') as f:
    meta = json.load(f)

best_per_mode = {}
for pid, info in meta.items():
    mode = info['mode']
    if mode not in best_per_mode or info['num_twins'] > best_per_mode[mode]['num_twins']:
        best_per_mode[mode] = {**info, 'id': pid}

new_meta = {}
for mode, info in best_per_mode.items():
    new_id = f"{mode}_CRASH"
    src_npy = src_dir / info['file']
    dst_npy = dst_dir / f"{new_id}.npy"
    shutil.copy(src_npy, dst_npy)
    new_meta[new_id] = {
        'mode': mode,
        'num_twins': info['num_twins'],
        'file': f"{new_id}.npy"
    }
    print(f"{mode}: {info['id']} -> {new_id} ({info['num_twins']} близн.)")

with open(dst_dir / 'patterns_db.json', 'w') as f:
    json.dump(new_meta, f, indent=2)
print(f"\nБаза сохранена в {dst_dir}")