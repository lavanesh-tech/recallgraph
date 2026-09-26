// Offline feature tests: fetch is mocked with SYNTHETIC responses.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { AuthProvider } from "../auth/AuthContext.jsx";

const MATCH = {
  engine_version: "match-2",
  candidates_considered: 3,
  disclaimer: "SYNTHETIC match disclaimer",
  matches: [
    {
      tier: "identifier_match",
      score: 0.91,
      recall: { id: 7, title: "SYNTHETIC Acme Air Fryer recall", recall_date: "2026-01-02" },
      signals: [
        { name: "identifier", applicable: true, weight: 0.4, value: 1, contribution: 0.4, evidence: ["AF-100X"] },
        { name: "date", applicable: false, weight: 0.05, value: 0, contribution: 0, evidence: [] },
      ],
    },
  ],
};

function mockApi(routes) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init = {}) => {
    const { pathname } = new URL(url);
    const key = `${init.method || "GET"} ${pathname}`;
    const route = routes[key];
    if (!route) return new Response(JSON.stringify({ detail: `unmocked ${key}` }), { status: 500 });
    const { status = 200, body = null } = typeof route === "function" ? route(init) : route;
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  });
}

const LOGIN = { "POST /api/v1/auth/login": { body: { access_token: "SYNTHETIC.jwt" } } };

async function signIn() {
  await userEvent.click(screen.getByRole("link", { name: "Sign in" }));
  await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByText("a@example.com");
}

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("check a product", () => {
  it("shows tier, score and the signals that explain the match", async () => {
    const fetchMock = mockApi({ "POST /api/v1/match": { body: MATCH } });
    renderApp("/check");
    await userEvent.type(screen.getByLabelText("Model"), "AF-100X");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(await screen.findByText("Identifier match")).toBeInTheDocument();
    expect(screen.getByText("AF-100X")).toBeInTheDocument();
    expect(screen.queryByText("date")).not.toBeInTheDocument(); // non-applicable hidden
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ model: "AF-100X", limit: 10 });
  });
});

describe("signed-in features", () => {
  it("redirects anonymous users away from inventory", async () => {
    mockApi({});
    renderApp("/inventory");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("adds an inventory item and checks it for recalls", async () => {
    const items = [];
    mockApi({
      ...LOGIN,
      "GET /api/v1/inventory": () => ({ body: { items, total: items.length } }),
      "POST /api/v1/inventory": (init) => {
        items.push({ id: "i1", ...JSON.parse(init.body) });
        return { status: 201, body: items[0] };
      },
      "GET /api/v1/inventory/i1/matches": { body: MATCH },
    });
    renderApp();
    await signIn();
    await userEvent.click(screen.getByRole("link", { name: "My products" }));
    await userEvent.type(screen.getByLabelText("Nickname"), "Kitchen fryer");
    await userEvent.type(screen.getByLabelText("Model"), "AF-100X");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await userEvent.click(await screen.findByRole("button", { name: "Check recalls" }));

    expect(await screen.findByRole("link", { name: /SYNTHETIC Acme/ })).toBeInTheDocument();
  });

  it("lists radar alerts and marks them read", async () => {
    let unread = 1;
    const alerts = () => ({
      body: {
        total: 1,
        unread,
        disclaimer: "SYNTHETIC",
        items: [
          {
            id: "a1",
            tier: "likely",
            read_at: unread ? null : "2026-09-26T00:00:00Z",
            item: { id: "i1", nickname: "Kitchen fryer" },
            recall: { id: 7, title: "SYNTHETIC Acme Air Fryer recall" },
          },
        ],
      },
    });
    mockApi({
      ...LOGIN,
      "GET /api/v1/radar/alerts": alerts,
      "POST /api/v1/radar/alerts/a1/read": () => {
        unread = 0;
        return { status: 204 };
      },
    });
    renderApp();
    await signIn();
    await userEvent.click(screen.getByRole("link", { name: "Alerts" }));
    expect(await screen.findByText(/1 unread of 1/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Mark read/ }));

    expect(await screen.findByText(/0 unread of 1/)).toBeInTheDocument();
  });
});

describe("explanations", () => {
  it("shows cited points next to their evidence", async () => {
    mockApi({
      ...LOGIN,
      "GET /api/v1/recalls": {
        body: { total: 1, items: [{ id: 7, title: "SYNTHETIC Acme recall", source: "cpsc" }] },
      },
      "GET /api/v1/recalls/7": {
        body: { id: 7, title: "SYNTHETIC Acme recall", products: [], hazards: [], remedies: [] },
      },
      "POST /api/v1/recalls/7/explanation": {
        body: {
          mode: "template",
          model: null,
          summary: "SYNTHETIC Acme recall",
          insufficient_evidence: false,
          points: [{ text: "Hazard: overheating", citations: ["E3"] }],
          evidence: [{ id: "E3", kind: "hazard", text: "overheating" }],
          disclaimer: "not a safety assessment",
        },
      },
    });
    renderApp();
    await signIn();
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.click(await screen.findByRole("link", { name: "SYNTHETIC Acme recall" }));
    const panel = (await screen.findByRole("heading", { name: "Explain this recall" })).parentElement;
    await userEvent.click(within(panel).getByRole("button", { name: "Explain" }));

    expect(await within(panel).findByText("Hazard: overheating")).toBeInTheDocument();
    expect(within(panel).getByText("[E3]")).toBeInTheDocument();
    expect(within(panel).getByText(/template from official record/)).toBeInTheDocument();
  });

  it("asks anonymous users to sign in", async () => {
    mockApi({
      "GET /api/v1/recalls/7": { body: { id: 7, title: "SYNTHETIC", products: [], hazards: [], remedies: [] } },
    });
    renderApp("/recalls/7");
    expect(await screen.findByText(/to get a plain-language explanation/)).toBeInTheDocument();
  });
});
