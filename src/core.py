from .LLMClient import LLMClient



if __name__ == "__main__":
    llmclient = LLMClient()
    prompt = """我开着思源笔记，上面记录着我昨天晚上给今天写的计划，今天最重要的事情就是锻炼自己的注意力。首先第一个任务是找 10 个大模型相关实习岗位，复制 JD 到文档里。把 JD 高频词圈出来，比如 RAG、Agent、LangChain、向量数据库、PyTorch、微调、评测、后端、Python。"""

    respose = llmclient.invoke(prompt=prompt)

    