import { Navigate, Route, Routes } from 'react-router-dom'

import { RouteFocus } from './RouteFocus'
import { AppShell } from '../components/AppShell'
import { GuestOnly } from '../features/auth/GuestOnly'
import { RequireAuth } from '../features/auth/RequireAuth'
import { AnalysisPage } from '../pages/AnalysisPage'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { ProjectPage } from '../pages/ProjectPage'
import { ProfilePage } from '../pages/ProfilePage'
import { ProjectsPage } from '../pages/ProjectsPage'
import { RegisterPage } from '../pages/RegisterPage'

export function AppRoutes() {
  return (
    <>
      <RouteFocus />
      <Routes>
        <Route element={<GuestOnly />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<ProjectPage />} />
            <Route path="/projects/:projectId/analysis" element={<AnalysisPage />} />
            <Route path="/profile" element={<ProfilePage />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/projects" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  )
}
