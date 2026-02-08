const http = require("http");
const { URL } = require("url");

const DEFAULT_PORT = Number(process.env.PORT || "8787");

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  const isTarget = req.method === "POST" && url.pathname === "/intake/directive";

  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");

  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.end();
    return;
  }

  if (!isTarget) {
    res.statusCode = 404;
    res.end("Not found");
    return;
  }

  const bodyText = await readBody(req);
  let parsed = null;
  try {
    parsed = JSON.parse(bodyText);
  } catch {
    // ignore
  }

  const ts = new Date().toISOString();
  process.stdout.write(`\n[${ts}] /intake/directive\n`);
  process.stdout.write(`Authorization: ${req.headers.authorization || ""}\n`);
  process.stdout.write(`${parsed ? JSON.stringify(parsed, null, 2) : bodyText}\n`);

  res.statusCode = 200;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify({ ok: true, received_at: ts }));
});

server.listen(DEFAULT_PORT, "127.0.0.1", () => {
  process.stdout.write(`mock_intake_server listening on http://127.0.0.1:${DEFAULT_PORT}/intake/directive\n`);
});
