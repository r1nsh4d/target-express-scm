# TARGET EXPRESS — DELIVERY MANAGEMENT PLATFORM
## Project Brief & Functional Specification

**Prepared:** 22 September 2026
**Status:** Draft for client review
**Client:** Target Express Logistics

---

## 1. PROJECT OVERVIEW

1.1 Target Express is a third-party logistics (3PL) operator. It positions itself between a vendor's warehouse and that vendor's delivery points.

1.2 Target Express sells three things together:
   - **Labour** — a Target Express admin and helper replace the vendor's own loading crew inside the vendor's godown.
   - **Transport** — owned or hired vehicles running multi-stop routes.
   - **Accountability** — every box identified, tracked, and proven delivered.

1.3 The software exists primarily to make the third item sellable. The system of record is therefore **the box and the trip**, not just the vehicle.

1.4 Revenue side: vendors are billed under per-vendor-division rate contracts with GST.

1.5 Cost side: hired-vehicle bills, driver pay, and on-road expenses.

1.6 The platform closes the loop between the two, making margin visible per trip, per vehicle and per vendor.

---

## 2. SCOPE — THREE CONNECTED PIECES

| Piece | Users | Purpose |
|---|---|---|
| Web application | Office admins, warehouse admins, accounts | Masters, sorting labels, trip creation, monitoring, invoicing, reports |
| Mobile application | Drivers | Trip sheet, navigation, odometer, photos, unloading charges, advances |
| Tracking link | End customers / distribution centres | No-login browser page: box list, live position, delivery proof, location correction |

2.1 All three share one database.

2.2 Warehouse admin and helper work from the web app on a tablet or laptop at the vendor's godown.

2.3 The driver carries no paper.

2.4 The customer installs nothing.

---

## 3. TERMINOLOGY (STANDARDISED)

| Term used by client | Standard term in system | Definition |
|---|---|---|
| Fright | **Freight / Trip** | One dispatch run: one origin, many drop points, one or more vehicles |
| Bill | **Consignment** | The vendor's invoice/delivery note for one customer. One consignment = one vendor bill number = one delivery point = N boxes |
| Point | **Freight Point (Stop)** | One stop on the trip |
| Customer / Distributor | **Consignee** | Two subtypes: RETAIL_CUSTOMER, DISTRIBUTION_CENTER |
| Sticker | **Box Label** | Physical label pasted on each box |

3.1 **LR (Consignment Note)** — legally required for GTA status in India. Issued per trip, numbered from a per-vehicle book.

3.2 **Vendor Division** — e.g. GODREJ OCP, GODREJ APPLIANCE SPARE. This is the level at which rate cards are held, not the vendor level.

---

## 4. ACTORS AND ROLES

| Role | Platform | Responsibilities |
|---|---|---|
| Super Admin (HQ) | Web | Masters, rate contracts, users, billing, reports |
| Warehouse Admin | Web / Tablet | Enter or import consignments, sort boxes, print labels, build trips, supervise loading |
| Helper / Loader | Mobile (light) | Assist loading; optional counting role |
| Driver | Mobile | Odometer, navigation, delivery, POD, unloading charges, advances |
| Consignee | Public link, no login | Track own delivery, correct drop location |
| Accounts | Web | Vendor GST invoices, vehicle payables, driver settlements |
| Vendor (Phase 3) | Web portal | Push bills, view shipments, download invoices |

---

## 5. BOUNDED CONTEXTS (SYSTEM MODULES)

5.1 **Masters** — vendors, divisions, warehouses, goods categories, consignees, vehicles, drivers, users

5.2 **Rating** — rate cards, charge rules, versioning

5.3 **Inbound & Sorting** — consignments, boxes, label generation

5.4 **Trip Planning** — route building, point sequencing, vehicle/driver assignment

5.5 **Execution** — loading confirmation, dispatch, live tracking, delivery, POD, exceptions

5.6 **Customer Visibility** — tracking links, location correction, notifications

5.7 **Billing (Receivable)** — vendor invoices, GST

5.8 **Settlements (Payable)** — vehicle hire bills, driver pay, expense approval

---

## 6. CORE ENTITIES AND FIELDS

### 6.1 Vendor
- name, GSTIN, PAN, billing address, payment terms, contact
- has many Vendor Divisions
- has many Vendor Warehouses

### 6.2 Vendor Division
- vendor_id
- name (GODREJ OCP, GODREJ APPLIANCE SPARE)
- goods_category (SPARE_PARTS, FURNITURE, …)
- gstin, billing_address, invoice_series
- **This is the rate card key.**

### 6.3 Vendor Warehouse
- vendor_id, name, address, geo point, contact
- origin point for trips

### 6.4 Goods Category
- name (spare parts, furniture, appliances)
- handling attributes: is_fragile, is_bulky, default_unload_unit (box / weight / CBM)

