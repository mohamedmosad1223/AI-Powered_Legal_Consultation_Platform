import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    def __init__(self):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key or api_key == "your_deepseek_api_key_here":
            print("WARNING: DEEPSEEK_API_KEY not found or not set in environment variables.")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )

        # DeepSeek model — deepseek-chat is the flagship model (DeepSeek-V3)
        self.model = "deepseek-chat"

    def generate_response(self, query: str, context_docs: list[dict]) -> str:
        """
        Generates an answer based on the retrieved context using DeepSeek.
        """
        if not self.client:
            return "عذراً، لم يتم إعداد مفتاح API الخاص بـ DeepSeek."

        # Prepare context string
        context_str = "المعلومات القانونية المتاحة:\n\n"
        for i, doc in enumerate(context_docs, 1):
            source = doc.get('source', 'مجهول')
            text = doc.get('text', '')
            context_str += f"[{i}] المصدر: {source}\nالنص:\n{text}\n\n"

        system_prompt = (
            "أنت مستشار قانوني أردني خبير وذكي. "
            "مهمتك هي الإجابة على أسئلة المستخدم القانونية بناءً على 'المعلومات القانونية المتاحة' فقط. "
            "إذا لم تجد الإجابة في المعلومات المتاحة، اعتذر بوضوح وقل أن المعلومات المتاحة غير كافية للإجابة. "
            "لا تقم بتأليف أي قوانين من خارج السياق. "
            "استخدم لغة عربية رسمية وواضحة، واذكر أرقام المواد أو أسماء الأحكام التي اعتمدت عليها في إجابتك. "
            "اجعل إجابتك منظمة في نقاط إن أمكن لتسهيل القراءة."
        )

        user_message = (
            f"{context_str}\n"
            f"بناءً على المعلومات السابقة، يرجى الإجابة على السؤال التالي:\n\n"
            f"السؤال: {query}"
        )

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ],
                model=self.model,
                temperature=0.3,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            return f"حدث خطأ أثناء التواصل مع نموذج الذكاء الاصطناعي: {str(e)}"

    def generate_rag_response(self, query: str, context_docs: list[dict], judgments: list[dict]) -> dict:
        """
        Generates an answer based on retrieved context and evaluates the relevance of judgments
        returning a JSON object with the answer and judgments evaluations.
        Uses DeepSeek with JSON mode.
        """
        if not self.client:
            return {
                "answer": "عذراً، لم يتم إعداد مفتاح API الخاص بـ DeepSeek.",
                "judgments_relevance": []
            }

        # Prepare context string
        context_str = "القوانين والمواد المتاحة:\n\n"
        for i, doc in enumerate(context_docs, 1):
            source = doc.get('source', 'مجهول')
            text = doc.get('text', '')
            context_str += f"[{i}] المصدر: {source}\nالنص:\n{text}\n\n"

        # Prepare judgments string
        judgments_str = "الأحكام القضائية المقترحة للمراجعة:\n\n"
        for i, j in enumerate(judgments, 1):
            judgments_str += (
                f"=== حكم قضائي رقم {i} ===\n"
                f"معرف الحكم (ruling_id): J{i}\n"
                f"الاسم الفعلي للحكم: {j.get('ruling_id', '')}\n"
                f"رقم القضية: {j.get('case_number', '')}\n"
                f"المحكمة: {j.get('court', '')}\n"
                f"تاريخ الحكم: {j.get('date', 'غير متوفر')}\n"
                f"الموضوع: {j.get('subject', '')}\n"
                f"النتيجة: {j.get('outcome', '')}\n"
                f"النصوص المستند إليها من الحكم (citation_text):\n{j.get('citation_text', '')}\n"
                f"النص الكامل للحكم (مقطع طويل):\n{j.get('full_text', '')[:3000]}\n\n"
            )

        system_prompt = (
            "أنت مستشار قانوني أردني خبير وذكي. "
            "مهمتك هي الإجابة على أسئلة المستخدم القانونية بناءً على القوانين والمواد المتاحة، وتقييم علاقة الأحكام القضائية المقترحة بسؤال المستخدم.\n\n"
            "يجب عليك إرجاع الإجابة بتنسيق JSON صالح يحتوي بدقة على المفاتيح التالية باللغة العربية:\n"
            "{\n"
            "  \"answer\": \"اكتب هنا نص الإجابة القانونية مباشرة بصيغة Markdown باللغة العربية. ابدأ فوراً بشرح وتفصيل المواد القانونية وإجابة سؤال المستخدم. ثم، أرفق قسماً خاصاً في النهاية تحت عنوان '### ⚖️ الأحكام القضائية المرتبطة وسياقها في القضية:' تشرح فيه الأحكام القضائية المرتبطة ذات الصلة المباشرة والقوية بالسؤال فقط بلغة مبسطة للغاية تناسب شخصاً عادياً (ما هي المشكلة؟ ماذا قررت المحكمة؟ وكيف ينطبق هذا على سؤال المستخدم؟)، مع ذكر رقم ومحكمة وتاريخ كل حكم (إذا كان التاريخ غير متوفر، اكتب 'غير متوفر' بدلاً من الأصفار 00-00-0000). تحذير هام: لا تذكر أو تشير إلى أي حكم قضائي غير مرتبط بسؤال المستخدم نهائياً في نص الإجابة ولا تكتب عنه 'لم يتم توفير تفاصيل كافية' بل تجاهله تماماً كأنه لم يكن موجوداً. ولا تكرر نصوص التوجيهات أو العناوين الإرشادية مثل '1. شرح تفصيلي...' بل اكتب محتوى الإجابة مباشرة. تنبيه: يرجى هروب (escape) كل الأسطر الجديدة وعلامات التبويب في النص لتصبح \\n و \\t بدلاً من الأسطر الجديدة الحقيقية (raw control characters) في حقل answer ليكون كائن JSON صالحاً تماماً.\",\n"
            "  \"judgments_relevance\": [\n"
            "    {\n"
            "      \"ruling_id\": \"معرف الحكم الفريد (ruling_id) المذكور في المدخلات بالضبط وبنفس الأحرف والأرقام والرموز دون تغيير أو اختصار (مثل: J1 or J2)\",\n"
            "      \"is_relevant\": true_or_false,\n"
            "      \"relevance_explanation\": \"شرح مبسط جداً وخالٍ من التعقيد القانوني (يناسب شخصاً عادياً) يوضح المشكلة الأساسية في القضية، وقرار المحكمة، وكيف ينطبق هذا القرار على حالة المستخدم وسؤاله.\"\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "تأكد من إرجاع كائن JSON صالح فقط ولا تضف أي نصوص قبله أو بعده."
        )

        user_message = (
            f"{context_str}\n\n"
            f"{judgments_str}\n\n"
            f"بناءً على المعلومات والأحكام السابقة، يرجى الإجابة على السؤال وتقييم علاقة كل حكم بالسؤال.\n\n"
            f"السؤال: {query}"
        )

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ],
                model=self.model,
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            result_text = chat_completion.choices[0].message.content
            # Try parsing with strict=False to allow unescaped newlines/control characters
            return json.loads(result_text, strict=False)
        except Exception as e:
            return {
                "answer": f"حدث خطأ أثناء معالجة الإجابة الذكية: {str(e)}",
                "judgments_relevance": []
            }
