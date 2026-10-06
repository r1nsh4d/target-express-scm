import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './api'

/** Read a collection. The path doubles as the cache key. */
export function useList<T>(path: string, params?: Record<string, unknown>, enabled = true) {
  return useQuery({
    queryKey: [path, params ?? {}],
    queryFn: async () => (await api.get<T[]>(path, { params })).data,
    enabled,
  })
}

export function useItem<T>(path: string, enabled = true) {
  return useQuery({
    queryKey: [path],
    queryFn: async () => (await api.get<T>(path)).data,
    enabled,
  })
}

/**
 * Create against a collection, invalidating that collection on success.
 * `alsoInvalidate` covers the cases where a write ripples - creating a driver
 * with a login changes the user list too.
 */
export function useCreate<TBody, TResult = unknown>(
  path: string,
  options?: { onSuccess?: (result: TResult) => void; alsoInvalidate?: string[] },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: TBody) => (await api.post<TResult>(path, body)).data,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [path] })
      options?.alsoInvalidate?.forEach((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      )
      options?.onSuccess?.(result)
    },
  })
}

export function useAction<TBody, TResult = unknown>(
  path: string,
  options?: { onSuccess?: (result: TResult) => void; invalidate?: string[] },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: TBody) => (await api.post<TResult>(path, body)).data,
    onSuccess: (result) => {
      options?.invalidate?.forEach((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      )
      options?.onSuccess?.(result)
    },
  })
}

/* Shared shapes, matching the API responses. */

export interface Vendor {
  id: string
  name: string
  gstin: string | null
  contact_person: string | null
  contact_phone: string | null
  payment_terms_days: number
  is_active: boolean
}

export interface VendorDivision {
  id: string
  vendor_id: string
  vendor_name: string | null
  name: string
  code: string
  goods_category_id: string | null
  invoice_series: string
  gst_rate_percent: string | number
  is_active: boolean
}

export interface Warehouse {
  id: string
  vendor_id: string
  name: string
  code: string
  address: string | null
  is_active: boolean
}

export interface GoodsCategory {
  id: string
  name: string
  code: string
}

export interface VehicleType {
  id: string
  name: string
  capacity_kg: number | null
}

export interface VehicleOwner {
  id: string
  name: string
  phone: string
}

export interface Vehicle {
  id: string
  registration_no: string
  vehicle_type_id: string | null
  vehicle_type_name: string | null
  ownership: 'OWNED' | 'HIRED'
  owner_id: string | null
  owner_name: string | null
  lr_next_number: number
  last_closing_km: number | null
  is_active: boolean
}

export interface Driver {
  id: string
  name: string
  phone: string
  engagement: string
  licence_no: string | null
  default_vehicle_id: string | null
  user_id: string | null
  is_active: boolean
}

export interface Consignee {
  id: string
  name: string
  type: 'RETAIL_CUSTOMER' | 'DISTRIBUTION_CENTER'
  phone: string | null
  address: string | null
  city: string | null
  geo_confidence: string
  is_active: boolean
}

export interface RateCard {
  id: string
  vendor_division_id: string
  vehicle_type_id: string | null
  effective_from: string
  effective_to: string | null
  base_trip_amount: string | number
  included_km: number
  extra_km_rate: string | number
  base_point_charge: string | number
  included_points: number
  extra_point_rate: string | number
  unloading_basis: string
  is_active: boolean
}

export interface FreightRow {
  id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  status: string
  destination_text: string | null
  point_count: number
  vehicle_no: string | null
  driver_name: string | null
  total_km: number | null
}

export interface FreightPoint {
  id: string
  sequence: number
  consignee_id: string
  consignee_name: string
  address: string | null
  phone: string | null
  latitude: number | null
  longitude: number | null
  floor_number: number
  has_lift: boolean
  loaded_box_count: number
  delivered_box_count: number
  // Four numbers, and every one is deliberate. Paid and billed differ because
  // a spare-parts run bills nothing for unloading while cash still goes out.
  // Coolie is apart from unloading because a vendor asking why unloading rose
  // must be able to see the two separately.
  unloading_paid: string | number
  unloading_billed: string | number
  coolie_paid: string | number
  coolie_billed: string | number
  coolie_note: string | null
  status: string
  tracking_url: string | null
}

export interface FreightLeg {
  id: string
  sequence: number
  vehicle_id: string
  vehicle_no: string
  driver_id: string
  driver_name: string
  start_odometer: number | null
  end_odometer: number | null
  leg_distance_km: number | null
  change_reason: string
}

export interface Freight {
  id: string
  trip_no: string
  lr_no: string | null
  trip_date: string
  status: string
  vendor_division_id: string
  vendor_division_name: string | null
  warehouse_id: string
  warehouse_name: string | null
  destination_text: string | null
  point_count: number
  billable_point_count: number
  delivered_point_count: number
  total_km: number | null
  has_returned: boolean
  points: FreightPoint[]
  legs: FreightLeg[]
}

export interface Quote {
  trip_no: string
  km: number
  points: number
  base_amount: string
  extra_km: number
  extra_km_amount: string
  extra_points: number
  extra_point_amount: string
  unloading: string
  toll: string
  line_total: string
  trace: string[]
}

export const STATUS_TONE: Record<
  string,
  'neutral' | 'accent' | 'success' | 'warning' | 'info' | 'danger'
> = {
  DRAFT: 'neutral',
  PLANNED: 'info',
  LOADING: 'info',
  DISPATCHED: 'accent',
  IN_TRANSIT: 'accent',
  COMPLETED: 'success',
  BILLED: 'success',
  SETTLED: 'success',
  CANCELLED: 'warning',
  PENDING: 'neutral',
  LOADED: 'info',
  ARRIVED: 'accent',
  DELIVERED: 'success',
  PART_DELIVERED: 'warning',
  FAILED: 'danger',
  SKIPPED: 'neutral',
}

export function rupees(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '—'
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/* ---------------------------------------------------------------------------
   Route presets — the office's own numbered rounds.

   "No. 11" is a known run with a known set of customers in a known order. A
   preset is a TEMPLATE: creating a freight copies its stops and then forgets
   where they came from, so editing the round next month cannot alter a freight
   that has already run and been invoiced.
--------------------------------------------------------------------------- */

export interface RoutePresetPoint {
  id: string
  consignee_id: string
  consignee_name: string
  consignee_city: string | null
  consignee_phone: string | null
  sequence: number
  default_floor_number: number
  default_has_lift: boolean
  delivery_hint: string | null
}

export interface RoutePreset {
  id: string
  name: string
  vendor_division_id: string | null
  warehouse_id: string | null
  typical_round_trip_km: number | null
  notes: string | null
  is_active: boolean
  times_used: number
  points: RoutePresetPoint[]
}

/** A lorry, or a supplier of lorries, that can be hired in. Not the fleet —
 *  this is the phonebook you work through before a freight exists. */
export interface MarketVehicle {
  id: string
  contact_name: string
  phone: string
  alternate_phone: string | null
  registration_no: string | null
  vehicle_type_id: string | null
  vehicle_type_name: string | null
  capacity_note: string | null
  base_city: string | null
  operating_area: string | null
  last_hired_rate: string | null
  last_hired_on: string | null
  times_hired: number
  standing: 'UNTRIED' | 'RELIABLE' | 'AVOID'
  notes: string | null
  pan: string | null
  bank_account: string | null
  ifsc: string | null
  is_active: boolean
}
