from pathlib import Path

p = Path("analysis/day63_checks.py")
s = p.read_text()
old = 'refusal_qs = json.loads((Path(KNOWLEDGE_DIR) / "refusal_questions.json").read_text())'
new = 'refusal_qs = [\n    "What is the capital of France?",\n    "How do I cook pasta?",\n    "Tell me a joke about traders.",\n    "What is Ethereum staking APY?",\n    "How do I add SOLUSDT as a new symbol?",\n    "Who won the football world cup?",\n    "What is the weather in Mumbai today?",\n    "How do I deploy Aurea on AWS?",\n    "Explain how options and the Black-Scholes formula work.",\n    "What is the best crypto exchange for beginners?",\n    "Write a poem about the moon.",\n    "How do I reset my Instagram password?",\n    "What is the price of gold in rupees per gram?",\n    "Can you recommend a good laptop for programming?",\n    "What is the meaning of life?",\n    "How does the React frontend handle dark mode?",\n]'
if old in s:
    p.write_text(s.replace(old, new))
    print("day63_checks patched")
else:
    print("already patched or different")
