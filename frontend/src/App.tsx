import { Navigate, Route, Routes } from 'react-router-dom'

import AppShell from '@/components/AppShell'
import { Spinner } from '@/components/ui'
import { homePathForRole, useAuth } from '@/lib/auth'
import type { UserRole } from '@/lib/auth'
import DashboardPage from '@/pages/DashboardPage'
import DriverPortalPage from '@/pages/DriverPortalPage'
import AdvancesPage from '@/pages/AdvancesPage'
import ConsignmentsPage from '@/pages/ConsignmentsPage'
import ExpensesPage from '@/pages/ExpensesPage'
import GuidePage from '@/pages/GuidePage'
import InvoicesPage from '@/pages/InvoicesPage'
import LabelsPage from '@/pages/LabelsPage'
import MarketVehiclesPage from '@/pages/MarketVehiclesPage'
import RoutePresetsPage from '@/pages/RoutePresetsPage'
import SettlementsPage from '@/pages/SettlementsPage'
import TrackFindPage from '@/pages/TrackFindPage'
import TrackPage from '@/pages/TrackPage'
import EnquiriesPage from '@/pages/EnquiriesPage'
import UsersPage from '@/pages/UsersPage'
import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import TripDetailPage from '@/pages/TripDetailPage'
import TripsPage from '@/pages/TripsPage'
import CategoriesPage from '@/pages/masters/CategoriesPage'
import CustomersPage from '@/pages/masters/CustomersPage'
import LabourPage from '@/pages/masters/LabourPage'
import UnloadingRatesPage from '@/pages/masters/UnloadingRatesPage'
import DriversPage from '@/pages/masters/DriversPage'
import RateCardsPage from '@/pages/masters/RateCardsPage'
import VehiclesPage from '@/pages/masters/VehiclesPage'
import VendorsPage from '@/pages/masters/VendorsPage'

function FullScreenLoader() {
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <Spinner className="size-6" />
    </div>
  )
}

/** Gate every authenticated route, and keep drivers out of the office screens. */
function Protected({ allow, children }: { allow?: UserRole[]; children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <FullScreenLoader />
  if (!user) return <Navigate to="/login" replace />
  if (allow && !allow.includes(user.role)) {
    return <Navigate to={homePathForRole(user.role)} replace />
  }
  return <>{children}</>
}

function LoginRoute() {
  const { user, loading } = useAuth()
  if (loading) return <FullScreenLoader />
  if (user) return <Navigate to={homePathForRole(user.role)} replace />
  return <LoginPage />
}

const BACK_OFFICE: UserRole[] = [
  'SUPER_ADMIN',
  'OPS_ADMIN',
  'WAREHOUSE_ADMIN',
  'ACCOUNTS',
  'STAKEHOLDER',
]

export default function App() {
  return (
    <Routes>
      {/* The public face. The console starts at /dashboard. */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginRoute />} />
      {/* Public, and in this order. /track is the front door a customer finds
          from the landing page; /track/:token is the link they were sent, where
          the token itself is the credential. */}
      <Route path="/track" element={<TrackFindPage />} />
      <Route path="/track/:token" element={<TrackPage />} />

      <Route
        path="/driver"
        element={
          <Protected allow={['DRIVER']}>
            <DriverPortalPage />
          </Protected>
        }
      />

      <Route
        element={
          <Protected allow={BACK_OFFICE}>
            <AppShell />
          </Protected>
        }
      >
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="guide" element={<GuidePage />} />
        <Route path="categories" element={<CategoriesPage />} />
        <Route path="freights" element={<TripsPage />} />
        <Route path="freights/:id" element={<TripDetailPage />} />
        <Route path="vendors" element={<VendorsPage />} />
        <Route path="rate-cards" element={<RateCardsPage />} />
        <Route path="vehicles" element={<VehiclesPage />} />
        <Route path="drivers" element={<DriversPage />} />
        <Route path="consignees" element={<CustomersPage />} />
        <Route path="consignments" element={<ConsignmentsPage />} />
        <Route path="labels" element={<LabelsPage />} />
        <Route path="route-presets" element={<RoutePresetsPage />} />
        <Route path="market-vehicles" element={<MarketVehiclesPage />} />
        <Route path="invoices" element={<InvoicesPage />} />
        <Route path="settlements" element={<SettlementsPage />} />
        <Route path="advances" element={<AdvancesPage />} />
        <Route path="expenses" element={<ExpensesPage />} />
        <Route path="unloading-rates" element={<UnloadingRatesPage />} />
        <Route path="labour" element={<LabourPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="enquiries" element={<EnquiriesPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
