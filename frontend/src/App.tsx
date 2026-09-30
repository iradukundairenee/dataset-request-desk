import { useEffect, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";
import type { User } from "./types";
import Login from "./components/Login";
import RequestList from "./components/RequestList";
import RequestView from "./components/RequestView";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingToken, setCheckingToken] = useState(true);
  // null = the request list; a number = that request's page.
  const [openRequestId, setOpenRequestId] = useState<number | null>(null);

  function logout() {
    setToken(null);
    setUser(null);
    setOpenRequestId(null);
  }

  // On page load, if a token is saved, ask the API who we are.
  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!getToken()) {
      setCheckingToken(false);
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setCheckingToken(false));
  }, []);

  if (checkingToken) return null;
  if (!user) return <Login onLoggedIn={setUser} />;

  return (
    <div className="app">
      <header>
        <strong className="brand" onClick={() => setOpenRequestId(null)}>
          Dataset Request Desk
        </strong>
        <span className="who">
          {user.name} · <span className="role">{user.role}</span>
          <button className="link" onClick={logout}>
            Log out
          </button>
        </span>
      </header>
      <main>
        {openRequestId === null ? (
          <RequestList user={user} onOpen={setOpenRequestId} />
        ) : (
          <RequestView user={user} requestId={openRequestId} onBack={() => setOpenRequestId(null)} />
        )}
      </main>
    </div>
  );
}
