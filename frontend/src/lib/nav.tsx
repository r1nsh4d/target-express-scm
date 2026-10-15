/* The one navigation map.
 *
 * The rail renders it, the top bar reads the current entry's description from
 * it, and the command palette searches it. Kept in one place so a screen can
 * never exist in the menu but not in search, or be reachable by someone whose
 * role should not see it. */

import {
  BarChart3,
  BookOpen,
  Bookmark,
  Building2,
  FileText,
  HandCoins,
  Landmark,
  HardHat,
  LayoutDashboard,
  MessageSquare,
  Package,
  PackageX,
  PhoneCall,
  ReceiptIndianRupee,
  ReceiptText,
  Route,
  ShieldCheck,
  ScanBarcode,
  Sofa,
  Truck,
  UserRound,
  Users,
  Wand2,
  Wallet,
} from 'lucide-react'
import type { ReactNode } from 'react'

import type { UserRole } from '@/lib/auth'

export interface NavItem {
  to: string
  label: string
  /** Shown under the page title in the top bar, so every screen says what it is
   *  for. Also the secondary line in the command palette, and the text the
   *  palette searches after the label. */
  blurb: string
  icon: ReactNode
  roles: UserRole[]
  group: number
  /** Extra words people might type in the palette that are not in the label —
   *  the client's vocabulary, and the obvious synonyms. */
  keywords?: string
}

const ALL_BACK_OFFICE: UserRole[] = [
  'SUPER_ADMIN',
  'OPS_ADMIN',
  'WAREHOUSE_ADMIN',
  'ACCOUNTS',
  'STAKEHOLDER',
]
const OPS: UserRole[] = ['SUPER_ADMIN', 'OPS_ADMIN', 'WAREHOUSE_ADMIN']
const ADMIN: UserRole[] = ['SUPER_ADMIN', 'OPS_ADMIN']
const MONEY: UserRole[] = ['SUPER_ADMIN', 'ACCOUNTS']

const ICON = 'size-4 shrink-0'

/* The rail, in sections that fold.
 *
 * Twenty-six items were all on screen at once, and a menu that long is one
 * nobody reads — the eye gives up and people navigate by memory or not at
 * all. Most of them are things you touch once when setting up a vendor and
 * never again.
 *
 * So only the day's work is open. Money, setup and administration fold away,
 * and the section holding the screen you are on opens itself, so nothing is
 * ever hidden from somebody who is already looking at it.
 */
export const SECTIONS: { group: number; label: string; openByDefault: boolean }[] = [
  { group: 1, label: 'Every day', openByDefault: true },
  { group: 3, label: 'Money', openByDefault: false },
  { group: 2, label: 'Set up', openByDefault: false },
  { group: 4, label: 'Admin', openByDefault: false },
]

export const NAV_GROUPS: Record<number, string> = {
  1: 'Operations',
  2: 'Masters',
  3: 'Money',
  4: 'Settings',
}

/* "Freight" is the client's own word for a delivery run, so it is the word the
   product uses everywhere. "Trip" is kept as a palette keyword only, because
   that is what their old paper books say. */
