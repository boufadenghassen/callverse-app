"""Hand-labelled calls to measure the quality analyst.

Each case is a short call written in natural words (not the phrase banks of the simulated history) with the rules a careful human would say
fire (`expect`) and the rules that must stay silent (`absent`). Rules not listed in a case are not judged by that case. Turn syntax:
"A: text" is the advisor, "C: text" the customer, "C30: text" the customer with a mood of 30 (0 to 100); without a mood one is guessed from the words.

The cases are split 60 / 40 into `dev` (what the thresholds are tuned on) and `test` (never used for tuning), by the number in the id.
"""
import os



def _turns(lines):
    out = []
    for line in lines:
        head, text = line.split(":", 1)
        who = "advisor" if head[0] == "A" else "customer"
        turn = dict(speaker=who, text=text.strip())
        if who == "customer" and head[1:]:
            turn["mood"] = int(head[1:])
        out.append(turn)
    return out


def case(cid: str, expect: list[str], absent: list[str], *lines: str, split: str | None = None) -> dict:
    n = int(cid[1:])
    return dict(id=cid, split=split or ("dev" if n % 5 in (0, 1, 2) else "test"), expect=expect, absent=absent, turns=_turns(lines))


BILL = "C60: I was charged twice on my September bill."
CASES = [
    # ---- promise before the policy check -------------------------------------------------------------
    case("P01", ["promise_before_check"], [], BILL, "A: Hello, thank you for calling. You'll have your money back today, no problem."),
    case("P02", ["promise_before_check"], [], BILL, "A: Good morning. I'm crediting the full amount to your account right now."),
    case("P03", ["promise_before_check"], [], BILL, "A: Hi there. Sure, I will refund the duplicate straight away."),
    case("P04", ["promise_before_check"], [], BILL, "A: Hello. Done, the refund is on its way to you."),
    case("P05", ["promise_before_check"], [], BILL, "A: Welcome. I promise you'll get everything back."),
    case("P06", ["promise_before_check"], [], BILL, "A: Hello. Absolutely, I'll reimburse you for that."),
    case("P07", ["promise_before_check"], [], BILL, "A: Hello, I will look at the account.", "C60: Thanks.", "A: Right, I'll put the money back on your card today."),
    case("P08", [], ["promise_before_check"], BILL, "A: Hello. Let me check the refund policy first.", "C60: Okay.", "A: Good, I will refund you."),
    case("P09", [], ["promise_before_check"], BILL, "A: Hello. Can you tell me the date of the invoice?"),
    case("P10", [], ["promise_before_check"], BILL, "A: Hello. I'm not able to promise a refund before I review the rules."),
    case("P11", [], ["promise_before_check"], BILL, "A: Hello. A refund may be possible, I need to verify the eligibility rules."),
    case("P12", [], ["promise_before_check"], BILL, "A: Hello. Once it is approved, the refund will show on your next statement."),
    case("P13", [], ["promise_before_check"], BILL, "A: Hello. I need to look at what our procedure says before I confirm anything.", "C60: Fine.", "A: The procedure allows it, so I'll credit you now."),
    # ---- refund above the limit ----------------------------------------------------------------------
    case("R01", ["refund_over_limit"], [], BILL, "A: Hello. I will refund you 120 TND."),
    case("R02", ["refund_over_limit"], [], BILL, "A: Hello. I can credit 200 dinars to your account."),
    case("R03", ["refund_over_limit"], [], BILL, "A: Hello. The refund of 75 TND is processed."),
    case("R04", ["refund_over_limit"], [], BILL, "A: Hello. We'll waive 90 TND for you."),
    case("R05", [], ["refund_over_limit"], BILL, "A: Hello. I will refund 120 TND once my supervisor has approved it."),
    case("R06", [], ["refund_over_limit"], BILL, "A: Hello. I will refund you 30 TND."),
    case("R07", [], ["refund_over_limit"], BILL, "A: Hello. The approval step comes first, then 150 TND can go back to you."),
    case("R08", [], ["refund_over_limit"], BILL, "A: Hello. I see the duplicate charge on your invoice."),
    # ---- identity check ------------------------------------------------------------------------------
    case("I01", ["no_identity_check"], [], BILL, "A: Hello. I'll refund the second payment."),
    case("I02", ["no_identity_check"], [], "C60: My SIM is lost.", "A: Hello. I'm blocking it and sending you a new one."),
    case("I03", ["no_identity_check"], [], "C60: I want to leave.", "A: Hello. Alright, I'll cancel your contract."),
    case("I04", ["no_identity_check"], [], BILL, "A: Hello. I'm activating a credit on your line."),
    case("I05", [], ["no_identity_check"], BILL, "A: Hello. Could you confirm your date of birth so I can verify your identity?", "C60: 3 May 1990.", "A: Thanks. I will refund the second payment."),
    case("I06", [], ["no_identity_check"], BILL, "A: Hello. First I have to make sure who I am speaking with: your full name and address, please.", "C60: Yasmine Toumi, Avenue Habib 5.", "A: Great, I'll credit the duplicate."),
    case("I07", [], ["no_identity_check"], BILL, "A: Hello. I can see the two payments on the invoice."),
    case("I08", [], ["no_identity_check"], BILL, "A: Hello. Can I check your account first?"),
    # ---- retention before cancelling -----------------------------------------------------------------
    case("T01", ["no_retention_offer"], [], "C50: I want to cancel my subscription.", "A: Hello. Okay, I will cancel it for you today."),
    case("T02", ["no_retention_offer"], [], "C50: I'd like to terminate my contract.", "A: Hello. Fine, I'm processing the cancellation now."),
    case("T03", ["no_retention_offer"], [], "C50: Please cancel my line, I'm leaving.", "A: Hello. Understood, I have cancelled your line."),
    case("T04", [], ["no_retention_offer"], "C50: I want to cancel my subscription.", "A: Hello. Before I cancel, can I review your plan with you? There is a better plan for your usage.", "C55: Okay.", "A: Good. I'll cancel only if you still want to."),
    case("T05", [], ["no_retention_offer"], "C50: I want to cancel my subscription.", "A: Hello. I'd like to keep you with us: I can offer a discount on your plan.", "C55: No thanks.", "A: Alright, I will cancel it then."),
    case("T06", [], ["no_retention_offer"], BILL, "A: Hello. I see the duplicate charge."),
    # ---- wrong facts ---------------------------------------------------------------------------------
    case("F01", ["wrong_fact"], [], BILL, "A: Hello. We will answer your dispute within two days."),
    case("F02", ["wrong_fact"], [], BILL, "A: Hello. About your dispute: you get our answer in a day or three."),
    case("F03", ["wrong_fact"], [], "C50: My plan change is not working.", "A: Hello. A plan change takes effect immediately."),
    case("F04", ["wrong_fact"], [], "C50: I paid my bill late.", "A: Hello. Your service will be restored within two days of the payment."),
    case("F05", ["wrong_fact"], [], BILL, "A: Hello. The refund will appear in your account today."),
    case("F06", ["wrong_fact"], [], "C50: I lost my SIM.", "A: Hello. The replacement SIM comes with a new number."),
    case("F07", [], ["wrong_fact"], BILL, "A: Hello. You will get our answer on the dispute within five working days."),
    case("F08", [], ["wrong_fact"], "C50: I paid my bill late.", "A: Hello. The service is restored within one hour of the payment."),
    case("F09", [], ["wrong_fact"], "C50: I want a better plan.", "A: Hello. The plan change starts with your next billing cycle."),
    case("F10", [], ["wrong_fact"], BILL, "A: Hello. The refund shows on your next statement."),
    case("F11", [], ["wrong_fact"], "C50: I lost my SIM.", "A: Hello. A replacement SIM keeps the same number."),
    # ---- answer grounded in the knowledge base -------------------------------------------------------
    case("G01", ["no_grounded_answer"], [], "C50: My roaming bundle did not work abroad.", "A: Hello. Lovely weather today, isn't it? How was your trip?"),
    case("G02", ["no_grounded_answer"], [], "C50: I want to cancel because of the early termination fee.", "A: Hello. Please hold the line for a moment."),
    case("G03", ["no_grounded_answer"], [], BILL, "A: Hello. We are very busy today, thank you for your understanding."),
    case("G04", [], ["no_grounded_answer"], "C50: My roaming bundle did not work abroad.", "A: Hello. Let me check that the roaming bundle was active for the country and the dates of your trip."),
    case("G05", [], ["no_grounded_answer"], BILL, "A: Hello. I can see the amount was charged twice on your bill, I will look at the billing history."),
    case("G06", [], ["no_grounded_answer"], "C50: I want to cancel because of the early termination fee.", "A: Hello. I understand the fee feels unfair, let me explain how the early termination fee is calculated for your contract."),
    # ---- absolute guarantees -------------------------------------------------------------------------
    case("O01", ["overpromise"], [], BILL, "A: Hello. I guarantee this will never happen again."),
    case("O02", ["overpromise"], [], BILL, "A: Hello. It's 100% sure that the problem is solved."),
    case("O03", ["overpromise"], [], BILL, "A: Hello. I'm absolutely sure, without a doubt, you won't see it twice."),
    case("O04", ["overpromise"], [], BILL, "A: Hello. That is guaranteed fixed."),
    case("O05", [], ["overpromise"], BILL, "A: Hello. I will do my best to fix it, and I will tell you tomorrow what I found."),
    case("O06", [], ["overpromise"], BILL, "A: Hello. Most of the time this is solved in a few days."),
    case("O07", [], ["overpromise"], BILL, "A: Hello. I have noted the problem and sent it to the billing team."),
    # ---- empathy for an upset customer ---------------------------------------------------------------
    case("E01", ["no_empathy"], [], "C20: This is unacceptable, I am furious!", "A: Hello. Let me open your file.", "C20: Hurry up.", "A: One second."),
    case("E02", ["no_empathy"], [], "C25: I've been waiting for an hour, this is ridiculous.", "A: Hello. What is your phone number?"),
    case("E03", ["no_empathy"], [], "C30: I'm so fed up with your service.", "A: Hello. State your problem."),
    case("E04", [], ["no_empathy"], "C20: This is unacceptable, I am furious!", "A: Hello. I'm really sorry, I would be angry too."),
    case("E05", [], ["no_empathy"], "C25: I've been waiting for an hour, this is ridiculous.", "A: Hello. That sounds exhausting, thank you for bearing with us."),
    case("E06", [], ["no_empathy"], "C30: I'm so fed up with your service.", "A: Hello. I can see why you're upset, let me put this right."),
    case("E07", [], ["no_empathy"], "C70: Hi, I have a quick question about my bill.", "A: Hello. Of course, what would you like to know?"),
    case("E08", [], ["no_empathy"], "C65: Good morning, I want to change my plan.", "A: Hello. Happy to help with that."),
    # ---- jargon --------------------------------------------------------------------------------------
    case("J01", ["jargon"], [], "C50: My internet does not work.", "A: Hello. Your APN configuration needs a new provisioning."),
    case("J02", ["jargon"], [], "C50: I cannot call abroad.", "A: Hello. The HLR shows your MSISDN without roaming."),
    case("J03", ["jargon"], [], "C50: My data is slow.", "A: Hello. It is a backend issue, I will escalate to tier 2."),
    case("J04", [], ["jargon"], "C50: My internet does not work.", "A: Hello. Please restart your phone and check that mobile data is switched on."),
    case("J05", [], ["jargon"], "C50: I cannot call abroad.", "A: Hello. Your line does not have the travel option yet, I can switch it on."),
    case("J06", [], ["jargon"], "C50: My data is slow.", "A: Hello. Let me look at how much data you have left this month."),
    # ---- asking to repeat ----------------------------------------------------------------------------
    case("Q01", ["ask_repeat"], [], BILL, "A: Hello. Could you go over the whole story again, please?"),
    case("Q02", ["ask_repeat"], [], BILL, "A: Hello. Tell me once more what happened from the beginning."),
    case("Q03", ["ask_repeat"], [], BILL, "A: Hello. Can you repeat the problem for me?"),
    case("Q04", ["ask_repeat"], [], BILL, "A: Hello. What was your problem again?"),
    case("Q05", [], ["ask_repeat"], BILL, "A: Hello. I have your history in front of me, I can see the two payments."),
    case("Q06", [], ["ask_repeat"], BILL, "A: Hello. Which of the two payments was made on the first of the month?"),
    case("Q07", [], ["ask_repeat"], BILL, "A: Hello. Thanks for explaining it so clearly, I understand."),
    # ---- transfers without the history ---------------------------------------------------------------
    case("X01", ["transfer"], [], BILL, "A: Hello. I'll pass you to a colleague in the billing department."),
    case("X02", ["transfer"], [], BILL, "A: Hello. Please hold while I put you through to another team."),
    case("X03", ["transfer"], [], BILL, "A: Hello. Let me transfer you."),
    case("X04", [], ["transfer"], BILL, "A: Hello. I'm going to transfer you to billing, stay on the line and I will pass them your whole history."),
    case("X05", [], ["transfer"], BILL, "A: Hello. I can fix this myself, no need to transfer you."),
    case("X06", [], ["transfer"], BILL, "A: Hello. I'll look at the invoice and solve it now."),
    # ---- greeting ------------------------------------------------------------------------------------
    case("H01", ["no_greeting"], [], BILL, "A: Yes, go ahead."),
    case("H02", ["no_greeting"], [], BILL, "A: Let me see your account."),
    case("H03", ["no_greeting"], [], BILL, "A: Name and number, please."),
    case("H04", [], ["no_greeting"], BILL, "A: Good afternoon, thanks for calling Orqestra. How can I help you?"),
    case("H05", [], ["no_greeting"], BILL, "A: Hi, you are speaking with Hela, what can I do for you today?"),
    case("H06", [], ["no_greeting"], BILL, "A: Welcome to customer care. How may I help?"),
    # ---- follow-up -----------------------------------------------------------------------------------
    case("U01", ["no_follow_up"], [], BILL, "A: Hello. I see, it should be fine now."),
    case("U02", ["no_follow_up"], [], BILL, "A: Hello. Okay, that is all I can do. Bye."),
    case("U03", ["no_follow_up"], [], BILL, "A: Hello. The billing team will take it from here."),
    case("U04", [], ["no_follow_up"], BILL, "A: Hello. I'll send you an email once it's done, with the case number."),
    case("U05", [], ["no_follow_up"], BILL, "A: Hello. You will receive a message that summarises everything we agreed."),
    case("U06", [], ["no_follow_up"], BILL, "A: Hello. I'll call you back on Friday to make sure it is solved."),
    case("U07", [], ["no_follow_up"], BILL, "A: Hello. I'm opening a ticket and you'll have the reference by text message."),
    # ---- closing -------------------------------------------------------------------------------------
    case("L01", ["no_closing"], [], BILL, "A: Hello. It is solved.", "C70: Thanks.", "A: Okay."),
    case("L02", ["no_closing"], [], BILL, "A: Hello. I have sent it to billing."),
    case("L03", ["no_closing"], [], BILL, "A: Hello. That is all."),
    case("L04", [], ["no_closing"], BILL, "A: Hello. It is solved. Is there anything else I can help you with today?"),
    case("L05", [], ["no_closing"], BILL, "A: Hello. It is solved. Thank you for calling, have a lovely day."),
    case("L06", [], ["no_closing"], BILL, "A: Hello. It is solved, I'm glad I could help."),
    case("L07", [], ["no_closing"], BILL, "A: Hello. It is solved. Would you like help with anything else?"),
    # ---- the customer's mood (given by the call, so these are checks of the rules themselves) --------
    case("M01", ["mood_drop"], [], "C70: I have a question.", "A: Hello. Let me transfer you.", "C40: Another transfer?"),
    case("M02", ["low_mood_end"], [], "C70: I have a question.", "A: Hello. Fine.", "C35: Whatever."),
    case("M03", ["hang_up"], [], "C40: I have a question.", "A: Hello. No.", "C15: That's it, I am hanging up."),
    case("M04", [], ["mood_drop", "low_mood_end", "hang_up"], "C60: I have a question.", "A: Hello. Happy to help, here is the answer.", "C85: Thanks a lot, goodbye."),
    case("M05", ["unresolved", "low_mood_end"], [], BILL, "A: Hello. That is the best I can do.", "C25: That is useless."),
    case("M06", ["low_mood_end"], ["unresolved"], BILL, "A: Hello. I'll email you the case number today.", "C30: Fine."),
    case("M07", ["unresolved"], [], BILL, "A: Hello. Nothing more to say.", "C20: You are no help at all."),
    case("M08", ["mood_drop"], [], "C80: Hi, quick question.", "A: Hello. That is not possible.", "C50: Really?"),
    case("M09", [], ["mood_drop"], "C60: Hi, quick question.", "A: Hello. I'm sorry, let me sort it.", "C70: Thank you."),
    case("M10", ["hang_up"], [], "C30: This is not fixed.", "A: Hello. Nothing I can do.", "C10: I've had enough, goodbye."),
    case("M11", [], ["hang_up"], "C70: Quick question.", "A: Hello. Here is the answer.", "C80: Thanks, goodbye."),
    case("M12", [], ["low_mood_end", "unresolved"], BILL, "A: Hello. I'll email you the case number today.", "C75: Thank you."),
]


def _more():
    from .eval_cases2 import CASES2
    cases = list(CASES2)
    if os.environ.get("QUALITY_EVAL_FINAL", "1") != "0":          # the final test calls (batch 3); QUALITY_EVAL_FINAL=0 keeps them out of sight while developing
        from .eval_cases3 import CASES3
        cases += CASES3
    return cases


CASES = CASES + _more()
