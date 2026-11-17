import { Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./auth/ProtectedRoute";
import { PublicOnlyRoute } from "./auth/PublicOnlyRoute";
import { AppShell } from "./components/layout/AppShell";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { Monitors } from "./pages/Monitors";
import { NotFound } from "./pages/NotFound";
import { Register } from "./pages/Register";
import { StyleGuide } from "./pages/StyleGuide";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/monitors" element={<Monitors />} />
        </Route>
      </Route>
      <Route path="/styleguide" element={<StyleGuide />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
