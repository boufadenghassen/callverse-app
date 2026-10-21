"""A third batch of hand-labelled calls: the final TEST. Written before the detectors were improved on the failures of batch 2 and not looked at
until that work was done, so the score on it is the honest one. New wording again; the same kinds of situations.
"""
from quality_eval_cases import BILL, case

T = "test"
CASES3 = [
    # ---- promises --------------------------------------------------------------------------------------
    case("V01", ["promise_before_check"], [], BILL, "A: Hello. You can count on getting that money returned to your account today.", split=T),
    case("V02", ["promise_before_check"], [], BILL, "A: Hello. I'm sending the funds back to your card as of now.", split=T),
    case("V03", ["promise_before_check"], [], BILL, "A: Hello. Sure thing, I'll refund it all immediately.", split=T),
    case("V04", ["promise_before_check"], [], BILL, "A: Hello. Don't worry, that amount will be in your pocket again by this evening.", split=T),
    case("V05", [], ["promise_before_check"], BILL, "A: Hello. I wish I could say you'd get it back, but I can't confirm anything yet.", split=T),
    case("V06", [], ["promise_before_check"], BILL, "A: Hello. A refund is subject to approval, so I'll ask for it now.", split=T),
    case("V07", [], ["promise_before_check"], BILL, "A: Hello. Let me confirm with the policy desk, then I'll tell you the outcome.", split=T),
    case("V08", [], ["promise_before_check"], BILL, "A: Hello. I'm reviewing the conditions for refunds.", "C60: Okay.", "A: The conditions are met, you will be refunded today.", split=T),
    # ---- empathy ---------------------------------------------------------------------------------------
    case("V09", [], ["no_empathy"], "C20: I'm absolutely livid about this charge.", "A: Hello. That must be really upsetting, I'm sorry you had to chase this.", split=T),
    case("V10", [], ["no_empathy"], "C25: Your company keeps ripping me off!", "A: Hello. I totally get why you're angry.", split=T),
    case("V11", ["no_empathy"], [], "C20: I'm absolutely livid about this charge.", "A: Hello. Tell me the amount and the date.", split=T),
    case("V12", ["no_empathy"], [], "C25: Your company keeps ripping me off!", "A: Hello. Postcode?", split=T),
    # ---- follow-up -------------------------------------------------------------------------------------
    case("V13", [], ["no_follow_up"], BILL, "A: Hello. I'll write to you today with the details of what was decided.", split=T),
    case("V14", [], ["no_follow_up"], BILL, "A: Hello. A case file is open now and its number will reach you by SMS.", split=T),
    case("V15", [], ["no_follow_up"], BILL, "A: Hello. I'll personally ring you again next week to check.", split=T),
    case("V16", ["no_follow_up"], [], BILL, "A: Hello. Okay then.", split=T),
    case("V17", ["no_follow_up"], [], BILL, "A: Hello. Anyway, good luck.", split=T),
    # ---- greeting and closing --------------------------------------------------------------------------
    case("V18", [], ["no_greeting"], BILL, "A: Good day, Orqestra customer service, how may I assist?", split=T),
    case("V19", [], ["no_greeting"], BILL, "A: Hi there, thanks for calling in.", split=T),
    case("V20", ["no_greeting"], [], BILL, "A: Yes?", split=T),
    case("V21", ["no_greeting"], [], BILL, "A: Talk to me.", split=T),
    case("V22", [], ["no_closing"], BILL, "A: Hello. It's fixed. Can I help with anything else?", split=T),
    case("V23", [], ["no_closing"], BILL, "A: Hello. It's fixed. Thanks for calling us, have a good one.", split=T),
    case("V24", ["no_closing"], [], BILL, "A: Hello. It's fixed.", split=T),
    # ---- identity --------------------------------------------------------------------------------------
    case("V25", [], ["no_identity_check"], BILL, "A: Hello. For security reasons, may I have your name and date of birth?", "C60: Yasmine, 3 May 1990.", "A: Thanks. I will credit the second payment.", split=T),
    case("V26", [], ["no_identity_check"], "C60: My SIM is broken.", "A: Hello. Could you verify your identity by giving me your ID number?", "C60: 12345678.", "A: Thank you, I'm replacing your SIM now.", split=T),
    case("V27", ["no_identity_check"], [], "C60: My phone was stolen.", "A: Hello. I'm blocking the line immediately.", split=T),
    # ---- asking to repeat ------------------------------------------------------------------------------
    case("V28", ["ask_repeat"], [], BILL, "A: Hello. I missed the beginning, could you tell me everything once again?", split=T),
    case("V29", ["ask_repeat"], [], BILL, "A: Hello. From the top, please: what exactly went wrong?", split=T),
    case("V30", [], ["ask_repeat"], BILL, "A: Hello. I read your notes, so no need to explain again.", split=T),
    case("V31", [], ["ask_repeat"], BILL, "A: Hello. Which date was the second payment taken?", split=T),
    # ---- transfers -------------------------------------------------------------------------------------
    case("V32", ["transfer"], [], BILL, "A: Hello. I'm forwarding you to the roaming specialists.", split=T),
    case("V33", ["transfer"], [], BILL, "A: Hello. Your call will be moved to a colleague in the technical department.", split=T),
    case("V34", [], ["transfer"], BILL, "A: Hello. I'm going to stay with you until this is solved, no handover needed.", split=T),
    # ---- guarantees ------------------------------------------------------------------------------------
    case("V35", ["overpromise"], [], BILL, "A: Hello. Rest assured, it can't ever happen again.", split=T),
    case("V36", ["overpromise"], [], BILL, "A: Hello. I guarantee you'll be fully satisfied.", split=T),
    case("V37", [], ["overpromise"], BILL, "A: Hello. I hope this solves it, and I'll check on it next week.", split=T),
    # ---- facts -----------------------------------------------------------------------------------------
    case("V38", ["wrong_fact"], [], BILL, "A: Hello. We reply to disputes in 48 hours.", split=T),
    case("V39", ["wrong_fact"], [], "C50: I changed my plan.", "A: Hello. Plan changes are applied instantly.", split=T),
    case("V40", [], ["wrong_fact"], BILL, "A: Hello. The dispute gets an answer within five business days.", split=T),
    case("V41", [], ["wrong_fact"], "C50: I lost my SIM.", "A: Hello. A new SIM keeps your existing number.", split=T),
    # ---- amounts, retention, grounding, jargon ---------------------------------------------------------
    case("V42", ["refund_over_limit"], [], BILL, "A: Hello. I'm crediting 250 TND to your account.", split=T),
    case("V43", ["refund_over_limit"], [], BILL, "A: Hello. We'll refund 100 dinars.", split=T),
    case("V44", [], ["refund_over_limit"], BILL, "A: Hello. I'll refund 20 TND.", split=T),
    case("V45", [], ["refund_over_limit"], BILL, "A: Hello. I'll refund 100 TND once the supervisor approves.", split=T),
    case("V46", ["no_retention_offer"], [], "C50: Cancel my line please.", "A: Hello. Sure, I'm terminating your contract right now.", split=T),
    case("V47", [], ["no_retention_offer"], "C50: Cancel my line please.", "A: Hello. Could I show you a cheaper plan before I cancel anything?", split=T),
    case("V48", ["no_grounded_answer"], [], BILL, "A: Hello. Do you like football?", split=T),
    case("V49", [], ["no_grounded_answer"], "C50: My roaming bundle did not work abroad.", "A: Hello. Let me check whether the roaming bundle was switched on for the country you visited.", split=T),
    case("V50", ["jargon"], [], "C50: My data is slow.", "A: Hello. It's a throttling issue on your MNP profile and the IVR.", split=T),
    case("V51", [], ["jargon"], "C50: My data is slow.", "A: Hello. Your phone is on the slow network, switching to Wi-Fi helps.", split=T),
]
