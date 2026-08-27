'use strict';
// Pins jsq() (flatwhite/dashboard/static/index.html), the helper every TAC
// Instagram render function uses to embed user-entered text (topic names,
// community questions, week labels, filenames) inside a DOUBLE-quoted
// onclick/onchange/ondragstart attribute, e.g.
//   onclick="buildTacCarousel(' + t.id + ',' + jsq(t.topic) + ')"
//
// F3 (fix wave, 27 Aug 2026 code review): jsq() only escaped backslash and
// single-quote. Two real gaps:
//   1. A raw double-quote in the value closes the surrounding HTML
//      attribute early - the rest of jsq()'s output becomes bogus extra
//      "attributes" on the tag instead of staying inside onclick="...".
//   2. A raw newline/carriage-return inside the JS single-quoted string
//      literal jsq() builds is a SyntaxError (JS string literals can't
//      contain a literal line break) - the inline handler simply fails to
//      parse, so the button's onclick does nothing.
// The fix escapes " -> &quot; (the HTML entity, decoded by the browser
// before the attribute's JS is compiled - this is exactly how escAttr()
// already handles the same problem for value=/href=/title= attributes,
// see the comment above escAttr() in index.html) and \n / \r -> the JS
// string escapes \n / \r.
//
// No browser/JS test harness exists in this repo (see the sibling
// tac_carousel_frontend_test.js for the same pattern), so this simulates
// what a browser actually does with an onclick="..." attribute:
//   (a) parse the HTML attribute value up to the first UNESCAPED double
//       quote (a real browser's HTML tokenizer works exactly this way -
//       it does not know or care about JS string syntax, only about where
//       the attribute's own quote delimiter is)
//   (b) HTML-decode entities in that attribute value (&quot; -> ")
//   (c) compile the decoded text as a function body and run it, the way a
//       browser compiles an inline event handler
// Run via tests/test_tac_instagram_api.py::test_tac_jsq_frontend_js_pinning_tests_pass.
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

const fnSrc = extractFunction(html, 'jsq');
// eslint-disable-next-line no-new-func
const jsq = new Function('return (' + fnSrc + ')')();

// Mirrors how a browser's HTML tokenizer finds a double-quoted attribute's
// value: everything up to the first (unescaped) literal '"' character.
// &quot; is just the characters &, q, u, o, t, ; at this stage - not a
// delimiter - which is exactly the property the fix relies on.
function extractDoubleQuotedAttr(fragmentHtml, attrName) {
  const marker = attrName + '="';
  const start = fragmentHtml.indexOf(marker);
  if (start === -1) throw new Error('attribute not found: ' + attrName);
  const contentStart = start + marker.length;
  const end = fragmentHtml.indexOf('"', contentStart);
  if (end === -1) throw new Error('no closing quote found for ' + attrName);
  return fragmentHtml.slice(contentStart, end);
}

function htmlDecode(s) {
  // The handful of entities esc()/escAttr()/this fix actually produce -
  // not a general HTML-entity decoder.
  return s.replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
}

// --- F3 regression: a double quote must not close the attribute early ----
{
  const value = 'She asked "why though?"';
  const call = 'handler(' + jsq(value) + ')';
  const fragment = '<button onclick="' + call + '">x</button>';

  const attrRaw = extractDoubleQuotedAttr(fragment, 'onclick');
  assert.strictEqual(attrRaw, call,
    'a literal double quote in the value must not truncate the onclick attribute');

  const decoded = htmlDecode(attrRaw);
  let captured = null;
  const fn = new Function('handler', decoded);
  fn(function(v) { captured = v; });
  assert.strictEqual(captured, value,
    'the double-quote-bearing value must round-trip exactly through the compiled handler');
}

// --- F3 regression: newlines/carriage returns must not break the JS ------
{
  const value = 'Line one\nLine two\r\nLine three';
  const call = 'handler(' + jsq(value) + ')';
  const fragment = '<button onclick="' + call + '">x</button>';

  const attrRaw = extractDoubleQuotedAttr(fragment, 'onclick');
  const decoded = htmlDecode(attrRaw);

  // A raw newline inside a JS single-quoted string literal is a
  // SyntaxError - new Function() throwing here IS the bug reproducing.
  let captured = null;
  const fn = new Function('handler', decoded);
  fn(function(v) { captured = v; });
  assert.strictEqual(captured, value,
    'newline/carriage-return content must round-trip exactly through the compiled handler');
}

// --- Combined: quotes, newlines, backslashes and single quotes together --
{
  const value = 'A "quoted" line\nwith a \\backslash\\ and a \'single quote\'\r\nend';
  const call = 'handler(' + jsq(value) + ',' + jsq('second arg') + ')';
  const fragment = '<img title="x" onclick="' + call + '" data-x="y">';

  const attrRaw = extractDoubleQuotedAttr(fragment, 'onclick');
  assert.strictEqual(attrRaw, call, 'combined special characters must not truncate the attribute');

  const decoded = htmlDecode(attrRaw);
  let capturedFirst = null;
  let capturedSecond = null;
  const fn = new Function('handler', decoded);
  fn(function(v, w) { capturedFirst = v; capturedSecond = w; });
  assert.strictEqual(capturedFirst, value);
  assert.strictEqual(capturedSecond, 'second arg');
}

// --- Pre-existing behaviour (backslash / single-quote) must still hold ---
{
  const value = "back\\slash and 'single' quotes";
  const call = 'handler(' + jsq(value) + ')';
  const fragment = '<button onclick="' + call + '">x</button>';

  const attrRaw = extractDoubleQuotedAttr(fragment, 'onclick');
  const decoded = htmlDecode(attrRaw);
  let captured = null;
  const fn = new Function('handler', decoded);
  fn(function(v) { captured = v; });
  assert.strictEqual(captured, value);
}

// Every jsq() call site in index.html was checked by hand (grep 'jsq(') and
// confirmed to sit inside a double-quoted onclick=/onchange=/ondragstart=
// attribute (community_question ~1354, topic name ~1364, week label ~1947,
// plus setTacTopicFilter ~1427, openBigConvTopic/archiveBigConvTopic ~3209-10,
// runBigConvTopic ~3293-3300, bcDragStart/bcPreview ~3314-3365,
// toggleInsideTrackPick ~3848) - none embed inside a single-quoted attribute
// or a non-attribute JS context, so hardening jsq() is safe for every
// existing call site.

console.log('tac_jsq_frontend_test.js: all assertions passed');
