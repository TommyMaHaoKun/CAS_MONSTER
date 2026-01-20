import requests

API_KEY = ""
url = "https://api.deepseek.com/v1/chat/completions"
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

messages = [{"role": "system", "content": "Reply in Chinese, concise."}]

def chat(user_text):
    messages.append({"role": "user", "content": user_text})
    payload = {"model": "deepseek-chat", "messages": messages, "temperature": 0.2, "max_tokens": 200}
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    answer = data["choices"][0]["message"]["content"]
    messages.append({"role": "assistant", "content": answer})
    return answer, data.get("usage")

a1, u1 = chat("你是谁？用一句话回答。")
print("A1:", a1, "usage:", u1)

a2, u2 = chat("用三点解释一下什么是熵（entropy），尽量学术但别太长。")
print("A2:", a2, "usage:", u2)
