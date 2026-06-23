import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AuthProvider } from "./features/auth/AuthContext";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { ForbiddenPage } from "./pages/ForbiddenPage";
import { LoginPage } from "./pages/LoginPage";
import { MyCapabilitiesPage } from "./pages/MyCapabilitiesPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OperationsMasterPage } from "./pages/OperationsMasterPage";
import { StaffAssignmentsPage } from "./pages/StaffAssignmentsPage";
import { StaffEditPage } from "./pages/StaffEditPage";
import { StaffListPage } from "./pages/StaffListPage";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <ChangePasswordPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/staff" replace />} />
          <Route path="staff" element={<StaffListPage />} />
          <Route path="staff/new" element={<StaffEditPage mode="create" />} />
          <Route path="staff/:id" element={<StaffEditPage mode="edit" />} />
          <Route path="operations/locations" element={<OperationsMasterPage resource="locations" />} />
          <Route path="operations/work-areas" element={<OperationsMasterPage resource="work-areas" />} />
          <Route path="operations/work-categories" element={<OperationsMasterPage resource="work-categories" />} />
          <Route path="operations/work-types" element={<OperationsMasterPage resource="work-types" />} />
          <Route path="operations/work-type-availabilities" element={<OperationsMasterPage resource="work-type-availabilities" />} />
          <Route path="operations/staff-locations" element={<StaffAssignmentsPage resource="staff-locations" />} />
          <Route path="operations/staff-capabilities" element={<StaffAssignmentsPage resource="staff-capabilities" />} />
          <Route path="operations/my-staff-locations" element={<MyCapabilitiesPage section="locations" />} />
          <Route path="operations/my-capabilities" element={<MyCapabilitiesPage />} />
          <Route path="403" element={<ForbiddenPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthProvider>
  );
}
