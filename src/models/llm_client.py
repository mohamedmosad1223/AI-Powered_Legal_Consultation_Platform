import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("WARNING: GROQ_API_KEY not found in environment variables.")
            self.client = None
        else:
            self.client = Groq(api_key=api_key)
            
        # Using the latest Groq model
        self.model = "llama-3.3-70b-versatile"

    def generate_response(self, query: str, context_docs: list[dict]) -> str:
        """
        Generates an answer based on the retrieved context using Groq.
        """
        if not self.client:
            return "عذراً، لم يتم إعداد مفتاح API الخاص بـ Groq."

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
                temperature=0.3, # Low temperature for more factual responses
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            return f"حدث خطأ أثناء التواصل مع نموذج الذكاء الاصطناعي: {str(e)}"
