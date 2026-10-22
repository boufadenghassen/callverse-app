// Rebuilds tests/golden_customer.json from the compiled TypeScript simulator (the reference), so the Python port can be checked against it.
// Run from the repository root after `npm run build` in app/:   node services/agents/tests/regenerate_golden.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, '..', '..', '..', 'app', 'dist', 'pages');
const { replay } = await import(pathToFileURL(join(dist, 'client-simulator.js')).href);
const { readAdvisor } = await import(pathToFileURL(join(dist, 'customer-llm.js')).href);

const file = join(here, 'golden_customer.json');
const gold = JSON.parse(readFileSync(file, 'utf8'));

// what the advisor said, and the move it is read as; new sentences are added once, below
const extraTexts = ['WHAT ARE YOU DOING!!!', "Don't be stupid.", 'Why did you put $2,000?', 'Good morning, how can I help?', 'Is this about 45 TND?', 'shut up and listen'];
const texts = [...new Set([...gold.texts.map(([t]) => t), ...extraTexts])].map((t) => [t, readAdvisor(t)]);

// a recorded call is its inputs; the lines, moods and outcome are recomputed from them
const extraCases = [
  { persona: 'IMPATIENT', mix: null, difficulty: 'MEDIUM', intent: 'BILLING', memory: false,
    moves: ['OTHER', 'OTHER', 'RUDE', 'OTHER'], said: ['Hello, how are you today?', 'Why did you put $2,000?', 'WHAT ARE YOU DOING!!!', 'Can you give me your name?'] },
  { persona: 'ANGRY_PREMIUM', mix: null, difficulty: 'HARD', intent: 'ROAMING', memory: true,
    moves: ['RUDE', 'RUDE', 'EMPATHY'], said: ["Don't be stupid.", 'I SAID NOW!!!', "I'm sorry."] },
  { persona: 'ANXIOUS', mix: null, difficulty: 'EASY', intent: 'CANCELLATION', memory: false,
    moves: ['OTHER', 'RUDE', 'EMPATHY', 'CHECK_POLICY', 'FOLLOW_UP'],
    said: ['Is this about 45 TND?', 'shut up and listen', 'I understand, sorry.', 'Let me check the policy.', 'I will email you a confirmation.'] },
];
const known = new Set(gold.cases.map((c) => JSON.stringify([c.persona, c.mix, c.difficulty, c.intent, c.memory, c.moves])));
const inputs = [...gold.cases, ...extraCases.filter((c) => !known.has(JSON.stringify([c.persona, c.mix, c.difficulty, c.intent, c.memory, c.moves])))];

const cases = inputs.map((c) => {
  const s = replay(c.persona, c.mix, c.difficulty, c.intent, c.memory, c.moves, c.said);
  return { persona: c.persona, mix: c.mix, difficulty: c.difficulty, intent: c.intent, memory: c.memory, said: c.said, moves: c.moves,
    opening: s.opening, turns: s.turns, outcome: s.outcome };
});

writeFileSync(file, JSON.stringify({ texts, cases }, null, 1) + '\n');
console.log(`${texts.length} sentences and ${cases.length} calls written to ${file}`);
