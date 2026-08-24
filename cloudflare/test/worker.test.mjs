import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  decryptJob,
  handleRequest,
  signSlackBody,
} from "../src/worker.mjs";

const NOW = 1_800_000_000_000;
const PAYLOAD_KEY = Buffer.from([...Array(32).keys()]).toString("base64url");
const ENV = {
  SLACK_SIGNING_SECRET: "slack-signing-secret-for-test",
  SLACK_TEAM_ID: "T123TEST",
  SLACK_ALLOWED_USER_IDS: "U123TEST",
  GITHUB_ACTIONS_TOKEN: "github-actions-token-for-test",
  WI_SLACK_PAYLOAD_KEY: PAYLOAD_KEY,
  GITHUB_OWNER: "test-owner",
  GITHUB_REPO: "test-repository",
  GITHUB_WORKFLOW: "slack-investigate.yml",
  GITHUB_REF: "main",
};

test("receiver and Python engine share the same encrypted payload format", async () => {
  const fixtureUrl = new URL("../../tests/fixtures/cloud_slack_interop.json", import.meta.url);
  const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const payload = await decryptJob(fixture.token, fixture.key);
  assert.deepEqual(payload, fixture.payload);
});

async function slackRequest(overrides = {}, signature = null) {
  const fields = new URLSearchParams({
    team_id: "T123TEST",
    user_id: "U123TEST",
    channel_id: "C123TEST",
    command: "/undersok",
    text: "https://example.com",
    ...overrides,
  });
  const body = fields.toString();
  const timestamp = String(Math.floor(NOW / 1000));
  const signed = signature || (await signSlackBody(ENV.SLACK_SIGNING_SECRET, timestamp, body));
  return new Request("https://receiver.test/slack/commands", {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "x-slack-request-timestamp": timestamp,
      "x-slack-signature": signed,
    },
    body,
  });
}

test("valid Slack command dispatches only encrypted target data", async () => {
  let githubRequest;
  const fetchImpl = async (url, options) => {
    githubRequest = { url, options };
    return new Response(null, { status: 204 });
  };

  const response = await handleRequest(await slackRequest(), ENV, {
    fetchImpl,
    now: () => NOW,
  });

  assert.equal(response.status, 200);
  assert.match((await response.json()).text, /Resultatet kommer privat/);
  assert.equal(githubRequest.options.headers.authorization, `Bearer ${ENV.GITHUB_ACTIONS_TOKEN}`);
  assert.equal(githubRequest.options.body.includes("example.com"), false);
  const dispatch = JSON.parse(githubRequest.options.body);
  const payload = await decryptJob(dispatch.inputs.job, PAYLOAD_KEY);
  assert.equal(payload.url, "https://example.com");
  assert.equal(payload.team_id, "T123TEST");
  assert.match(payload.request_id, /^\d{8}T\d{6}Z-[0-9a-f]{10}$/);
});

test("invalid Slack signature is rejected before GitHub dispatch", async () => {
  let dispatched = false;
  const response = await handleRequest(await slackRequest({}, `v0=${"0".repeat(64)}`), ENV, {
    fetchImpl: async () => {
      dispatched = true;
      return new Response(null, { status: 204 });
    },
    now: () => NOW,
  });
  assert.equal(response.status, 401);
  assert.equal(dispatched, false);
});

test("wrong workspace is rejected", async () => {
  const response = await handleRequest(await slackRequest({ team_id: "TOTHER1" }), ENV, {
    fetchImpl: async () => new Response(null, { status: 204 }),
    now: () => NOW,
  });
  assert.equal(response.status, 403);
});

test("user outside the private allowlist cannot dispatch", async () => {
  let dispatched = false;
  const response = await handleRequest(await slackRequest({ user_id: "UOTHER1" }), ENV, {
    fetchImpl: async () => {
      dispatched = true;
      return new Response(null, { status: 204 });
    },
    now: () => NOW,
  });
  assert.equal(response.status, 200);
  assert.match((await response.json()).text, /ikke tilgang/);
  assert.equal(dispatched, false);
});

test("help is private and does not dispatch", async () => {
  let dispatched = false;
  const response = await handleRequest(await slackRequest({ text: "hjelp" }), ENV, {
    fetchImpl: async () => {
      dispatched = true;
      return new Response(null, { status: 204 });
    },
    now: () => NOW,
  });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.response_type, "ephemeral");
  assert.equal(dispatched, false);
});

test("GitHub failure returns a private generic error", async () => {
  const response = await handleRequest(await slackRequest(), ENV, {
    fetchImpl: async () => new Response(null, { status: 403 }),
    now: () => NOW,
  });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.doesNotMatch(body.text, /example/);
});

test("missing secrets fail closed", async () => {
  const response = await handleRequest(await slackRequest(), { ...ENV, SLACK_TEAM_ID: "" }, {
    fetchImpl: async () => new Response(null, { status: 204 }),
    now: () => NOW,
  });
  assert.equal(response.status, 503);
});
