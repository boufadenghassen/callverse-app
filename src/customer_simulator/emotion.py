"""Moteur d'état émotionnel : règles d'évolution + seuils de comportement."""
from .schemas import EmotionState, AdvisorSignals, Action


def update_emotion(state: EmotionState, s: AdvisorSignals, difficulty: int = 3) -> EmotionState:
    """Fait évoluer l'état après une réponse de l'Advisor.
    `difficulty` (1-5) amplifie les effets négatifs."""
    k = 0.8 + 0.1 * difficulty  # 0.9 .. 1.3
    new = state.model_copy()

    new.frustration += (0.5 - s.relevance) * 0.35 * k
    new.trust += (s.relevance - 0.5) * 0.25
    new.frustration -= (s.empathy - 0.5) * 0.2
    new.trust += (s.empathy - 0.5) * 0.15
    if s.repeated_question:
        new.frustration += 0.15 * k
        new.patience -= 0.12 * k
    if s.wait_seconds > 10:
        new.patience -= min(0.2, s.wait_seconds / 200) * k
        new.frustration += 0.05 * k
    if new.frustration > 0.6:
        new.patience -= 0.05 * k
    if s.resolved:
        new.frustration -= 0.3
        new.trust += 0.2
        new.urgency -= 0.2
    # lissage : la frustration ne peut pas bondir ou chuter d'un coup
    new.frustration = max(state.frustration - 0.3, min(state.frustration + 0.25, new.frustration))
    return new.clamp()


def decide_action(state: EmotionState, resolved: bool = False) -> Action:
    """Seuils qui déclenchent une fin de conversation ou une escalade."""
    if resolved and state.frustration < 0.5:
        return "resolved"
    if state.patience <= 0.05 and state.frustration > 0.4:
        return "hangup"      # plus aucune patience : le client raccroche
    if state.patience < 0.15:
        return "escalate"    # patience épuisée : demande un responsable
    if state.frustration > 0.75 or (state.trust < 0.15 and state.frustration > 0.55):
        return "escalate"
    return "continue"


def mood_label(state: EmotionState) -> str:
    if state.frustration > 0.75:
        return "furieux"
    if state.frustration > 0.5:
        return "très irrité"
    if state.frustration > 0.3:
        return "agacé"
    if state.trust > 0.65:
        return "rassuré"
    return "calme"
