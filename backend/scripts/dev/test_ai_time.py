from app.db.db_store import DBStore
from app.services.ai_service import AIService

store = DBStore()
ai_service = AIService(store=store)

print("--- 1. 已配置的 AI 模型列表 ---")
for pid, p in store.model_providers.items():
    print(f"Provider: {pid}, Name: {p.get('name')}, Model: {p.get('model')}, Enabled: {p.get('enabled')}")

# 找到一个启用的模型进行提问测试
active_provider = None
for pid, p in store.model_providers.items():
    if p.get("enabled") and p.get("secret_ref"):
        active_provider = pid
        break

if active_provider:
    print(f"\n--- 2. 使用启用模型 [{active_provider}] 测试提问: '现在比特币是什么情况？当前几几年几月几日？' ---")
    try:
        res = ai_service.chat(
            provider_id=active_provider,
            messages=[{"role": "user", "content": "现在比特币是什么情况？当前几几年几月几日？"}],
            temperature=0.3,
            max_tokens=500
        )
        print("AI 模型原生回答:")
        print(res.get("content"))
    except Exception as e:
        print("Chat error:", type(e), e)
else:
    print("未找到可用已启用的模型")
