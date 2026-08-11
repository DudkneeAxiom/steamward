#!/usr/bin/env python3
"""Write assets/models/manifest.json by scanning the exported GLB files.

The browser cannot list a directory, so the manifest is the contract between
the Blender kits and the runtime asset library.
"""

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MODELS = os.path.join(ROOT, 'assets', 'models')


# Bootstrap fallbacks load first so a dedicated kit's asset of the same name
# always wins.
PRIORITY = ['scenery', 'nature', 'settlement', 'industrial', 'military', 'units']


def order_key(name):
    return (PRIORITY.index(name) if name in PRIORITY else len(PRIORITY), name)


def main():
    categories = {}
    total = 0
    for entry in sorted(os.listdir(MODELS), key=order_key):
        d = os.path.join(MODELS, entry)
        if not os.path.isdir(d):
            continue
        names = sorted(f[:-4] for f in os.listdir(d) if f.endswith('.glb'))
        if names:
            categories[entry] = names
            total += len(names)
    manifest = {'categories': categories}
    with open(os.path.join(MODELS, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=1)
    print(f'manifest: {total} assets across {len(categories)} categories')
    for c, n in categories.items():
        print(f'  {c}: {len(n)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
