const encoder = new TextEncoder();
const AAD = encoder.encode("website-investigator-slack-v1");
const MAX_BODY_BYTES = 8192;
const MAX_CLOCK_SKEW_SECONDS = 300;

function base64url(bytes) {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decodeBase64url(value, expectedLength) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error("invalid secret");
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const bytes = Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
  if (expectedLength !== undefined && bytes.length !== expectedLength) {
    throw new Error("invalid secret");
  }
  return bytes;
}

function constantTimeEqual(left, right) {
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  if (leftBytes.length !== rightBytes.length) return false;
  let difference = 0;
  for (let index = 0; index < leftBytes.length; index += 1) {
    difference |= leftBytes[index] ^ rightBytes[index];
  }
  return difference === 0;
}

export async function signSlackBody(secret, timestamp, body, cryptoImpl = crypto) {
  const key = await cryptoImpl.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await cryptoImpl.subtle.sign(
    "HMAC",
    key,
    encoder.encode(`v0:${timestamp}:${body}`),
  );
  return `v0=${[...new Uint8Array(signature)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("")}`;
}

async function verifySlackRequest(request, body, secret, nowSeconds, cryptoImpl) {
  const timestampText = request.headers.get("x-slack-request-timestamp") || "";
  const signature = request.headers.get("x-slack-signature") || "";
  if (!/^\d{10}$/.test(timestampText) || !/^v0=[0-9a-f]{64}$/.test(signature)) return false;
  const timestamp = Number.parseInt(timestampText, 10);
  if (Math.abs(nowSeconds - timestamp) > MAX_CLOCK_SKEW_SECONDS) return false;
  const expected = await signSlackBody(secret, timestampText, body, cryptoImpl);
  return constantTimeEqual(signature, expected);
}

function parseCommandText(value) {
  let cleaned = value.trim();
  if (cleaned.startsWith("<") && cleaned.endsWith(">")) {
    cleaned = cleaned.slice(1, -1).split("|", 1)[0];
  }
  if (!cleaned || ["help", "hjelp"].includes(cleaned.toLowerCase())) return null;
  if (/\s/.test(cleaned) || cleaned.length > 2048) throw new Error("invalid command");
  return cleaned;
}

function validSlackId(value) {
  return /^[A-Z][A-Z0-9]{5,31}$/.test(value);
}

function newRequestId(now, cryptoImpl) {
  const timestamp = new Date(now)
    .toISOString()
    .replaceAll("-", "")
    .replaceAll(":", "")
    .replace(/\.\d{3}Z$/, "Z");
  const random = cryptoImpl.getRandomValues(new Uint8Array(5));
  return `${timestamp}-${[...random]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("")}`;
}

export async function encryptJob(payload, payloadKey, cryptoImpl = crypto) {
  const keyBytes = decodeBase64url(payloadKey, 32);
  const key = await cryptoImpl.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["encrypt"]);
  const nonce = cryptoImpl.getRandomValues(new Uint8Array(12));
  const ciphertext = await cryptoImpl.subtle.encrypt(
    { name: "AES-GCM", iv: nonce, additionalData: AAD },
    key,
    encoder.encode(JSON.stringify(payload)),
  );
  return `v1.${base64url(nonce)}.${base64url(new Uint8Array(ciphertext))}`;
}

export async function decryptJob(token, payloadKey, cryptoImpl = crypto) {
  const parts = token.split(".");
  if (parts.length !== 3 || parts[0] !== "v1") throw new Error("invalid payload");
  const key = await cryptoImpl.subtle.importKey(
    "raw",
    decodeBase64url(payloadKey, 32),
    "AES-GCM",
    false,
    ["decrypt"],
  );
  const plaintext = await cryptoImpl.subtle.decrypt(
    { name: "AES-GCM", iv: decodeBase64url(parts[1], 12), additionalData: AAD },
    key,
    decodeBase64url(parts[2]),
  );
  return JSON.parse(new TextDecoder().decode(plaintext));
}

