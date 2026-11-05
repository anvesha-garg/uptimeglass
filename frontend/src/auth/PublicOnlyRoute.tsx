import { Navigate, Outlet, useLocation } from "react-router-dom";

import { LoadingScreen } from "./LoadingScreen";
import { useAuth } from "./auth-context";

/** Login and register pages. A signed-in user is sent on to the app instead. */
export function PublicOnlyRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <LoadingScreen />;
  if (status === "authenticated") {
    const from = (location.state as { from?: unknown } | null)?.from;
    // Only paths inside this app: "//evil.example" would be an address on another site.
    const target = typeof from === "string" && from.startsWith("/") && !from.startsWith("//") ? from : "/";
    return <Navigate to={target} replace />;
  }
  return <Outlet />;
}
