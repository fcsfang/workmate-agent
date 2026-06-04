from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self,
                 model: str = None, 
                 apiKey: str = None, 
                 baseUrl: str = None, 
                 timeout: int = None):
        self.model = model or os.getenv("LLM_MODEL_ID")
        self.apiKey = apiKey or os.getenv("LLM_API_KEY")
        self.baseUrl = baseUrl or os.getenv("LLM_BASE_URL")
        self.client = OpenAI(=self.model, api_key=self.apiKey, self.baseUrl)
        

    def generate_response(self, prompt):
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()