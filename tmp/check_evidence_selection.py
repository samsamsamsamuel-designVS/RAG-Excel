from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openai import OpenAI
from config import load_settings
from documents import DocumentStore
from rag import select_display_evidence
settings = load_settings()
docs = DocumentStore(settings)
p = Path('output/pdf/employee_promotion_test_policy.pdf')
docs.load([(p.name, p.read_bytes())])
knowledge = docs.retrieve('Who qualifies for promotion?', [])
with OpenAI(api_key=settings.api_key, timeout=settings.api_timeout, max_retries=0) as client:
    selected = select_display_evidence(client, settings, 'Do two consecutive Grade B ratings qualify for promotion shortlisting?', 'Yes, B or above in both FY2025 and FY2026 qualifies under R1.', knowledge)
    assert selected and len(selected) < len(knowledge['passages']), 'Expected a relevant subset'
    assert any('R1' in p['text'] for p in selected), 'Expected the policy rule'
    unrelated = select_display_evidence(client, settings, 'What is the capital of France?', 'Paris is the capital of France.', knowledge)
    assert unrelated == [], 'Unrelated question should have no evidence'
    print('Live selection passed: relevant policy paragraphs only; unrelated question returned no evidence.')
    print('Displayed paragraphs:', len(selected), 'of', len(knowledge['passages']))
