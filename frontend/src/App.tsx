import { useEffect, useState } from "react";
import { Avatar, Button, Layout, Menu, Tag, Tooltip, Typography } from "antd";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";
import type { User } from "./types";
import Icon, { Logo } from "./components/Icon";
import Login from "./components/Login";
import RequestList from "./components/RequestList";
import RequestView from "./components/RequestView";
import NewRequestForm from "./components/NewRequestForm";
import Analytics from "./components/Analytics";
import ImportEpisodes from "./components/ImportEpisodes";

type Page = "requests" | "new" | "analytics" | "import";

// Sidebar links per role. The API enforces the same limits; this only decides what to show.
const NAV: Record<User["role"], { page: Page; label: string; icon: "list" | "plus" | "chart" | "upload" }[]> = {
  client: [
    { page: "requests", label: "My requests", icon: "list" },
    { page: "new", label: "New request", icon: "plus" },
  ],
  operator: [
    { page: "requests", label: "All requests", icon: "list" },
    { page: "analytics", label: "Analytics", icon: "chart" },
    { page: "import", label: "Import episodes", icon: "upload" },
  ],
  admin: [
    { page: "requests", label: "All requests", icon: "list" },
    { page: "analytics", label: "Analytics", icon: "chart" },
    { page: "import", label: "Import episodes", icon: "upload" },
  ],
};

const ROLE_COLORS = { client: "blue", operator: "green", admin: "purple" };

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingToken, setCheckingToken] = useState(true);
  const [page, setPage] = useState<Page>("requests");
  // When set, the requests page shows this one request instead of the list.
  const [openRequestId, setOpenRequestId] = useState<number | null>(null);

  function logout() {
    setToken(null);
    setUser(null);
    setPage("requests");
    setOpenRequestId(null);
  }

  function go(next: Page) {
    setPage(next);
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

  const nav = NAV[user.role];
  const title = openRequestId !== null ? `Request #${openRequestId}` : nav.find((n) => n.page === page)?.label;

  return (
    <Layout className="shell">
      <Layout.Sider width={248} breakpoint="lg" collapsedWidth={0} className="sidebar">
        <div className="sidebar-inner">
          <div className="sidebar-brand" onClick={() => go("requests")}>
            <Logo />
            <span>
              Dataset
              <br />
              Request Desk
            </span>
          </div>

          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[page]}
            onClick={(item) => go(item.key as Page)}
            items={nav.map((item) => ({
              key: item.page,
              label: item.label,
              // "anticon" is the class Ant Design uses to space a menu icon from its label.
              icon: (
                <span className="anticon">
                  <Icon name={item.icon} />
                </span>
              ),
            }))}
          />

          <div className="sidebar-user">
            <Avatar className="avatar">{user.name.charAt(0)}</Avatar>
            <div className="sidebar-user-text">
              <span className="sidebar-user-name">{user.name}</span>
              <Tag color={ROLE_COLORS[user.role]} className="role-tag">
                {user.role}
              </Tag>
            </div>
            <Tooltip title="Log out">
              <Button type="text" className="logout" onClick={logout} aria-label="Log out" icon={<Icon name="logout" />} />
            </Tooltip>
          </div>
        </div>
      </Layout.Sider>

      <Layout>
        <Layout.Header className="topbar">
          <Typography.Title level={3} className="topbar-title">
            {title}
          </Typography.Title>
          <Typography.Text type="secondary">{user.organisation ?? user.email}</Typography.Text>
        </Layout.Header>
        <Layout.Content className="content">
          {page === "requests" && openRequestId === null && <RequestList user={user} onOpen={setOpenRequestId} />}
          {page === "requests" && openRequestId !== null && (
            <RequestView user={user} requestId={openRequestId} onBack={() => setOpenRequestId(null)} />
          )}
          {page === "new" && <NewRequestForm onCreated={() => go("requests")} />}
          {page === "analytics" && <Analytics />}
          {page === "import" && <ImportEpisodes />}
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
