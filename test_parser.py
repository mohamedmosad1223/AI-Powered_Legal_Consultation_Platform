import sys
sys.stdout.reconfigure(encoding='utf-8')
from src.models.docx_parser import DocxParser

FILE = r'd:\Work\AI-Powered_Legal_Consultation_Platform\data\قانون رقم 34 لسنة 2014 (قانون ضريبة الدخل لسنة 2014) وتعديلاته النسخة كما في 01-01-2015.docx'
data = DocxParser.parse_law(FILE)

# ── Test Article 59 (had para+item bug)
art59 = next(a for a in data['articles'] if a['number'] == 59)
print('=== مادة 59 ===')
for p in art59['paragraphs']:
    items = [i['number'] for i in p['items']]
    print(f"  فقرة [{p['letter']}]  البنود: {items}")
    print(f"    نص: {p['text'][:60]}")

# ── Test Article 9 (another para+item case)
art9 = next(a for a in data['articles'] if a['number'] == 9)
print()
print('=== مادة 9 ===')
for p in art9['paragraphs']:
    items = [i['number'] for i in p['items']]
    print(f"  فقرة [{p['letter']}]  البنود: {items}")

# ── Overall stats
total_paras = sum(len(a['paragraphs']) for a in data['articles'])
total_items = sum(len(p['items']) for a in data['articles'] for p in a['paragraphs'])
عام_count   = sum(1 for a in data['articles'] for p in a['paragraphs'] if p['letter'] == 'عام')
print()
print(f"إجمالي المواد:   {len(data['articles'])}")
print(f"إجمالي الفقرات: {total_paras}  (منها 'عام': {عام_count})")
print(f"إجمالي البنود:  {total_items}")
