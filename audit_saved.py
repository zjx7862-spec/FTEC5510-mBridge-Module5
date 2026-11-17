"""Fail closed on incomplete pilots and replay every event-time cash state."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
from validation import audit_saved
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        count = audit_saved(args.root)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Audit FAILED: {exc}\n')
    print(f'{count} saved pilot runs reconciled at every event; coverage, manifests and summaries verified.')
