import {
  Banknote,
  BarChart3,
  Bookmark,
  Building2,
  FileText,
  HandCoins,
  HardHat,
  LayoutDashboard,
  type LucideIcon,
  MessageSquare,
  Package,
  PackageX,
  PhoneCall,
  ReceiptIndianRupee,
  ReceiptText,
  ScanBarcode,
  ShieldCheck,
  Sofa,
  Truck,
  UserRound,
  Users,
  Wallet,
  Wand2,
} from 'lucide-react'

/* Eight things, and everything else inside them.
 *
 * Twenty-six items in the rail is a menu nobody reads: the eye gives up and
 * people navigate by memory, which is exactly what somebody who has never
 * used software before cannot do. And it is a false flatness — Rate cards and
 * Unloading rates are not peers of Dashboard, they are two details of what a
 * vendor is charged.
 *
 * So the rail is the eight things the business is actually made of, and each
 * one opens onto the pieces that belong to it, as tiles. A tile can say what
 * is inside it — eleven vehicles, four needing papers — which a line in a
 * menu cannot, and that is the difference between a list you read and a list
 * you scan.
 *
 * Every screen is still at its own address. Nothing moved; it is the way in
 * that changed.
 */

export interface HubChild {
  to: string
  label: string
  blurb: string
  icon: LucideIcon
  /** Which count from /hub-counts to show on the tile, if any. */
  count?: string
}

export interface Hub {
  to: string
  label: string
  blurb: string
  icon: LucideIcon
  children: HubChild[]
}

export const HUBS: Hub[] = [
  {
    to: '/dashboard',
    label: 'Dashboard',
    blurb: 'What is waiting, and how the month is going',
    icon: LayoutDashboard,
    children: [],
  },
  {
    // Second, not fourth as listed. It is the day's work and everything else
    // here is touched once a month — putting it below Vehicles would cost a
    // click on the one screen that gets opened forty times a day.
    to: '/freights',
    label: 'Freights',
    blurb: "The day's runs, the bills on them and the labels",
    icon: Truck,
    children: [
      {
        to: '/day-sheet',
        label: 'Day sheet',
        blurb: "Type or drop the day's bills and create everything at once",
        icon: Wand2,
      },
      {
        to: '/consignments',
        label: 'Consignments',
        blurb: 'Vendor bills and the boxes against them',
        icon: Package,
        count: 'consignments',
      },
      {
        to: '/labels',
        label: 'Sorting & labels',
        blurb: 'Sort by point, print a sticker per box',
        icon: ScanBarcode,
      },
      {
        to: '/returns',
        label: 'Returns',
        blurb: 'Cartons that came back, and why',
        icon: PackageX,
        count: 'returns',
      },
      {
        to: '/route-presets',
        label: 'Saved routes',
        blurb: 'Rounds that recur, ready to load',
        icon: Bookmark,
        count: 'presets',
      },
    ],
  },
  {
    to: '/vendors',
    label: 'Vendors',
    blurb: 'Who you carry for, what you charge, where it goes',
    icon: Building2,
    children: [
      {
        to: '/consignees',
        label: 'Customers',
        blurb: 'Delivery points, their addresses and pins',
        icon: Users,
        count: 'consignees',
      },
      {
        to: '/rate-cards',
        label: 'Rate cards',
        blurb: 'What each division is charged per trip',
        icon: ReceiptIndianRupee,
        count: 'rate_cards',
      },
      {
        to: '/unloading-rates',
        label: 'Unloading rates',
        blurb: 'Per article — what the vendor pays and the driver earns',
        icon: Sofa,
        count: 'unloading_rates',
      },
      {
        to: '/categories',
        label: 'Goods categories',
        blurb: 'What is carried, and whether unloading is charged',
        icon: Package,
      },
    ],
  },
  {
    to: '/vehicles',
    label: 'Vehicles',
    blurb: 'Owned and hired, and the papers on them',
    icon: Truck,
    children: [
      {
        to: '/market-vehicles',
        label: 'Market vehicles',
        blurb: 'The phonebook, for when a lorry is needed today',
        icon: PhoneCall,
        count: 'market_vehicles',
      },
    ],
  },
  {
    to: '/drivers',
    label: 'Drivers',
    blurb: 'Who drives, and what they are paid',
    icon: UserRound,
    children: [
      {
        to: '/labour',
        label: 'Loading crew',
        blurb: 'The godown hands, by name',
        icon: HardHat,
        count: 'labour',
      },
    ],
  },
  {
    to: '/settlements',
    label: 'Settlements',
    blurb: 'Money in from vendors, money out to drivers',
    icon: Wallet,
    children: [
      {
        to: '/invoices',
        label: 'Vendor invoices',
        blurb: 'Bill the completed freights',
        icon: FileText,
        count: 'invoices',
      },
      {
        to: '/money-in',
        label: 'Money in',
        blurb: 'What vendors have actually paid',
        icon: Banknote,
      },
      {
        to: '/advances',
        label: 'Advances',
        blurb: 'Cash handed over, and its recovery',
        icon: HandCoins,
        count: 'advances',
      },
      {
        to: '/expenses',
        label: 'Expenses',
        blurb: 'What drivers paid on the road, waiting on a decision',
        icon: ReceiptText,
        count: 'expenses_pending',
      },
    ],
  },
  {
    to: '/reports',
    label: 'Reports',
    blurb: 'Vendors, freights, drivers and vehicles over a period',
    icon: BarChart3,
    children: [],
  },
  {
    to: '/users',
    label: 'Users',
    blurb: 'Logins, what each may reach, and who has asked to work with you',
    icon: Users,
    children: [
      {
        to: '/roles',
        label: 'Roles',
        blurb: 'What each kind of user may reach',
        icon: ShieldCheck,
        count: 'roles',
      },
      {
        to: '/enquiries',
        label: 'Enquiries',
        blurb: 'Businesses who asked to work with you',
        icon: MessageSquare,
        count: 'enquiries',
      },
      {
        to: '/guide',
        label: 'User guide',
        blurb: 'The full cycle, in the order it has to be done',
        icon: Package,
      },
    ],
  },
]

/** The hub a path belongs to, for highlighting the rail. */
export function hubFor(pathname: string): Hub | undefined {
  const path = pathname.replace(/\/$/, '')
  return (
    HUBS.find((h) => path === h.to || path.startsWith(`${h.to}/`)) ??
    HUBS.find((h) => h.children.some((c) => path === c.to || path.startsWith(`${c.to}/`)))
  )
}
