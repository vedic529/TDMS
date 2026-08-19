/**
 * Bulk import matching and the Personal Email rule.
 *
 * Mirrors `import-validation.ts`. Keep the two in step.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

const INVISIBLE = /[ ​‌‍﻿]/g;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function normalise(value) {
  return value.replace(INVISIBLE, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
}

function splitEmails(value) {
  return value
    .split(',')
    .map((entry) => entry.replace(INVISIBLE, ' ').trim())
    .filter(Boolean);
}

const invalidEmails = (value) => splitEmails(value).filter((e) => !EMAIL.test(e));

// ------------------------------------------------------- invisible characters

test('a non-breaking space does not stop a campus matching', () => {
  // The real failure: a student file carried `Tasmania 7000`, the database
  // holds `Tasmania 7000`. Identical on screen, different to a comparison.
  const fromFile = '132-146 Elizabeth Street, HOBART, Tasmania  7000';
  const fromDatabase = '132-146 Elizabeth Street, HOBART, Tasmania 7000';

  assert.notEqual(fromFile.trim().toLowerCase(), fromDatabase.trim().toLowerCase());
  assert.equal(normalise(fromFile), normalise(fromDatabase));
});

test('zero-width characters are normalised too', () => {
  assert.equal(normalise('​CHC33021​'), 'chc33021');
  assert.equal(normalise('﻿AIBT'), 'aibt');
});

test('repeated and surrounding whitespace collapses', () => {
  assert.equal(normalise('  125  Main   St  '), '125 main st');
});

test('normalising does not make different values equal', () => {
  assert.notEqual(normalise('CHC30121'), normalise('CHC30125'));
  assert.notEqual(normalise('Hobart'), normalise('Haymarket'));
});

// ------------------------------------------------------------ personal email

test('one address is accepted', () => {
  assert.deepEqual(invalidEmails('student@example.com'), []);
});

test('several addresses separated by commas are accepted', () => {
  // Students supply more than one — their own and an agent's.
  assert.deepEqual(invalidEmails('a@gmail.com,b@icloud.com'), []);
  assert.deepEqual(invalidEmails('info@studyagency.example,jordan.lee@example.com'), []);
});

test('spacing around the separator does not matter', () => {
  assert.deepEqual(invalidEmails('a@x.com , b@y.com'), []);
});

test('they are stored comma-separated and normalised', () => {
  assert.equal(splitEmails('a@x.com , b@y.com').join(','), 'a@x.com,b@y.com');
  assert.equal(splitEmails('a@x.com,,b@y.com').join(','), 'a@x.com,b@y.com');
});

test('only the malformed address is reported, not the whole field', () => {
  // One bad entry must not condemn the valid ones alongside it.
  assert.deepEqual(invalidEmails('good@x.com,not-an-email'), ['not-an-email']);
});

test('several malformed addresses are all reported', () => {
  assert.deepEqual(invalidEmails('bad1,good@x.com,bad2'), ['bad1', 'bad2']);
});

test('an empty value raises nothing — Personal Email is optional', () => {
  assert.deepEqual(invalidEmails(''), []);
  assert.deepEqual(invalidEmails('   '), []);
});
