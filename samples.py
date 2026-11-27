"""Read the bundled demo files using paths relative to the app, not the terminal."""
from pathlib import Path


def load_sample_files():
    root = Path(__file__).resolve().parent
    spreadsheets = [
        root / 'sample_hr_dataset_100_employees.xlsx',
        root / 'sample_hr_performance_50_employees.xlsx',
    ]
    policy = root / 'employee_promotion_test_policy.pdf'
    # Support the original generated-policy location as well as the project root.
    if not policy.is_file():
        policy = root / 'output' / 'pdf' / 'employee_promotion_test_policy.pdf'
    files = spreadsheets + [policy]
    missing = [path.name for path in files if not path.is_file()]
    if missing:
        raise ValueError('Sample files are missing: ' + ', '.join(missing))
    return ([(path.name, path.read_bytes()) for path in spreadsheets],
            [(policy.name, policy.read_bytes())])


def combine_files(samples, uploads):
    """Keep uploads available alongside samples; skip exact duplicate files."""
    combined = []
    seen = set()
    for name, content in list(samples) + list(uploads):
        identity = (name, content)
        if identity not in seen:
            combined.append((name, content))
            seen.add(identity)
    return combined
