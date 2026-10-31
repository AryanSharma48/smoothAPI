import http from 'node:http';
import { URL } from 'node:url';

const port = parseInt(process.argv[2] ?? '3099', 10);
const seenIds = new Map();

const OK_BODY = Buffer.from('{"ok":true}');
const RETRY_OK_BODY = Buffer.from('{"ok":true,"retried":true}');
const ERR_BODY = Buffer.from('{"error":"transient_failure"}');

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  const pathname = url.pathname;

  if (pathname === '/normal_200') {
    res.writeHead(200, {
      'Content-Type': 'application/json',
      'Content-Length': OK_BODY.length,
    });
    res.end(OK_BODY);
    return;
  }

  if (pathname === '/intermittent_503_429') {
    const id = url.searchParams.get('id') ?? '0';
    if (!seenIds.has(id)) {
      seenIds.set(id, 1);
      if (seenIds.size > 50000) seenIds.clear();
      const idx = parseInt(id.split('_').pop() ?? '0', 10);
      if (idx % 2 === 0) {
        res.writeHead(503, {
          'Content-Type': 'application/json',
          'Content-Length': ERR_BODY.length,
        });
      } else {
        res.writeHead(429, {
          'Content-Type': 'application/json',
          'Retry-After': '0',
          'Content-Length': ERR_BODY.length,
        });
      }
      res.end(ERR_BODY);
    } else {
      seenIds.delete(id);
      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Content-Length': RETRY_OK_BODY.length,
      });
      res.end(RETRY_OK_BODY);
    }
    return;
  }

  if (pathname === '/repeated_failures_cb') {
    res.writeHead(503, {
      'Content-Type': 'application/json',
      'Content-Length': ERR_BODY.length,
    });
    res.end(ERR_BODY);
    return;
  }

  res.writeHead(404);
  res.end();
});

server.keepAliveTimeout = 60000;
server.headersTimeout = 65000;

server.listen(port, '127.0.0.1', () => {
  console.log(`E2E_SERVER_READY:${port}`);
});

