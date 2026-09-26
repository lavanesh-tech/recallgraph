// Offline UI tests: fetch is mocked with SYNTHETIC responses.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { AuthProvider } from "../auth/AuthContext.jsx";

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

function mockFetch(handler) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const { status = 200, body } = handler(new URL(url), init);
    return new Response(JSON.stringify(body), { status });
  });
}

describe("search", () => {
  it("shows results with the official-data disclaimer", async () => {
    const fetchMock = mockFetch(() => ({
      body: {
        total: 1,
        items: [{ id: 7, title: "SYNTHETIC Acme Air Fryer recall", source: "cpsc", recall_date: "2026-01-02" }],
        disclaimer: "SYNTHETIC disclaimer: no match does not mean safe.",
      },
    }));
    renderApp();
    await userEvent.type(screen.getByLabelText("Keywords"), "air fryer");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("link", { name: /SYNTHETIC Acme/ })).toHaveAttribute("href", "/recalls/7");
    expect(screen.getByRole("note")).toHaveTextContent("no match does not mean safe");
    expect(fetchMock.mock.calls[0][0].toString()).toContain("q=air+fryer");
  });

  it("never presents an empty result as safe", async () => {
    mockFetch(() => ({ body: { total: 0, items: [], disclaimer: "d" } }));
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText(/does not mean the product is safe/)).toBeInTheDocument();
  });

  it("shows API problem details", async () => {
    mockFetch(() => ({ status: 422, body: { title: "Unprocessable", detail: "SYNTHETIC bad filter" } }));
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("SYNTHETIC bad filter");
  });
});

describe("auth", () => {
  it("signs in and keeps the token in memory only", async () => {
    const fetchMock = mockFetch(() => ({ body: { access_token: "SYNTHETIC.jwt", token_type: "bearer" } }));
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("a@example.com")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      email: "a@example.com",
      password: "correct horse battery",
    });
    expect(setItem).not.toHaveBeenCalled();
  });
});
