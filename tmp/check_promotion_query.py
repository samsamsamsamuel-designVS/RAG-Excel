import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import load_settings
from data_store import DataStore
from documents import DocumentStore
from rag import answer_question
settings = load_settings()
docs = DocumentStore(settings)
pdf = Path('output/pdf/employee_promotion_test_policy.pdf')
docs.load([(pdf.name, pdf.read_bytes())])
store = DataStore(settings)
try:
    store.load([('synthetic_performance.csv', b'Employee ID,Full Name,FY2024 Grade,FY2025 Grade,FY2026 Grade\nE1,Test One,C,B,B\nE2,Test Two,C,A,B\nE3,Test Three,B,B,C\nE4,Test Four,A,B,\n')])
    result = answer_question('Using the promotion policy, return only employees shortlisted for promotion. Include Employee ID, Full Name, both required grades, Promotion Status, and Reason.', [], store, settings, docs)
    frame = result.get('data')
    if frame is None:
        print('Check returned a clarification rather than results.')
        raise SystemExit(1)
    data = frame.to_json(orient='records')
    assert len(frame) == 2 and 'E1' in data and 'E2' in data and 'E3' not in data and 'E4' not in data
    print('Live promotion check passed: complete policy query executed and the two expected employees were shortlisted.')
except Exception as error:
    print('Check failed with:', type(error).__name__)
    raise SystemExit(1)
finally:
    store.close()
