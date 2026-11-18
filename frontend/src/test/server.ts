import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import {
  API,
  CONV_A,
  CONV_B,
  conversation,
  models,
  project,
  PROJECT_ID,
  providers,
} from "./fixtures";

/** Answers every request the shell makes on its own, so each test adds only what it tests. */
export const defaultHandlers = [
  http.get(`${API}/health`, () => HttpResponse.json({ status: "ok", database: "up" })),
  http.get(`${API}/api/v1/projects`, () => HttpResponse.json([project])),
  http.get(`${API}/api/v1/projects/${PROJECT_ID}`, () => HttpResponse.json(project)),
  http.get(`${API}/api/v1/models`, () => HttpResponse.json(models)),
  http.get(`${API}/api/v1/providers`, () => HttpResponse.json(providers)),
  http.get(`${API}/api/v1/usage/records`, () => HttpResponse.json([])),
  http.get(`${API}/api/v1/projects/${PROJECT_ID}/conversations`, () =>
    HttpResponse.json([conversation(CONV_A, "First chat"), conversation(CONV_B, "Second chat")]),
  ),
  http.get(`${API}/api/v1/projects/${PROJECT_ID}/memory`, () =>
    HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 }),
  ),
  http.get(`${API}/api/v1/conversations/:id`, ({ params }) =>
    HttpResponse.json(conversation(String(params.id), "Chat")),
  ),
  http.get(`${API}/api/v1/conversations/:id/messages`, () => HttpResponse.json([])),
];

export const server = setupServer(...defaultHandlers);
