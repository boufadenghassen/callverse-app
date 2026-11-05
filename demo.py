"""Boucle de test avec un Advisor factice.
  python demo.py --backend mock
  python demo.py --backend ollama --model qwen2.5:7b --persona derja_m --difficulty 4
"""
import argparse, os, sys
sys.path.insert(0, "src")
ap = argparse.ArgumentParser()
ap.add_argument("--backend", choices=["mock", "ollama", "anthropic"])
ap.add_argument("--model")
ap.add_argument("--persona", default="fr_m")
ap.add_argument("--difficulty", type=int, default=3)
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()
if a.backend:
    os.environ["LLM_BACKEND"] = a.backend
    os.environ.pop("EVAL_BACKEND", None)
if a.model:
    os.environ["LLM_MODEL"] = a.model
    os.environ.pop("EVAL_MODEL", None)

from customer_simulator import CustomerSimulatorAgent, Scenario, make_llm

# Advisor factice : réponses volontairement vagues, pour voir la frustration monter
FAKE_ADVISOR = [
    "Veuillez patienter, je vérifie votre dossier.",
    "Pouvez-vous me redonner votre numéro de ligne ?",
    "Je comprends, veuillez patienter encore un instant.",
    "Je vais transférer votre appel.",
]

agent = CustomerSimulatorAgent(make_llm("LLM"), make_llm("EVAL"))
msg = agent.start(Scenario(persona_id=a.persona, difficulty=a.difficulty, seed=a.seed))
print(f"Profil : {agent.profile.name}, {agent.profile.age} ans, intentions={agent.profile.intents}\n")
i = 0
while True:
    e = msg.emotion
    print(f"[Client t{msg.turn}] {msg.text}")
    print(f"   émotion: patience={e.patience:.2f} frustration={e.frustration:.2f} "
          f"confiance={e.trust:.2f} | {msg.metadata['mood']} | action={msg.action}")
    if msg.action != "continue":
        break
    adv = FAKE_ADVISOR[min(i, len(FAKE_ADVISOR) - 1)]
    print(f"[Advisor]   {adv}")
    msg = agent.reply(adv, wait_seconds=45)
    i += 1
