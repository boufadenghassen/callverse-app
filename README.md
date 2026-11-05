# CallVerse — Customer Simulator Agent (agent 1)

Tu es le conseiller, l'IA est le client (français ou anglais). **100 % local, gratuit, sans limite.**

- Le client a une **voix distincte par persona** (Piper via sherpa-onnx) et parle plus vite quand il s'énerve.
- Sa réplique est **jouée phrase par phrase pendant que le LLM l'écrit** (pas d'attente de la réponse complète).
- Ta voix est transcrite localement (Whisper). Avec `--barge-in`, tu peux **lui couper la parole**.
- Le LLM garde tout l'historique et répond selon l'état du client (patience, frustration, confiance, urgence).

## Installation
    python -m venv C:\Users\Sami\callverse-venv
    C:\Users\Sami\callverse-venv\Scripts\activate
    python -m pip install -r requirements.txt -r requirements-voice.txt
    ollama pull qwen2.5:7b
    python download_voices.py              # une fois : ~330 Mo, voix locales

## Lancer
    python chat.py                         # client fr/en aléatoire, mains libres
    python chat.py --barge-in              # + coupure de parole (CASQUE obligatoire)
    python chat.py --lang en --gender F
    python chat.py --persona fr_m --difficulty 4
    python chat.py --manual                # micro avec Entrée
    python chat.py --text                  # clavier seulement
    python chat.py --backend mock --text   # test sans modèle

Arrêt : dire « stop simulation » ou Ctrl+C. Les conversations sont dans transcripts/.

## Voix par persona (data/voices.json)
| Persona | Voix |
|---|---|
| fr_f | fr_FR-siwis-medium |
| fr_m | fr_FR-tom-medium |
| en_f | en_US-amy-medium |
| en_m | en_US-ryan-medium |
Pour changer une voix : modifie `data/voices.json` (autres modèles : releases `tts-models` de k2-fsa/sherpa-onnx)
puis `python download_voices.py`. Les voix « high » et Kokoro sont plus naturelles mais ~1x temps réel sur CPU : trop lent.

## Coupure de parole (--barge-in)
Le micro reste ouvert pendant que le client parle. Si tu parles par-dessus, le son est coupé net, ta phrase est
capturée et le client sait qu'il a été coupé (frustration +). Avec des haut-parleurs, sa propre voix serait captée :
utilise un casque filaire.

## Vitesse
Les lignes [temps] montrent : évaluation, 1er mot du LLM, premier son. Transcription trop imprécise :
`--stt-model small`. Génération lente : `--model qwen2.5:3b`. Synthèse lente : `TTS_THREADS=4`.

## Structure
- data/personas.json (6 personas, dont derja en pause), data/voices.json, data/intents.json
- src/customer_simulator/ : schemas, generator, emotion, prompts, llm, localtts, voice, live, agent, api
- chat.py (appel interactif), demo.py (Advisor factice), download_voices.py
