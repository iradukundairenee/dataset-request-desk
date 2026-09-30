import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";
import "@fontsource-variable/inter";
import App from "./App";
import "./styles.css";

// One place for the look: font, size, colours, corners. Ant Design components read these tokens.
const theme = {
  token: {
    fontFamily: "'Inter Variable', system-ui, -apple-system, 'Segoe UI', sans-serif",
    fontSize: 15,
    colorPrimary: "#4f46e5",
    borderRadius: 8,
    colorBgLayout: "#f4f6fa",
  },
  components: {
    Layout: { siderBg: "#0f172a", headerBg: "#ffffff", headerHeight: 64 },
    Menu: { darkItemBg: "#0f172a", darkItemSelectedBg: "#4f46e5", itemHeight: 44 },
    Table: { headerBg: "#f8fafc", cellPaddingBlock: 14 },
  },
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider theme={theme}>
      {/* AntApp gives components access to message/modal with the theme applied. */}
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
);
