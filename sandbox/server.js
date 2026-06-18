import express from 'express';

const app = express();
const PORT = 3001;

// Mutable request counter. Drives the failure injection logic below.
// Intentionally module-scoped so /reset can zero it between test suites.
let requestCount = 0;

app.use(express.json());

app.use((req, res, next) => {
  res.header("Access-Control-Allow-Origin", "*");
  next();
});

// Always 200. Used by test runners to poll for readiness before the suite
// starts. Does not touch requestCount.
app.get('/health', (_req, res) => {
  res.status(200).json({ status: 'ok', requestCount });
});

// Zeroes requestCount. Call this before each test suite so the two runners
// (TS and Python) don't share counter state and get wrong status codes.
app.get('/reset', (_req, res) => {
  requestCount = 0;
  res.status(200).json({ message: 'Counter reset', requestCount });
});

// Deterministic failure injection via modular arithmetic.
//
// Counter is incremented before branching so the first real request is #1,
// not #0 — keeps the sequence readable in logs and predictable in tests.
//
// Precedence: %3 (500) is evaluated before %5 (429). At multiples of 15
// both conditions hold; the 500 branch wins.
//
//   count  %3  %5  status
//       3   0       500
//       5       0   429
//       6   0       500
//       9   0       500
//      10       0   429
//      12   0       500
//      15   0   0   500
//
// Note: the failures are spaced out by 200s, never 3-in-a-row. A circuit
// breaker that resets its failure count on every success (as ours does) will
// therefore never trip against this endpoint — each 500/429 is followed by a
// 200 that clears the counter. Use /always-fail to exercise the breaker.
//
app.get('/unstable-data', (_req, res) => {
  requestCount++;

  console.log(`[sandbox] req #${requestCount}`);

  if (requestCount % 3 === 0) {
    console.log(`[sandbox]   500`);
    return res.status(500).json({ error: 'Internal Server Error' });
  }

  if (requestCount % 5 === 0) {
    console.log(`[sandbox]   429`);
    return res.status(429).json({ error: 'Too Many Requests' });
  }

  console.log(`[sandbox]   200`);
  return res.status(200).json({ success: true, data: 'Solid Data' });
});

// Always 500. Unlike /unstable-data, this never succeeds, so consecutive
// failures accumulate and trip a circuit breaker. Does not touch requestCount.
app.get('/always-fail', (_req, res) => {
  console.log(`[sandbox] /always-fail -> 500`);
  return res.status(500).json({ error: 'Service Unavailable' });
});

app.listen(PORT, () => {
  console.log(`[sandbox] listening on http://localhost:${PORT}`);
});