### 6.5 Consignee (Customer / Distribution Centre)
- name, type (RETAIL_CUSTOMER | DISTRIBUTION_CENTER)
- phone — **required for tracking link**
- address text, geo point
- geo_confidence (VERIFIED | APPROXIMATE | UNVERIFIED)
- parent_vendor_id (when it is the vendor's own DC)

> **Note:** Address quality is the hidden cost centre. Every corrected location is saved back to the consignee, so the next delivery to that address is already accurate. Accuracy compounds over time.

### 6.6 Vehicle
- registration number, vehicle type, capacity (weight + volume)
- ownership: OWNED | HIRED
- owner_id → Vehicle Owner (set when rented)
- insurance, fitness certificate, permit expiry dates
- LR book series and next number (per vehicle)
- last closing odometer

### 6.6a Vehicle Owner  ⭐
- name, phone, address, PAN, GSTIN
- bank account, IFSC, bank name
- has many Vehicles

> Held separately from the vehicle because one owner commonly supplies several vehicles, and both settlement and advances run per owner rather than per lorry.

### 6.7 Vehicle Hire Terms (rented vehicles only)
- rate_basis: PER_KM | PER_TRIP | PER_DAY
- rate value
- minimum km guarantee per trip
- includes_unloading (true = rent already covers it, nothing reimbursed separately)
- per_point_amount (normally zero on rentals)
- effective_from / effective_to (versioned, like a rate card)

### 6.8 Driver
- name, phone, licence number, licence expiry
- engagement: OWN_STAFF | ATTACHED_TO_HIRED_VEHICLE
- documents

### 6.9 Driver Pay Terms
- fixed salary
- per trip amount
- per km amount
- daily allowance (batta)
- share of unloading charge
- effective dates

### 6.10 Rate Card  ⭐ (see Section 8 for verified values)
- vendor_division_id
- vehicle_type_id (nullable = applies to all types)
- effective_from / effective_to (versioned, never edited in place)
- base_trip_amount
- included_km
- extra_km_rate
- included_points
- extra_point_rate
- unloading_applicable (true/false)
- unloading_basis (PER_POINT | PER_BOX | ACTUAL)
- unloading_rate
- toll / detention / unloading_additional → PASS_THROUGH_ACTUAL

### 6.11 Consignment
- vendor_division_id, vendor_bill_no, bill_date
- goods_category_id, consignee_id
- declared box count, declared value
- e-way bill number (optional)
- lr_no
- status

### 6.12 Box
- consignment_id, item_no (1 of N)
- barcode / QR code (unique)
- weight, dimensions (if known)
- status lifecycle:
  ```
  SORTED → LABELLED → LOADED → IN_TRANSIT → DELIVERED
                          ↘ SHORT_AT_LOADING
                          ↘ DAMAGED
                          ↘ NOT_DELIVERED → RETURNED_TO_WAREHOUSE
  ```

### 6.13 Box Label (print layout)
Priority order on the sticker:
1. **Point number + colour band** (largest element — loaders sort by colour and position)
2. Customer / consignee name
3. Bill number + box number ("Bill 4521 · Box 3 of 7")
4. Trip code
5. QR / barcode (verification layer only)

### 6.14 Freight (Trip)  ⭐ key aggregate
- trip_no (global sequence, e.g. Y26005651)
- lr_no (per-vehicle book)
- date, origin warehouse
- planned distance
- status: `DRAFT → PLANNED → LOADING → DISPATCHED → IN_TRANSIT → COMPLETED → BILLED → SETTLED`
- dispatched_at, **returned_at**, completed_at
- has many Freight Points
- has one or more Freight Legs

> **A trip is complete when the vehicle is back at the origin warehouse — not when the last point is delivered.** That is what makes the billed kilometres a closed round trip, and what lets the closing reading meet the next trip's opening reading on the odometer chain. A trip with any leg still open is still running, whatever the delivery points say.

### 6.15 Freight Point (Stop)
- sequence number
- consignee_id, address snapshot, geo point
- reference image (location photo for driver)
- planned ETA, actual arrival, actual departure
- consignments / boxes assigned
- loading photo + loaded box count
- delivery photo + delivered box count
- POD: receiver name, signature / OTP
- unloading amount paid (driver entry)
- status

### 6.16 Freight Leg  ⭐ handles mid-trip vehicle change
- freight_id, vehicle_id, driver_id
- from_point_seq, to_point_seq
- start_odometer + photo
- end_odometer + photo
- start_time, end_time
- leg_distance_km
- change_reason (BREAKDOWN | ACCIDENT | DRIVER_UNAVAILABLE | OTHER)

> **Critical design note:** A trip has 1..N legs. Vendor billing rolls up the whole trip. Vehicle and driver payables compute **per leg**. This is how one trip correctly produces two vehicle bills without changing the vendor's invoice format. `vehicle_id` must NOT hang directly off Freight.

### 6.17 Trip Expense
- leg_id, point_id (nullable)
- type: UNLOADING | LOADING | FUEL | TOLL | PARKING | FOOD | REPAIR | ADVANCE | OTHER
- amount, receipt photo
- paid_by: DRIVER | COMPANY
- entered_by (user), entry_mode: SELF | ADMIN_ON_BEHALF
- approval status, approver, approved_at

### 6.18 Vendor Invoice
- invoice_no (series / FY / serial — e.g. 191/2026-27/022)
- invoice_date, period_from, period_to
- vendor_division_id, vehicle_type (descriptive)
- taxable_value, cgst, sgst, igst, total
- status: DRAFT | ISSUED | SENT | PAID

### 6.19 Vendor Invoice Line (one per trip)
- freight_id, trip_no, lr_no
- trip_date, vehicle_no
- destination_text, point_count
- start_km, close_km, km
- base_amount, included_km, extra_km, extra_km_rate, extra_km_amount
- toll, unloading, unloading_additional, extra_point_amount, detention
- line_total

> `destination_text` is derived from the trip's points but **stored on the line**, so a later edit to a consignee's name does not silently change an issued invoice.

### 6.20 Vehicle Settlement
- per hired vehicle per leg/period
- km × rate, minus advances

### 6.21 Driver Settlement
- trips, km, batta, unloading share, minus advances

### 6.22 Tracking Session
- freight_point_id, opaque token, expiry
- channel sent (SMS / WhatsApp), view count

### 6.23 Location Change Request
- freight_point_id, old geo, new geo, distance delta
- status, approver
- **Must be approved when the delta exceeds a threshold, because it changes billable km.**

### 6.24 Supporting
- User, Role, Permission
- Audit Log (every trip, every correction)

---

## 7. END-TO-END OPERATIONAL FLOW

### 7.1 Vendor bills arrive
- Warehouse admin enters the day's delivery bills, or uploads an Excel file the vendor already produces
- Each bill carries: vendor bill number, goods category, delivery point, box count

### 7.2 Sorting and labelling
- System groups bills by delivery point
- Prints one label per box (layout per 6.13)
- Loaders sort by colour band and point number

### 7.3 Building the trip
- Admin selects points for this vehicle
- Drags them into delivery order on a map
- Assigns vehicle and driver
- System issues trip number and LR number from that vehicle's book

### 7.4 Loading
- For each point, admin confirms the box count going into the vehicle
- Takes one photograph of that point's stacked, labelled consignment
- Trip cannot dispatch while a point is short without a recorded reason

### 7.5 Dispatch
- Driver enters opening odometer reading + photographs the meter
- Every customer on the trip receives their tracking link at this moment

### 7.6 At each point
- Driver navigates from the app (using the customer's corrected pin where one exists)
- Marks arrival
- Confirms boxes handed over
- Photographs unloaded goods and receiver
- Captures receiver name + confirmation code / OTP
- Enters unloading amount paid
- Any shortfall is recorded as an exception on the spot

### 7.7 Vehicle change mid-trip
- Driver closes current leg with meter reading
- Office assigns replacement vehicle → opens second leg
- Kilometres, costs, and driver pay split automatically between legs
- Vendor still sees one trip

### 7.8 Return and reconciliation
- Driver enters closing odometer + photograph
- Undelivered boxes checked back into warehouse
- **Trip closes only when: boxes loaded = boxes delivered + boxes returned**

### 7.9 Invoice and payouts
- Completed trip becomes one line on the vendor invoice
- Simultaneously produces driver earnings and vehicle hire amount

---

## 8. BILLING ENGINE — VERIFIED AGAINST ACTUAL INVOICES

### 8.1 The rule

```
Line Total = Base trip amount
           + max(0, KM − Included KM) × Extra KM rate
           + max(0, Points − Included Points) × Extra point rate
           + Toll               (actual pass-through)
           + Unloading charges
           + Unloading additional charges
           + Detention charges  (actual pass-through)
```

### 8.2 Verified rate constants (Godrej, both divisions)

| Parameter | Value |
|---|---|
| Base trip amount | ₹1,867 |
| Included KM | 60 |
| Extra KM rate | ₹17 per km |
| Included points | 3 |
| Extra point rate | ₹175 per point |
| Toll | Actual pass-through |
| Detention | Actual pass-through |

### 8.2a Point charges are a configurable slab ⭐

Points bill as a fixed amount covering the first N stops, then a rate for each stop beyond:

```
point_charge = base_point_charge + max(0, points − included_points) × extra_point_rate
```

| Vendor | Slab | Included | Per extra point | A 7-point trip |
|---|---|---|---|---|
| Example vendor | ₹500 | 3 | ₹100 | 500 + (4 × 100) = **₹900** |
| Godrej | ₹0 | 3 | ₹175 | 4 × 175 = **₹700** |

8.2a.1 Godrej sets the slab to **₹0** because their point allowance is already inside the ₹1,867 trip base. That is why their invoices still reconcile exactly with this field present.

8.2a.2 Every figure is **per vendor division**, so a vendor charging a flat ₹500 for three points needs configuration, not code. The same 10-point trip:

| Vendor | Slab | Min points | Per extra | 3 pts | 5 pts | 10 pts |
|---|---|---|---|---|---|---|
| Godrej | ₹0 | 3 | ₹175 | ₹0 | ₹350 | ₹1,225 |
| Vendor B | ₹500 | 3 | ₹100 | ₹500 | ₹700 | ₹1,200 |
| Vendor C | ₹0 | 5 | ₹120 | ₹0 | ₹0 | ₹600 |
| Vendor D | ₹750 | 8 | ₹90 | ₹750 | ₹750 | ₹930 |

### 8.2b Which points are billable ⭐

8.2b.1 "Points" are the freight's **delivery points** — the stops on the trip.

8.2b.2 **A failed delivery still bills.** The vehicle went there, and that journey is the work being charged for.

8.2b.3 Only a point **pulled from the route before the vehicle set off** (`SKIPPED`) is excluded, because no journey was made.

| Point outcome | Bills the vendor? |
|---|---|
| Delivered | Yes |
| Part delivered | Yes |
| **Failed at the door** | **Yes** |
| Skipped before dispatch | No |

### 8.3 Reconciliation — Invoice 191/2026-27/022 (Godrej Appliance Spare, 29 trips)

| Control total | Computed | On invoice | Match |
|---|---|---|---|
| Per-trip base | 29 × ₹1,867 | ₹54,143 | ✔ |
| Sum of KM column | — | 15,151 km | ✔ |
| Extra KM | 15,151 − (29 × 60) | 13,411 km | ✔ |
| Extra KM amount | 13,411 × ₹17 | ₹2,27,987 | ✔ |
| Extra point amount | 139 × ₹175 | ₹24,325 | ✔ |
| Toll | pass-through | ₹5,280 | ✔ |
| Unloading additional | pass-through | ₹1,540 | ✔ |
| **GRAND TOTAL** | sum | **₹3,13,275** | ✔ |

### 8.4 Line-level spot checks

| Trip | Destination | Points | KM | Calculation | Invoice |
|---|---|---|---|---|---|
| Y26005822 | Thrissur | 6 | 182 | 1867 + 2074 + 105 + 525 | ₹4,571 |
| Y26005823 | Palakkad | 7 | 345 | 1867 + 4845 + 260 + 700 | ₹7,672 |
| Y26005892 | Kasaragod | 7 | 900 | 1867 + 14280 + 290 + 700 | ₹17,137 |
| Y26006109 | TVM | 11 | 944 | 1867 + 15028 + 290 + 1400 | ₹18,585 |
| Y26006140 | Palakkad | 2 | 270 | 1867 + 3570 + 260 + 0 | ₹5,697 |
| Y26006013 | Kollam | 3 | 388 | 1867 + 5576 + 0 + 0 | ₹7,443 |

### 8.5 Unloading differs by vendor division

| Vendor division | Goods | Unloading basis |
|---|---|---|
| Godrej Appliance Spare | Spare parts | **Not billed.** ₹0 across all 29 trips |
| Godrej OCP | Furniture | **Per article, plus the climb** |

8.5.1 Rate cards are therefore held **per vendor division**, and the unloading basis is set at that level.

### 8.6 Furniture unloading: per article plus the climb ⭐

Furniture is not unloaded by the box. A chair, a wardrobe and a mattress are different work, and carrying any of them up four floors is different work again.

```
charge per article = base_rate + floors_charged × per_floor_rate
point total        = Σ over articles of (charge × quantity)
```

8.6.1 Ground floor is **0**, so a ground-floor delivery is the base rate alone.

8.6.2 Worked example — the client's own: a **chair** at ₹50 with ₹10 a floor, delivered to the **4th floor**:

```
50 + (4 × 10) = ₹90
```

8.6.3 Each article carries its own pair of rates, per vendor division, versioned by effective date:

| Article | Ground floor | Per floor | 4th floor |
|---|---|---|---|
| Chair | ₹50 | ₹10 | ₹90 |
| Table | ₹120 | ₹25 | ₹220 |
| Mattress | ₹150 | ₹30 | ₹270 |
| Sofa | ₹300 | ₹60 | ₹540 |
| Bed | ₹350 | ₹70 | ₹630 |
| Wardrobe | ₹400 | ₹80 | ₹720 |

8.6.4 **The floor is a billable fact, so the driver confirms it at the point** rather than it being assumed when the trip is planned. `floor_number` and `has_lift` are captured per delivery point.

8.6.5 **A lift cancels the climb charge by default**, but this is a per-division commercial setting, not a fixed rule — wheeling a wardrobe into a lift is not the same job as carrying it up four flights, but it is not a ground-floor drop either. A per-article cap on chargeable floors is also supported for contracts that stop counting beyond a certain height.

8.6.6 An article delivered with **no rate on file is billed as zero and flagged**, so the gap reaches the office instead of quietly costing money.

8.6.7 The rates in the table above are **placeholders pending the signed furniture rate sheet** — only the chair figures came from the client. The structure is confirmed; the numbers are one screen of data entry.

### 8.6 Vehicle type does NOT drive the rate

8.6.1 The same registrations (KL41U0317, KL75E2101, KL75E2107, KL12N5176, KL38C7608, KL41W9315, KL07CW3317) appear on both invoices at identical rates, under different "VEHICLE TYPE" headers (50SF and DOST).

8.6.2 Conclusion: vehicle type is recorded and printed but does not drive the calculation. The field is retained on the rate card as an optional, nullable qualifier in case a future vendor prices by vehicle type.

### 8.7 KM is round-trip

8.7.1 Kasaragod at 838 km and Kannur at 663 km are return figures from the origin warehouse.

8.7.2 A trip is one out-and-back loop; the odometer chain closes at the warehouse.

### 8.8 Numbering series

| Series | Pattern | Scope |
|---|---|---|
| Trip No | Y26005651 … Y26006288 | Global, continuous across ALL vendors |
| LR No | 774 … 822 (with out-of-block entries, e.g. 851) | Per vehicle — physical book |
| Invoice No | 191/2026-27/022 | Per financial year, sequential |

### 8.9 Invoice generation flow

1. Office selects vendor division + date range (month or custom)
2. System pulls every COMPLETED trip not yet invoiced
3. Renders annexure in the existing Target Express layout
4. Adds tax invoice (GST) on top
5. Stamps each trip with the invoice ID — prevents double billing
6. A standing "Completed but not invoiced" list shows the backlog

### 8.10 GST

8.10.1 Forward charge — Target Express charges the vendor.

8.10.2 Place-of-supply logic determines CGST+SGST vs IGST.

8.10.3 Invoice carries Target Express GSTIN, invoice series, and authorised signatory block ("For Target Express Logistics — Director").

---

## 9. CHARGE HEADS, PAY AND MARGIN

### 9.1 Three charge heads, used on both sides ⭐

A trip earns under three heads, and pays out under the same three heads:

| Head | Billed to the vendor | Paid out |
|---|---|---|
| **Transportation** | Base trip charge + distance beyond the included km | **Per km** to the driver (own vehicle), or the hire rate to the owner (rented) |
| **Loading / unloading** | Per the vendor rate card; ₹0 for spare parts, per article for furniture | **To the driver**, who splits it with the cleaner and labourers |
| **Point incentives** | Slab + points beyond those included | **Nothing** — retained margin, unless a driver is put on a point rate |

9.1.0a Target Express pays its drivers on **distance, plus the unloading cash**. The point charge the vendor pays does **not** reach the driver — that difference is margin Target Express keeps. The per-point field exists for drivers on a different arrangement and defaults to zero.

9.1.1 Plus two pass-throughs on both sides: **toll** and **detention**.

9.1.2 Using the same heads on both sides is the point. Margin becomes readable head by head, not just as one figure at the bottom of a trip.

9.1.3 The amounts on each side are independent. The billed side comes from the vendor rate card; the paid side from the driver's pay terms or the vehicle's hire terms.

9.1.4 Worked example — a 345 km, 7-point trip on an owned vehicle:

| Head | Billed | Paid | Margin |
|---|---|---|---|
| Transportation | ₹6,712 | ₹1,217.50 | ₹5,494.50 |
| Point incentives | ₹700 | ₹280 | ₹420 |
| Loading / unloading | ₹0 (spare parts) | ₹700 | **−₹700** |
| **Trip total** | **₹8,112** | **₹2,197.50** | **₹5,914.50** |

9.1.5 The negative unloading line is the case that matters. On spare-parts work the vendor is billed nothing for unloading while cash still goes out. A single shared field would hide that entirely; two fields under one head surface it.

### 9.2 Who gets paid depends on the vehicle, not the trip ⭐

| Vehicle | Payee | Terms applied |
|---|---|---|
| **Owned** by Target Express | The **driver** | Driver pay terms |
| **Rented** from outside | The **vehicle owner** | Vehicle hire terms |

9.2.0a **Unloading is the exception — it always goes to the driver.** He is the one paying the labourers at the point, and he splits it with the cleaner himself. So on a rented trip the hire settles to the owner while the unloading cash reaches the driver: **one leg, two payees.** Configurable per vehicle where an owner insists on receiving it instead.

9.2.1 Rent is a vehicle arrangement, not a driver one. The owner settles with his own driver.

9.2.2 **The driver is still recorded on every payout row**, and both the owner's name and the driver's name print on the settlement document.

9.2.3 Vehicle owners are a first-class record (`vehicle_owners`), not fields on the vehicle, because one owner commonly supplies several vehicles and settlement runs per owner.

9.2.4 Hire terms support per-km (with a minimum km guarantee per trip), per-trip flat, and per-day. Unloading is reimbursed at actuals unless the agreed rent already includes it.

### 9.3 Rented vehicles: advance out, balance on return ⭐

A rented vehicle runs a **per-trip** money cycle, not a monthly payment run:

```
Vehicle leaves   → owner draws an advance against the trip
Trip runs        → payouts written head by head as each leg closes
Vehicle returns  → advance set against what the trip earned
                 → balance paid, trip account closed
```

9.3.1 Target Express pays the **vehicle owner only** on a rented trip. The driver takes nothing from Target Express — the owner pays his own driver. The driver is still recorded on every payout row and named on the document.

9.3.2 Worked example — a 561 km, 6-point rented trip at ₹13/km with ₹900 unloading paid out:

| | Amount |
|---|---|
| Transportation (561 km × ₹13) | ₹7,293 |
| Loading / unloading (reimbursed at actuals) | ₹900 |
| **Gross** | **₹8,193** |
| Less advance drawn at dispatch | −₹5,000 |
| **Balance payable on return** | **₹3,193** |

9.3.3 An advance larger than the trip earned is **not an error**. The excess stays outstanding against that owner and is recovered from his next trip.

9.3.4 Advances are matched to the payee who drew them. An advance taken by a vehicle owner is never recovered from the driver who happened to be at the wheel.

9.3.5 Each advance tracks amount, amount recovered, and status (outstanding / part recovered / recovered / written off).

### 9.3a Loading labour at the godown

9.3a.1 The helpers who load the vehicle at the warehouse are held as a **master** (`labour`), because it is largely the same few people every day — the admin picks a name rather than retyping it.

9.3a.2 Their payment is recorded as a **loading expense** on the trip, carrying the labour name and head count, so a month's payments to one helper can be totalled without reading every trip.

9.3a.3 Unloading labour at the delivery end is deliberately **not** tracked here: that money goes to the driver as a lump and he splits it himself.

### 9.3b Earnings visibility is per user ⭐

9.3b.1 Drivers on rented vehicles log in to run the trip, but Target Express does not pay them for driving, so their earnings screen is switched off.

9.3b.2 The flag (`can_view_earnings`) is set **per user**, not derived from the vehicle — a driver can move between an owned and a rented lorry from one week to the next, and his visibility should not flip with the roster.

9.3b.3 A blocked request returns a clear refusal rather than an empty screen. A zero total reads like a missing payment, and that starts the wrong conversation.

### 9.4 Settlements

9.4.1 Own drivers settle over a period: gross by head, less advances recovered and other deductions, giving net payable.

9.4.2 Payouts are computed **when the trip closes**, on the terms in force on the day of the trip — not at settlement time, when those terms may have moved.

9.4.3 A trip whose vehicle was swapped mid-run produces **two accounts**, each covering only the legs that party actually ran.

### 9.3 Owned vs hired vehicles

9.3.1 Vehicles are marked OWNED or HIRED.

9.3.2 Hired vehicles carry owner's rate and minimum km guarantee.

9.3.3 Hire bills accumulate per leg.

9.3.4 Enables comparison of real cost per km: owning vs hiring. This is the number behind every fleet decision.

### 9.4 Advances and expenses

9.4.1 Every amount paid or taken on the road is entered with a receipt photograph.

9.4.2 Flows into an approval queue.

9.4.3 Approved items settle against driver earnings.

9.4.4 Driver sees his own running balance — removes most settlement disputes before they start.

9.4.5 If the driver cannot manage an entry, the office can enter it on his behalf. It appears in his app marked as office-entered. Nothing is recorded against him that he cannot see.

---

## 10. CONTROLS AND VALIDATIONS

### 10.1 Odometer continuity check ⭐

10.1.1 Since km is billed from meter readings, a vehicle's closing reading on one trip should equal its opening reading on the next.

10.1.2 **Verified on the actual invoices:**
   - KL4156965 → 250507, 250852, 250852, 251426, 251426, 251778 (zero gap across four trips)
   - KL07DE1175 → 140704 → 140704 → 141448 → 141448 (exact)
   - KL07CW3317 → 239003 → 239003 (exact)

10.1.3 **Where gaps appear, the cause is cross-vendor trips.** KL41U0317 closes at 189143 and reopens at 189375 — a 232 km gap explained only by a trip on the *other* vendor division's invoice.

10.1.4 One spreadsheet per vendor cannot see across that boundary. One database can. This is a control the client does not have today at any price.

10.1.5 It also catches plain errors: KL07DE1129 closes at 133432 and reopens at 133422 — ten kilometres backwards.

10.1.6 The system flags every unexplained gap with both trips shown side by side.

### 10.2 Odometer correction with audit

10.2.1 Admins can correct a meter reading.

10.2.2 The correction is kept as its own record: original value, corrected value, reason, who, when.

10.2.3 The driver's original entry is never overwritten.

10.2.4 Both appear on the audit trail — a vendor query six months later needs to see what was captured vs what was billed.

### 10.3 Box reconciliation

10.3.1 Boxes loaded must equal boxes delivered plus boxes returned, on every trip, before it can close.

10.3.2 This is the check that turns the missing-box complaint into a number.

### 10.4 Location change approval

10.4.1 Customer-initiated location changes beyond a distance threshold require admin approval, because they change billable km.

### 10.5 Double-billing prevention

10.5.1 Trips are stamped with the invoice number once billed and cannot be selected again.

---

## 11. PROOF OF HANDLING — PHOTO CHECKPOINTS

11.1 **Decision:** counted photo checkpoints rather than mandatory per-box scanning.

11.2 **At loading, per point:** admin enters box count for that point + photographs the stacked, labelled consignment.

11.3 **At drop-off, per point:** driver enters delivered count + photographs unloaded goods and receiver + captures receiver name/OTP.

11.4 Mismatch between the two counts raises an exception on the spot.

11.5 In-app camera barcode scan remains **optional**, as a per-vendor toggle — useful where the vendor's cartons already carry barcodes.

11.6 **Trade-off, stated plainly:** counting tells you *that* a box is missing; scanning would tell you *which one*. Counted checkpoints plus photographs recover most of that gap at a fraction of the operational friction, and are realistic at loading-bay speed. Revisit per vendor once crews are used to the app.

---

## 12. TRACKING LINK (CUSTOMER-FACING)

12.1 Sent on dispatch via WhatsApp with SMS fallback.

12.2 No app, no login — opens in any browser.

12.3 Shows:
   - ETA and live vehicle position (throttled — shows the vehicle, not the driver's whole day)
   - **Their** box list with bill numbers — this is the differentiator; no competitor shows the consignee their own carton manifest
   - "Wrong location? Fix it" → drops a pin → raises a Location Change Request
   - Masked driver call
   - On delivery: POD photo + confirmation

12.4 Link expires after delivery.

---

## 13. MOBILE APPLICATION (DRIVER)

13.1 One trip at a time, one point at a time, large targets, few words.

13.2 Screens and functions:
   - Today's trip: points in order, box count per point
   - Opening / closing odometer entry with meter photograph
   - Navigation to next point (uses corrected pin where available)
   - At the point: boxes handed over, photograph, receiver name, confirmation code
   - Unloading amount paid, tolls, fuel, advances — each with receipt photograph
   - Running total of own earnings and advances for the month

13.3 **Offline-first is an architectural requirement, not a feature.**
   - Deliveries happen in basements, industrial estates and villages
   - Every action writes to a local queue and syncs opportunistically
   - Uploading a POD photo must never block marking a point delivered
   - Location breadcrumbs buffer offline and backfill
   - Retrofitting offline support later is a rewrite

13.4 Language: Malayalam alongside English (to be confirmed), icon-led UI.

---

## 14. REPORTS

14.1 Short and missing box register — by vendor, point, driver, vehicle

14.2 Delivery success and on-time percentage — by vendor, driver, vehicle

14.3 Cost per kilometre — owned vehicles vs hired

14.4 Profitability per trip and per vendor — billed vs vehicle, driver and unloading costs

14.5 Driver settlement and advance ledger

14.6 Completed trips not yet invoiced

14.7 GST output register

14.8 Document expiry alerts — insurance, fitness certificate, permits, licences

14.9 Full audit trail per trip

14.10 Odometer gap exceptions

---

## 15. RECOMMENDED TECHNICAL STACK

| Layer | Recommendation | Rationale |
|---|---|---|
| Backend | NestJS + TypeScript (or Django) | Shared types with web if TypeScript |
| Database | PostgreSQL + PostGIS | Geo queries, zone rating |
| Web | Next.js + React + TypeScript | Admin is table and form heavy |
| Mobile | React Native | One codebase; offline via WatermelonDB or SQLite + sync queue |
| Maps | Google Maps (India coverage) or Mapbox | Routing, geocoding, distance matrix |
| Labels | Thermal printer, ZPL / TSPL direct | Browser printing to thermal is fragile |
| Messaging | WhatsApp Business API + SMS fallback | WhatsApp is how Indian consignees actually read links |
| File storage | S3 / Cloudflare R2, presigned upload from app | POD photos are the bulk of storage |
| Tracking | Mobile GPS (foreground service) or SIM-based tracker | To be decided — see open points |

---

## 16. BUILD PLAN

### 16.1 Phase 1 — Operations
- Masters (vendors, divisions, warehouses, categories, consignees, vehicles, drivers, users)
- Bill entry and Excel import
- Sorting and label printing
- Trip creation with point sequencing
- Loading confirmation with counts and photos
- Driver mobile application (offline-first)
- Tracking link
- Proof of delivery
- Box reconciliation

### 16.2 Phase 2 — Money
- Rate cards with versioning
- Vendor invoicing with GST in the current layout
- Driver settlements
- Vehicle hire bills
- Expense approval workflow

### 16.3 Phase 3 — Depth
- Vendor self-service portal
- Analytics dashboards
- Vendor ERP integration
- Returns / RTO handling

### 16.4 Why Phase 1 before Phase 2

16.4.1 Operations cannot run without labels and box counts.

16.4.2 Billing can continue on the present method for a few weeks without harm.

16.4.3 Running a month of real trips through the system first makes rate configuration safer — it can be proved against invoices already raised and paid.

---

## 17. DELIBERATELY EXCLUDED

### 17.1 Automatic route optimisation
- Real trips carry 2 to 12 points
- Warehouse admins know Kerala routing better than a solver
- Drag-to-reorder on a map with distance shown gives a better result for less money and less risk
- Can be added later if trip sizes grow

### 17.2 Mandatory per-box scanning
- See Section 11.6 for the reasoning and trade-off

### 17.3 Returns / RTO handling
- Deferred to Phase 3 by agreement, pending a decision on refused boxes

---

## 18. DECISIONS ALREADY CONFIRMED BY CLIENT

| # | Question | Client's answer |
|---|---|---|
| 1 | Km measurement | From driver's start and end odometer readings; admin can correct |
| 2 | Proof method | Photo at loading to vehicle and photo at drop-off; scanning from the app if possible |
| 3 | Who pays unloading | Vendor pays; driver is paid at his own rate; vendor bill carries the vendor's agreed rate |
| 4 | Points per trip | 2–12 typical; the 10–30 figure was a safety buffer |
| 5 | GST status | Target Express charges the vendors (forward charge) |
| 6 | Driver expense entry | Driver enters himself; if not possible, admin enters per driver's guidance |
| 7 | Vehicle GPS | Mobile GPS tracking or SIM-based tracking |
| 8 | Rate card key | Vendor division (not vehicle type) |
| 9 | Unloading by category | ₹0 for spare parts; charged for furniture |
| 10 | LR books | Per vehicle (to be confirmed) |
| 11 | Billing period | Month by month, or a custom range |
| 12 | Returns / RTO | To be decided later |
| 13 | Trip completion | A trip is complete when it lands back at the starting point |
| 14 | Charge heads | Transportation, loading/unloading, point incentives — billed to the vendor, and driver/owner pay generated from the same heads |
| 15 | Rented vehicle payee | Payment goes to the **vehicle owner**, not the driver; the bill names both the owner and the driver |
| 16 | Advances | Provided against both drivers and vehicle owners, recovered at settlement |
| 17 | Rented vehicle cycle | Owner draws an advance at the start of the trip; the full amount is closed after the trip. The driver is paid nothing by Target Express for driving |
| 18 | Unloading payee | Paid to the **driver**, who splits it with the cleaner and other labourers — on owned and rented vehicles alike |
| 19 | Loading labour | Godown loading crew held as a master; their payment recorded as a loading expense on the trip |
| 20 | Point charges | A configurable slab: fixed amount for the first N points, then a rate per extra point (e.g. ₹500 for 3, ₹100 thereafter → 7 points = ₹900). Per vendor |
| 21 | Earnings visibility | Configurable per user. Off for drivers on rented vehicles, who log in but are not paid by Target Express |
| 22 | Failed deliveries | Still count as a billable point to the vendor — the vehicle went there |
| 23 | Driver pay basis | **Kilometres only**, plus the unloading charge where it applies. No point incentive |

---

## 19. OPEN POINTS TO CONFIRM

| # | Point | Why it matters |
|---|---|---|
| 1 | **Points included in the base rate** — the invoice arithmetic gives **3**, Target Express described **5** | Worth ₹8,050 on invoice 191/2026-27/022 alone (138 chargeable points against 92), which annualises to roughly **₹2.26 lakh on this one division**. If the agreement says 5 and invoices were raised at 3, that is an overbilling the vendor can reclaim |
| 2 | **The signed furniture rate sheet** — the full article list with ground-floor and per-floor rates | The calculation is built and the chair figures are confirmed (₹50 + ₹10/floor = ₹90 to the 4th). Only the remaining article rates are outstanding, and they are data entry rather than development |
| 2a | **Does a lift remove the climb charge?** | Currently yes by default, configurable per division. A one-field decision, but it changes real money on every high-rise furniture drop |
| 3 | **The GST page** that accompanies the trip annexure | Needed to build the invoice template. The annexure we have ends at the total with no tax line |
| 4 | **LR books held per vehicle** — confirm | Decides whether the system issues LR numbers from a per-vehicle series or records a number from a physical book |
| 5 | **How vendor bills reach the warehouse admin** — keyed in, Excel upload, or from the vendor's own system | This is the admin's largest daily workload. Excel import removes most of it |
| 6 | **Do vendor bills carry the end customer's mobile number?** | Tracking links cannot be sent without it. If not on the bills, the admin must capture them |
| 7 | **Label printing hardware** at each vendor warehouse | Thermal label printers assumed. Model and quantity affect cost and setup |
| 8 | **Languages** for the driver application | Malayalam alongside English assumed unless told otherwise |
| 9 | **Vehicle position** — driver's phone or SIM-based tracker | Phone tracking costs nothing but stops when the phone does. Decide before Phase 1 |
| 10 | **What happens to a refused or undelivered box** | Agreed to be settled later. Shapes the returns screens in Phase 3 |
| 11 | **Scale at launch** — vendor warehouses, vehicles, drivers, trips per day | Sizing, licence counts, rollout sequence |
| 12 | **Rate cards for other vendors** — are there vendors beyond Godrej, and do their rates differ by vehicle type? | Confirms whether vehicle type stays out of the rate key |
| 13 | **Billing lag** — how long between running a trip and raising the invoice today? | If it is currently weeks, compressing it to days is a working-capital gain worth quantifying for the client |

19.1 **Points 1 and 2 close out the billing engine completely.** Everything else can be settled during Phase 1 without holding up the build.

---

## 20. SUMMARY OF KEY DESIGN DECISIONS

20.1 **Rate cards are keyed on vendor division**, not vendor and not vehicle type. Versioned with effective dates; never edited in place. Every trip stores a rate snapshot at dispatch.

20.2 **A trip is composed of legs.** Vendor billing rolls up the trip; vehicle and driver payables compute per leg. This handles mid-trip vehicle changes cleanly.

20.3 **Unloading is two independent fields** — billed and paid. The difference is margin.

20.4 **Proof is photo-based with counts**, not mandatory per-box scanning. Optional scan available per vendor.

20.5 **Odometer readings are the billing source of truth**, with photo capture, admin correction under audit, and cross-vendor continuity validation.

20.6 **The driver app is offline-first** from day one.

20.7 **Invoices reproduce the existing Target Express layout exactly**, with a stored calculation trace on every line so disputes can be answered instantly.

20.8 **Route optimisation is out of scope** — manual sequencing on a map is better and cheaper at 2–12 points.

---

*End of document.*
