import { Navigate, Outlet, useLocation } from "react-router-dom";

import { LoadingScreen } from "./LoadingScreen";
import { useAuth } from "./auth-context";

/** Pages inside this route need a signed-in user. Others are sent to the login page. */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <LoadingScreen />;
  if (status === "anonymous") {
    // Remember where the user wanted to go, to return there after login.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}
