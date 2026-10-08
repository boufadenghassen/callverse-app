import { Injectable } from '@nestjs/common';
import { AgentGateway } from './agent.gateway';
import * as m from './models';

/** Realistic fake data so the UI can be built and demoed before the agents are ready. */
@Injectable()
export class MockAgentGateway extends AgentGateway {
  async customerContext(id: string): Promise<m.CustomerContext> {
    return { id, name: 'Yasmine Toumi', profile: 'Loyal customer, 6 years', intents: ['Billing', 'Plan change'],
      contract: 'Mobile Plus 40 GB', openTickets: 1, transfers: 1, mood: 'Impatient' };
  }

  async suggestAnswer(): Promise<m.SuggestedAnswer> {
    return {
      text: "I can see the double charge on your September bill. I've opened a refund for the duplicate amount; "
        + "it will appear on your next statement. I'm also noting your plan-change request so you won't need to explain it again.",
      sources: ['Billing policy §4.2', 'Refund procedure v3'],
      policyWarning: 'Refunds above 50 TND need supervisor approval.', confidence: 0.86,
    };
  }

  async forecast(): Promise<m.ForecastPoint[]> {
    // [hour, actual, forecast]; actual is null for hours not reached yet
    const rows: [string, number | null, number][] = [['9h', 20, 22], ['10h', 28, 30], ['11h', 40, 42], ['12h', 52, 55], ['13h', 60, 64],
      ['14h', null, 72], ['15h', null, 60], ['16h', null, 45], ['17h', null, 35]];
    return rows.map(([hour, actual, forecast]) => ({ hour, actual, forecast }));
  }

  async simulate(r: m.SimulationRequest): Promise<m.SimulationResult> {
    const baseline = 240;
    return {
      baselineWaitSec: baseline, simulatedWaitSec: Math.max(20, baseline - r.extraAdvisors * 55),
      baselineSla: 0.71, simulatedSla: Math.min(0.98, 0.71 + r.extraAdvisors * 0.06),
      recommendations: ['Move 2 billing-skilled advisors from queue A (forecast below capacity)',
        'Shift one break from 14:30 to 16:15', 'Offer a callback when the wait passes 3 minutes'],
    };
  }

  async recentReviews(): Promise<m.QualityReview[]> {
    return [
      { callId: 'CALL-3381', advisor: 'Karim B.', overall: 62, criteria: [
          { name: 'Accuracy', score: 8, max: 10, evidence: 'Correct refund amount quoted', timestamp: '01:12' },
          { name: 'Compliance', score: 4, max: 10, evidence: 'Promised a refund before checking the approval policy', timestamp: '02:41' },
          { name: 'Communication', score: 9, max: 10, evidence: 'Acknowledged frustration before answering', timestamp: '00:35' },
          { name: 'Resolution', score: 5, max: 10, evidence: 'Plan change left open, no follow-up set', timestamp: '04:02' }],
        counterfactual: 'If the refund approval had been checked first, compliance would have passed (+5).' },
      { callId: 'CALL-3379', advisor: 'Hela M.', overall: 88, criteria: [
          { name: 'Accuracy', score: 9, max: 10, evidence: 'Right plan details given', timestamp: '00:58' },
          { name: 'Compliance', score: 10, max: 10, evidence: 'Identity verified before account access', timestamp: '00:20' },
          { name: 'Communication', score: 8, max: 10, evidence: 'Some jargon with a new customer', timestamp: '01:45' },
          { name: 'Resolution', score: 9, max: 10, evidence: 'Issue closed on first contact', timestamp: '03:10' }],
        counterfactual: "Replacing 'APN settings' with plain wording would lift communication to 10." },
    ];
  }

  async openComplaints(): Promise<m.ComplaintCase[]> {
    return [
      { id: 'CMP-221', summary: 'Charged twice, third contact this month', severity: 'Critical', escalationRisk: 87, cluster: 'Billing duplicates', hoursLeft: 6 },
      { id: 'CMP-219', summary: 'Roaming bundle not applied abroad', severity: 'High', escalationRisk: 64, cluster: 'Roaming activation', hoursLeft: 20 },
      { id: 'CMP-214', summary: 'Contract cancellation fee disputed', severity: 'Medium', escalationRisk: 41, cluster: 'Contract terms', hoursLeft: 46 },
    ];
  }

  async scenarios(): Promise<m.Scenario[]> {
    return [
      { id: 'SC-31', title: 'Double charge, customer threatens to post online', profile: 'Unsatisfied', difficulty: 'Hard', origin: 'QA weakness: compliance' },
      { id: 'SC-30', title: 'First call from a new subscriber about data limits', profile: 'New', difficulty: 'Easy', origin: 'Template library' },
      { id: 'SC-29', title: 'Premium customer, two intents, transferred once', profile: 'Premium', difficulty: 'Medium', origin: 'What-if mutation' },
    ];
  }

  async opportunities(): Promise<m.Opportunity[]> {
    return [
      { customer: 'Mounir Sassi', offer: 'Family bundle', relevance: 82, reason: 'Asked twice about adding a line' },
      { customer: 'Salma Hammami', offer: 'Loyalty data top-up', relevance: 71, reason: 'Usage dropping, churn risk; retention offer' },
    ];
  }
}