export const NAV: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', blurb: "Today's operations at a glance", icon: <LayoutDashboard className={ICON} />, roles: ALL_BACK_OFFICE, group: 1, keywords: 'home overview summary' },
  { to: '/freights', label: 'Freights', blurb: 'Delivery runs — one warehouse out, many points, back again', icon: <Route className={ICON} />, roles: ALL_BACK_OFFICE, group: 1, keywords: 'trips runs lr dispatch' },
  { to: '/day-sheet', label: 'Day sheet', blurb: "Type the day's bills and create everything in one go", icon: <Wand2 className={ICON} />, roles: OPS, group: 1, keywords: 'bulk entry paste quick add morning import smart' },
  { to: '/consignments', label: 'Consignments', blurb: 'Vendor bills and the boxes against them', icon: <Package className={ICON} />, roles: OPS, group: 1, keywords: 'bills boxes inward' },
  { to: '/route-presets', label: 'Saved routes', blurb: 'The rounds you already run — pick one and the whole trip is filled in', icon: <Bookmark className={ICON} />, roles: OPS, group: 1, keywords: 'presets rounds no 11 template recurring' },
  { to: '/labels', label: 'Sorting & labels', blurb: 'Sort boxes by point and print the stickers', icon: <ScanBarcode className={ICON} />, roles: OPS, group: 1, keywords: 'print stickers barcode sort' },

  { to: '/returns', label: 'Returns', blurb: 'Cartons that came back, and why', icon: <PackageX className={ICON} />, roles: OPS, group: 1, keywords: 'rto refused damaged not delivered came back' },
  { to: '/vendors', label: 'Vendors', blurb: 'Vendors, their divisions, warehouses and rates', icon: <Building2 className={ICON} />, roles: ADMIN, group: 2, keywords: 'clients godrej divisions godown warehouse' },
  { to: '/consignees', label: 'Customers', blurb: 'Delivery points — customers and distribution centres', icon: <Users className={ICON} />, roles: OPS, group: 2, keywords: 'consignees points dealers' },
  { to: '/vehicles', label: 'Vehicles', blurb: 'Owned and rented vehicles, and who gets paid', icon: <Truck className={ICON} />, roles: ADMIN, group: 2, keywords: 'trucks lorry fleet owners' },
  { to: '/market-vehicles', label: 'Market vehicles', blurb: 'Lorries you can hire in — who to call, and what we paid them last', icon: <PhoneCall className={ICON} />, roles: OPS, group: 2, keywords: 'hire rent broker owner phonebook contacts outside' },
  { to: '/drivers', label: 'Drivers', blurb: 'Drivers, their logins and their pay terms', icon: <UserRound className={ICON} />, roles: ADMIN, group: 2, keywords: 'staff licence' },
  { to: '/labour', label: 'Loading crew', blurb: 'The helpers who load at the godown', icon: <HardHat className={ICON} />, roles: OPS, group: 2, keywords: 'helpers labour loaders' },
  { to: '/categories', label: 'Goods categories', blurb: 'Spare parts, furniture — what decides whether unloading is billed', icon: <Package className={ICON} />, roles: ADMIN, group: 2, keywords: 'divisions spare parts furniture' },

  { to: '/rate-cards', label: 'Rate cards', blurb: 'What each vendor division is charged, by date', icon: <ReceiptIndianRupee className={ICON} />, roles: [...ADMIN, 'ACCOUNTS'], group: 3, keywords: 'pricing tariff rates' },
  { to: '/unloading-rates', label: 'Unloading rates', blurb: 'What the vendor pays per article, and what the driver is paid', icon: <Sofa className={ICON} />, roles: [...ADMIN, 'ACCOUNTS'], group: 3, keywords: 'articles floors chair table driver pay margin coolie' },
  { to: '/invoices', label: 'Vendor invoices', blurb: 'Bill completed freights to vendors', icon: <FileText className={ICON} />, roles: MONEY, group: 3, keywords: 'billing gst tax bill' },
  { to: '/money-in', label: 'Money in', blurb: 'Payments received from vendors, against each invoice', icon: <Landmark className={ICON} />, roles: MONEY, group: 3, keywords: 'payments received collection receipts tds bank credit' },
  { to: '/settlements', label: 'Settlements', blurb: 'Pay drivers and vehicle owners', icon: <Wallet className={ICON} />, roles: MONEY, group: 3, keywords: 'payout payments salary hire' },
  { to: '/advances', label: 'Advances', blurb: 'Cash handed over before a settlement, and its recovery', icon: <HandCoins className={ICON} />, roles: MONEY, group: 3, keywords: 'cash loan recovery' },
  { to: '/reports', label: 'Reports', blurb: 'What the business did, over a period', icon: <BarChart3 className={ICON} />, roles: [...MONEY, 'STAKEHOLDER'], group: 3, keywords: 'analytics summary month revenue margin performance' },
  { to: '/expenses', label: 'Expenses', blurb: 'What drivers paid on the road, waiting for a decision', icon: <ReceiptText className={ICON} />, roles: [...MONEY, 'OPS_ADMIN'], group: 3, keywords: 'diesel toll claims approve' },

  { to: '/enquiries', label: 'Enquiries', blurb: 'Businesses who asked to work with Target Express', icon: <MessageSquare className={ICON} />, roles: ADMIN, group: 4, keywords: 'leads contact sales website' },
  { to: '/roles', label: 'Roles', blurb: 'What each kind of user may reach', icon: <ShieldCheck className={ICON} />, roles: ADMIN, group: 4, keywords: 'permissions privileges access rights' },
  { to: '/users', label: 'Users', blurb: 'Logins, roles and who can see earnings', icon: <Users className={ICON} />, roles: ADMIN, group: 4, keywords: 'accounts permissions roles' },
  { to: '/guide', label: 'User guide', blurb: 'The full cycle, in the order it has to be done', icon: <BookOpen className={ICON} />, roles: ALL_BACK_OFFICE, group: 4, keywords: 'help how to manual training' },
]

/** Longest matching prefix wins, so /freights/:id still resolves to "Freights". */
export function currentNav(pathname: string): NavItem | undefined {
  return [...NAV]
    .sort((a, b) => b.to.length - a.to.length)
    .find((n) => pathname === n.to || pathname.startsWith(`${n.to}/`))
}

/* Which screens this person sees.
 *
 * A custom role brings its own list, and it wins — that is the whole point of
 * being able to make one. The built-in role's list is the fallback, so
 * somebody who is not on a custom role sees exactly what they always did.
 *
 * `screens` are keyed by the path without its slash, which is what the server
 * sends back from /me/access. */
export function navForAccess(
  role: UserRole | undefined,
  screens: string[] | undefined,
): NavItem[] {
  if (screens && screens.length) {
    const allowed = new Set(screens)
    return NAV.filter((item) => allowed.has(item.to.replace(/^\//, '')))
  }
  return navFor(role)
}

export function navFor(role: UserRole | undefined): NavItem[] {
  if (!role) return []
  return NAV.filter((item) => item.roles.includes(role))
}