function slackResponse(text, status = 200) {
  return new Response(JSON.stringify({ response_type: "ephemeral", text }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

async function dispatchGitHub(env, encryptedJob, fetchImpl) {
  const owner = encodeURIComponent(env.GITHUB_OWNER);
  const repository = encodeURIComponent(env.GITHUB_REPO);
  const workflow = encodeURIComponent(env.GITHUB_WORKFLOW);
  const response = await fetchImpl(
    `https://api.github.com/repos/${owner}/${repository}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
        "content-type": "application/json",
        "user-agent": "website-investigator-slack-receiver",
        "x-github-api-version": "2026-03-10",
      },
      body: JSON.stringify({ ref: env.GITHUB_REF, inputs: { job: encryptedJob } }),
      signal: AbortSignal.timeout(1800),
    },
  );
  return response.ok;
}

export async function handleRequest(
  request,
  env,
  { fetchImpl = fetch, now = () => Date.now(), cryptoImpl = crypto } = {},
) {
  const url = new URL(request.url);
  if (request.method !== "POST" || url.pathname !== "/slack/commands") {
    return new Response("Not found", { status: 404 });
  }
  const requiredSecrets = [
    env.SLACK_SIGNING_SECRET,
    env.SLACK_TEAM_ID,
    env.SLACK_ALLOWED_USER_IDS,
    env.GITHUB_ACTIONS_TOKEN,
    env.WI_SLACK_PAYLOAD_KEY,
  ];
  if (requiredSecrets.some((value) => typeof value !== "string" || value.length === 0)) {
    return new Response("Service unavailable", { status: 503 });
  }
  const contentLength = Number.parseInt(request.headers.get("content-length") || "0", 10);
  if (contentLength > MAX_BODY_BYTES) return new Response("Request too large", { status: 413 });
  const body = await request.text();
  if (encoder.encode(body).length > MAX_BODY_BYTES) {
    return new Response("Request too large", { status: 413 });
  }

  const nowMilliseconds = now();
  const authentic = await verifySlackRequest(
    request,
    body,
    env.SLACK_SIGNING_SECRET,
    Math.floor(nowMilliseconds / 1000),
    cryptoImpl,
  );
  if (!authentic) return new Response("Unauthorized", { status: 401 });

  const fields = new URLSearchParams(body);
  const teamId = fields.get("team_id") || "";
  const userId = fields.get("user_id") || "";
  const channelId = fields.get("channel_id") || "";
  if (fields.get("command") !== "/undersok" || teamId !== env.SLACK_TEAM_ID) {
    return new Response("Forbidden", { status: 403 });
  }
  if (![teamId, userId, channelId].every(validSlackId)) {
    return new Response("Invalid request", { status: 400 });
  }
  const allowedUsers = new Set(
    env.SLACK_ALLOWED_USER_IDS.split(",").map((value) => value.trim()).filter(validSlackId),
  );
  if (allowedUsers.size === 0) return new Response("Service unavailable", { status: 503 });
  if (!allowedUsers.has(userId)) {
    return slackResponse("Du har ikke tilgang til å starte en undersøkelse.");
  }

  let target;
  try {
    target = parseCommandText(fields.get("text") || "");
  } catch {
    return slackResponse("Oppgi én nettadresse, for eksempel `/undersok nettadresse.no`.");
  }
  if (!target) {
    return slackResponse("Bruk `/undersok nettadresse.no` for å starte en privat undersøkelse.");
  }

  const requestId = newRequestId(nowMilliseconds, cryptoImpl);
  const encryptedJob = await encryptJob(
    {
      version: 1,
      request_id: requestId,
      url: target,
      user_id: userId,
      team_id: teamId,
      channel_id: channelId,
      issued_at: Math.floor(nowMilliseconds / 1000),
    },
    env.WI_SLACK_PAYLOAD_KEY,
    cryptoImpl,
  );
  let dispatched = false;
  try {
    dispatched = await dispatchGitHub(env, encryptedJob, fetchImpl);
  } catch {
    dispatched = false;
  }
  if (!dispatched) {
    return slackResponse("Kunne ikke starte undersøkelsen. Prøv igjen om litt.");
  }
  return slackResponse(
    `Undersøkelsen er startet. Referanse: \`${requestId}\`. Resultatet kommer privat.`,
  );
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
};
