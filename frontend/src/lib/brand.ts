/* Everything a different operator would change, in one file.
 *
 * The software is Target Express's, but the same business runs in every
 * district in Kerala and the next operator should not need a developer to put
 * their own name on it. So the name, the tagline, the contact details and the
 * headline copy live here rather than being typed into the markup in nine
 * places — which is how a rebrand ends up with someone else's phone number
 * still in the footer.
 *
 * What is deliberately NOT here: the company's GSTIN, PAN and bank details.
 * Those print on a tax invoice, they are legal facts rather than presentation,
 * and they belong on the server in .env.prod — not in a file that ships to
 * every visitor's browser.
 */

export const BRAND = {
  /* The wordmark. Rendered uppercase; keep it short enough to sit in the rail. */
  name: 'TARGET EXPRESS',
  /* Under the wordmark, in the rail and on the landing page. */
  tagline: 'LOGISTICS TO CONNECT WORLD',
  /* The footer line, after the © and the year. */
  legalName: 'Target Express Logistics',
} as const

/* Published to the world. A landing page with a wrong number is worse than one
 * with no number, so these are the real ones off the letterhead. */
export const CONTACT = {
  phone: '+91 70120 36002',
  phoneHref: 'tel:+917012036002',
  whatsapp: 'https://wa.me/917012036002',
  email: 'targetexpress1997@gmail.com',
  address: '6/857 A, Sky Tower, HMT Jn., Kalamassery - 683 104',
  city: 'Kalamassery, Kerala',
} as const

/* The headline copy.
 *
 * Split into lines because the display type is set to break exactly where it
 * is told — a headline that rewraps on a phone reads as an accident. Each
 * array is one line per entry.
 */
export const COPY = {
  heroLines: ['We move more', 'than cargo.'],
  /* The word that gets the gradient treatment, and what follows it. */
  heroAccent: 'certainty',
  heroTail: '.',
  heroSub:
    'Full-truck and part-load movement across Kerala for manufacturers and their dealers. Every carton labelled, scanned at the door, and signed for.',
  promiseLines: ['Sorted.', 'Sealed.', 'Signed for.'],
  trackTitle: 'Expecting a delivery?',
  trackSub: 'Enter the LR number from your paperwork. No app, no login, no password.',
} as const
