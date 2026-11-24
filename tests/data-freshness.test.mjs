import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './helpers/load-ts.mjs';
const {sessionsLate, isSession} = loadTs('app/data-freshness.ts');
const at = (iso, utc) => sessionsLate(iso, new Date(utc));

test('a session counts as late from midnight New York after its close', () => {
 // Monday 22:11 ET: Monday's run has until midnight; Friday data is still on time.
 assert.equal(at('2026-11-20', '2026-11-24T03:11:00Z'), 0);
 assert.equal(at('2026-11-23', '2026-11-24T03:11:00Z'), 0);
 // Tuesday 00:30 ET without Monday's data: one session late.
 assert.equal(at('2026-11-20', '2026-11-24T05:30:00Z'), 1);
});

test('the 18–20 November failure turns amber after the first missed session', () => {
 assert.equal(at('2026-11-17', '2026-11-19T04:59:00Z'), 0);
 assert.equal(at('2026-11-17', '2026-11-19T05:30:00Z'), 1);
 assert.equal(at('2026-11-17', '2026-11-21T12:00:00Z'), 3);
});

test('NYSE holidays and weekends are not counted', () => {
 assert.equal(isSession('2026-11-26'), false);
 assert.equal(isSession('2026-11-27'), true);
 // Thanksgiving: Wednesday data is complete on Friday morning, late from Saturday.
 assert.equal(at('2026-11-25', '2026-11-27T12:00:00Z'), 0);
 assert.equal(at('2026-11-25', '2026-11-28T06:00:00Z'), 1);
 // 3 July closure and summer time (UTC-4).
 assert.equal(at('2026-07-02', '2026-07-07T03:59:00Z'), 0);
 assert.equal(at('2026-07-02', '2026-07-07T04:01:00Z'), 1);
});

test('newer or malformed dates are never late', () => {
 assert.equal(at('2026-11-24', '2026-11-24T05:30:00Z'), 0);
 for (const bad of ['', '2026-13-40', 'not-a-date']) assert.equal(at(bad, '2026-11-24T05:30:00Z'), 0, bad);
});
