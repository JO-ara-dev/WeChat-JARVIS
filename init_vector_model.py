import os
from sentence_transformers import SentenceTransformer

print("💡 提示：如果下载缓慢，请在终端执行: $env:HF_ENDPOINT='https://hf-mirror.com'")

model_name = "paraphrase-multilingual-MiniLM-L12-v2"
print(f"正在预下载向量模型: {model_name}...")
model = SentenceTransformer(model_name)
print("✅ 模型已就绪！")
