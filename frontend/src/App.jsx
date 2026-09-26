import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import InventoryPage from "./pages/InventoryPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import MatchPage from "./pages/MatchPage.jsx";
import RecallPage from "./pages/RecallPage.jsx";
import SearchPage from "./pages/SearchPage.jsx";

export function RequireAuth({ children }) {
  const { session } = useAuth();
  return session ? children : <Navigate to="/login" replace />;
}

export default function App() {
  const { session, logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          RecallGraph
        </Link>
        <nav>
          <Link to="/">Search</Link>
          <Link to="/check">Check a product</Link>
          {session && (
            <>
              <Link to="/inventory">My products</Link>
              <Link to="/alerts">Alerts</Link>
            </>
          )}
          {session ? (
            <>
              <span className="muted">{session.email}</span>
              <button className="link" onClick={logout}>
                Sign out
              </button>
            </>
          ) : (
            <Link to="/login">Sign in</Link>
          )}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/recalls/:id" element={<RecallPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/check" element={<MatchPage />} />
          <Route
            path="/inventory"
            element={
              <RequireAuth>
                <InventoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/alerts"
            element={
              <RequireAuth>
                <AlertsPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  );
}
