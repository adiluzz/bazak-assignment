import { XProvider } from "@ant-design/x";
import { Button } from "antd";
import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { GuidePage } from "./guide/GuidePage";
import { ChatPage } from "./routes/ChatPage";
import { appTheme } from "./theme";

export function App() {
  const [dark, setDark] = useState(() => window.localStorage.getItem("shop-theme") !== "light");
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);
  function toggle() {
    const next = !dark;
    setDark(next);
    window.localStorage.setItem("shop-theme", next ? "dark" : "light");
  }
  return (
    <XProvider theme={appTheme(dark)}>
      <Button className="theme-toggle" onClick={toggle}>
        {dark ? "Light" : "Dark"}
      </Button>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ChatPage />}>
            <Route index element={null} />
            <Route path="c/:conversationId" element={null} />
          </Route>
          <Route path="/guide" element={<GuidePage />} />
        </Routes>
      </BrowserRouter>
    </XProvider>
  );
}
