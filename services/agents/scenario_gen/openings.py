"""What the customer says first in a practice call, and how they name their problem afterwards.

The catalogue's cards are written to the customer ("You were charged twice..."). The customer simulator speaks English and has only three reasons for
a call, so these lines, in the customer's own voice, are what keep a lost SIM a lost SIM on the phone.
"""
OPENINGS = {
    "double_billing": ("I was charged twice for the same invoice and nobody has fixed it.", "my double charge"),
    "roaming_bill_shock": ("I'm travelling abroad and I'm scared of a huge data roaming bill. What have I been charged, and how do I stop it?", "my roaming charges"),
    "line_cut": ("My line was cut while I'm abroad and I can't make calls any more.", "my line"),
    "slow_internet": ("My home internet has been very slow for a week and I can't work from home any more.", "my internet"),
    "cancellation_request": ("I want to cancel after six years. I really didn't want to, but the prices keep going up.", "my cancellation"),
    "refund_status": ("I'm waiting for a refund I was promised two weeks ago. Where is it?", "my refund"),
    "data_allowance_question": ("Hello. How much data is left on my plan, and when does it renew?", "my data allowance"),
    "plan_change": ("I want a cheaper plan, but I don't want to lose my number or my benefits.", "my plan"),
    "fee_dispute": ("I was charged a fee nobody explained to me, and I was told it was normal. I find that insulting.", "this fee"),
    "lost_sim_or_phone": ("I lost my phone with my SIM card. I want the line blocked right now and a replacement.", "my lost SIM"),
    "installation_delay": ("A technician was supposed to come on Monday and never showed up. I waited at home all day.", "my installation"),
    "unrecognized_charge": ("There's a charge on my bill I don't recognize, and I'm afraid someone used my number.", "this charge"),
    "contract_renewal_offer": ("I got a message about renewing my contract. What are the offers before I decide?", "my contract renewal"),
    "refund_received": ("My refund just arrived, and the advisor who handled it was very kind. When is my next invoice?", "my next invoice"),
    "formal_complaint": ("I want to file a formal complaint about how I was treated in a shop, and I want a written answer.", "my complaint"),
}
