import sys
import os

# Reconfigure stdout for Arabic characters on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.controllers.rag_controller import RAGController

def test_query(question: str):
    print("\n" + "="*80)
    print(f"🎯 السؤال التجريبي: {question}")
    print("="*80)
    
    try:
        controller = RAGController()
        result = controller.query(question)
        
        print("\n🔍 --- نتائج الاسترجاع والمطابقة (Retrieval & Sources) ---")
        sources = result.get("sources", [])
        if not sources:
            print("❌ لم يتم استرجاع أي مصادر!")
        for idx, src in enumerate(sources, 1):
            print(f"\n[{idx}] نوع النود: {src.get('type')} | معرف العنصر: {src.get('id')}")
            print(f"    العنوان المعروض: {src.get('label')}")
            print(f"    نسبة المطابقة الدلالية (Score): {src.get('score', 0)*100:.2f}%")
            
            # Print a snippet of the text
            text_snippet = src.get('text', '').replace('\n', ' ')
            if len(text_snippet) > 120:
                text_snippet = text_snippet[:120] + "..."
            print(f"    مقتطف النص: {text_snippet}")
        
        print("\n⚖ --- الأحكام القضائية المرتبطة التي تم جلبها من Neo4j ---")
        judgments = result.get("judgments", [])
        if not judgments:
            print("❌ لم يتم العثور على أحكام قضائية مرتبطة بالفقرة/المادة المحددة!")
        for idx, j in enumerate(judgments, 1):
            print(f"\n[{idx}] حكم رقم: {j.get('case_number')} | المحكمة: {j.get('court')} | التاريخ: {j.get('date')}")
            print(f"    النتيجة: {j.get('outcome')}")
            print(f"    الموضوع: {j.get('subject')}")
            if "relevance_explanation" in j:
                print(f"    💡 التقييم والربط (Relevance): {j['relevance_explanation']}")
        
        print("\n🤖 --- الإجابة النهائية المصاغة من الذكاء الاصطناعي (LLM Answer) ---")
        print(result.get("answer", "لا توجد إجابة!"))
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"❌ حدث خطأ غير متوقع أثناء معالجة السؤال: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_queries = [
        "هل أجور التغليف أو مصاريف التعبئة والتغليف التي تدفعها شركة (شخص اعتباري) لشركة أخرى تخضع لاقتطاع ضريبة دخل بنسبة 5% من المصدر؟ وهل هناك حكم قضائي بخصوص هذا الموضوع؟",
        "هل يحق لوزير المالية أو مدير الضريبة منع محاسب قانوني من مراجعة الدائرة أو عدم قبول الحسابات التي يقدمها؟ وما هي الشروط؟",
        "كم تبلغ قيمة الإعفاءات الشخصية والعائلية المكفولة للشخص الطبيعي المقيم وزوجته وأولاده في القانون المعدل؟",
        "هل تخضع أتعاب الطبيب أو المحامي لاقتطاع ضريبة بنسبة 5% من المصدر؟ وهل هناك حكم قضائي بخصوص هذا الموضوع؟",
        "ما هي ضريبة التكافل الاجتماعي المفروضة بموجب القانون؟"
    ]
    
    print("🚀 بدء تشغيل اختبار خط أنابيب الـ RAG المطور...")
    
    for q in test_queries:
        test_query(q)
