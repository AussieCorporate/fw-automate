'use strict';
// Pins _tacCarouselFindNewMatch (flatwhite/dashboard/static/index.html),
// the pure decision function verifyTacCarouselSaved uses to tell a
// genuinely-new-for-THIS-topic Content Bank row apart from noise. This is
// the layer the code review round-2 finding (G1, 27 Aug 2026) actually
// lives at: cross-topic contamination, where _MAX_CONCURRENT lets two
// topics build at once and topic B's save could make topic A's poll toast
// success even though A's own script never saved.
//
// This repo has no browser/JS test harness, so the function is extracted
// straight out of the live index.html (brace-matched, not regex-guessed)
// and executed with plain Node `assert` - run via
// tests/test_tac_instagram_api.py::test_tac_carousel_frontend_js_pinning_tests_pass,
// so it's part of the normal pytest run, not a separate manual step.
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const htmlPath = path.join(__dirname, '..', '..', 'flatwhite', 'dashboard', 'static', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

function extractFunction(src, name) {
  const marker = 'function ' + name + '(';
  const start = src.indexOf(marker);
  if (start === -1) {
    throw new Error('Could not find function ' + name + '() in index.html - has it been renamed or removed?');
  }
  const braceStart = src.indexOf('{', start);
  let depth = 0;
  let i = braceStart;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) { i++; break; }
    }
  }
  if (depth !== 0) {
    throw new Error('Could not find a balanced closing brace for ' + name + '()');
  }
  return src.slice(start, i);
}

const fnSrc = extractFunction(html, '_tacCarouselFindNewMatch');
// eslint-disable-next-line no-new-func
const _tacCarouselFindNewMatch = new Function('return (' + fnSrc + ')')();

// --- G1 regression: cross-topic contamination -----------------------------
// A new row (id past beforeMaxId) that belongs to a DIFFERENT topic must
// never count as proof THIS topic's carousel saved.
{
  const items = [
    { id: 10, title: 'Sunday scaries' },  // pre-existing, at the beforeMaxId boundary
    { id: 12, title: 'Cover Letters' },   // NEW row, but a DIFFERENT topic entirely
  ];
  const match = _tacCarouselFindNewMatch(items, 10, 'Sunday scaries');
  assert.strictEqual(match, null,
    'a same-run new row from a DIFFERENT topic must not count as a match for this topic');
}

// The genuine match: a new id AND the matching title.
{
  const items = [
    { id: 10, title: 'Sunday scaries' },
    { id: 12, title: 'Cover Letters' },
    { id: 13, title: 'Sunday scaries' },  // the real new save for THIS topic
  ];
  const match = _tacCarouselFindNewMatch(items, 10, 'Sunday scaries');
  assert.ok(match, 'the genuinely new same-topic row must be found');
  assert.strictEqual(match.id, 13);
}

// A same-title row that already existed BEFORE this run (id <= beforeMaxId)
// must not count - that's a stale item from a previous build of the same
// topic, not proof THIS run saved anything.
{
  const items = [{ id: 5, title: 'Sunday scaries' }];
  const match = _tacCarouselFindNewMatch(items, 10, 'Sunday scaries');
  assert.strictEqual(match, null,
    'an old row for the same topic (id <= beforeMaxId) must not count as a new match');
}

// The highest-id match wins when more than one new row for the topic exists.
{
  const items = [
    { id: 11, title: 'Sunday scaries' },
    { id: 14, title: 'Sunday scaries' },
  ];
  const match = _tacCarouselFindNewMatch(items, 10, 'Sunday scaries');
  assert.strictEqual(match.id, 14);
}

// Empty/undefined items must never throw.
{
  assert.strictEqual(_tacCarouselFindNewMatch([], 0, 'Sunday scaries'), null);
  assert.strictEqual(_tacCarouselFindNewMatch(undefined, 0, 'Sunday scaries'), null);
}

console.log('tac_carousel_frontend_test.js: all assertions passed');
