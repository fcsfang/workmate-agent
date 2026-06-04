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
        self.timeout = timeout
        
        #创建openai客户端
        self.client = OpenAI(api_key=self.apiKey, base_url=self.baseUrl, timeout=self.timeout)
        

    def invoke(self, prompt):
        response = self.client.chat.completions.create(
            model = self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    



if __name__ == "__main__":
    llmclient = LLMClient()
    prompt = "我使用API调用你，你会有记忆能力吗？"
    respose = llmclient.invoke(prompt)
    print(respose)