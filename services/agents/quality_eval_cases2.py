"""A second, harder batch of hand-labelled calls. It was written as TEST calls and measured once (first score: F1 81 %, keyword rules alone 75 %),
nothing having been tuned on it. Its failures were then used to improve the detectors in general ways, so from that moment these calls are DEVELOPMENT
calls and the final test is batch 3 (quality_eval_cases3.py).

They try to break the analyst: paraphrases the prototypes do not contain, negations, conditionals, restating instead of repeating, and wording the keyword
lists never saw.
"""
from quality_eval_cases import BILL, case

T = "dev"
CASES2 = [
    # ---- promises said in unusual words, and things that sound like promises but are not --------------
    case("S01", ["promise_before_check"], [], BILL, "A: Hello. Right, your money will be back on your card by tonight.", split=T),
    case("S02", ["promise_before_check"], [], BILL, "A: Hello. I'll make sure you get that amount back today.", split=T),
    case("S03", ["promise_before_check"], [], BILL, "A: Hello. That duplicate payment is going back to you right now.", split=T),
    case("S04", ["promise_before_check"], [], BILL, "A: Hello. No worries, I'm reversing the second charge as we speak.", split=T),
    case("S05", [], ["promise_before_check"], BILL, "A: Hello. I can't tell you yet whether you will be refunded.", split=T),
    case("S06", [], ["promise_before_check"], BILL, "A: Hello. If the check passes, the money will be returned to you.", split=T),
    case("S07", [], ["promise_before_check"], BILL, "A: Hello. I'd love to refund you but the rules decide, give me a moment to read them.", split=T),
    case("S08", [], ["promise_before_check"], BILL, "A: Hello. Let me read the refund rules.", "C60: Ok.", "A: The rules allow it, so your refund is on its way.", split=T),
    # ---- empathy ---------------------------------------------------------------------------------------
    case("S09", [], ["no_empathy"], "C20: This is unacceptable, I am furious!", "A: Hello. I hear you, that is a lot to deal with.", split=T),
    case("S10", [], ["no_empathy"], "C25: I have been waiting forever, this is ridiculous.", "A: Hello. How annoying for you, my apologies.", split=T),
    case("S11", ["no_empathy"], [], "C20: This is unacceptable, I am furious!", "A: Hello. Okay. Account number?", split=T),
    case("S12", ["no_empathy"], [], "C25: I have been waiting forever, this is ridiculous.", "A: Hello. Right. Give me your invoice reference.", split=T),
    # ---- follow-up -------------------------------------------------------------------------------------
    case("S13", [], ["no_follow_up"], BILL, "A: Hello. I'll text you the ticket reference in a minute.", split=T),
    case("S14", [], ["no_follow_up"], BILL, "A: Hello. Expect an email from us tonight confirming all this.", split=T),
    case("S15", [], ["no_follow_up"], BILL, "A: Hello. If nothing changes, call me tomorrow on this case and I will check it myself.", split=T),
    case("S16", ["no_follow_up"], [], BILL, "A: Hello. There you go.", split=T),
    case("S17", ["no_follow_up"], [], BILL, "A: Hello. That's sorted. Bye.", split=T),
    # ---- greeting and closing --------------------------------------------------------------------------
    case("S18", [], ["no_greeting"], BILL, "A: Hey, Orqestra support here, what can I do for you?", split=T),
    case("S19", [], ["no_greeting"], BILL, "A: Good evening, and thanks for holding.", split=T),
    case("S20", ["no_greeting"], [], BILL, "A: Right. Invoice number?", split=T),
    case("S21", [], ["no_closing"], BILL, "A: Hello. Done. Anything more I can do for you?", split=T),
    case("S22", [], ["no_closing"], BILL, "A: Hello. Done. Take care, and thanks for your patience.", split=T),
    case("S23", ["no_closing"], [], BILL, "A: Hello. Done. Okay, bye.", split=T),
    # ---- identity --------------------------------------------------------------------------------------
    case("S24", [], ["no_identity_check"], BILL, "A: Hello. To protect your account I need to confirm who you are first. What is your date of birth?", "C60: 3 May 1990.", "A: Thanks, I will refund the duplicate.", split=T),
    case("S25", [], ["no_identity_check"], BILL, "A: Hello. Before I touch anything: your full name and the address on file, please.", "C60: Yasmine Toumi, Avenue Habib 5.", "A: Perfect, I'll credit the second payment.", split=T),
    case("S26", ["no_identity_check"], [], "C60: I want to leave.", "A: Hello. No problem, I'm cancelling it for you now.", split=T),
    # ---- asking to repeat versus restating -------------------------------------------------------------
    case("S27", ["ask_repeat"], [], BILL, "A: Hello. Sorry, remind me what the issue was?", split=T),
    case("S28", ["ask_repeat"], [], BILL, "A: Hello. Would you mind running through everything once more?", split=T),
    case("S29", [], ["ask_repeat"], BILL, "A: Hello. Just to confirm what I heard: two payments on the first of the month.", split=T),
    # ---- transfers -------------------------------------------------------------------------------------
    case("S30", ["transfer"], [], BILL, "A: Hello. I'll hand you over to someone in billing.", split=T),
    case("S31", [], ["transfer"], BILL, "A: Hello. I will keep this myself, I won't transfer you.", split=T),
    case("S32", [], ["transfer"], BILL, "A: Hello. I'm asking a billing colleague a quick question, you stay with me.", split=T),
    # ---- guarantees ------------------------------------------------------------------------------------
    case("S33", ["overpromise"], [], BILL, "A: Hello. This will absolutely never happen again, trust me.", split=T),
    case("S34", ["overpromise"], [], BILL, "A: Hello. It is a hundred percent resolved.", split=T),
    case("S35", ["overpromise"], [], BILL, "A: Hello. You can be sure nothing like this will occur again.", split=T),
    # ---- facts -----------------------------------------------------------------------------------------
    case("S36", ["wrong_fact"], [], BILL, "A: Hello. Disputes are settled in three days.", split=T),
    case("S37", ["wrong_fact"], [], "C50: I changed my plan.", "A: Hello. The plan switch applies right now.", split=T),
    case("S38", ["wrong_fact"], [], "C50: I paid my bill late.", "A: Hello. Your service is back on within the day.", split=T),
    case("S39", [], ["wrong_fact"], BILL, "A: Hello. Disputes are answered within five working days.", split=T),
    # ---- amounts above the limit, retention, grounding -------------------------------------------------
    case("S40", ["refund_over_limit"], [], BILL, "A: Hello. Sure, 60 dinars will be returned to you.", split=T),
    case("S41", ["refund_over_limit"], [], BILL, "A: Hello. I'll give you back 80 TND.", split=T),
    case("S42", ["no_retention_offer"], [], "C50: I want to cancel my subscription.", "A: Hello. No problem, I'm closing your account today.", split=T),
    case("S43", [], ["no_retention_offer"], "C50: I want to cancel my subscription.", "A: Hello. Would a cheaper plan change your mind? If not, I will close it.", split=T),
    case("S44", ["no_grounded_answer"], [], BILL, "A: Hello. Our shop opens at nine tomorrow.", split=T),
]
