export interface Title { id: string; title: string; author: string; available_copies: number; public_reference_url: string | null; source_kind: 'DEMO'; }
export interface Catalog { items: Title[]; offset: number; has_more: boolean; source_kind: 'DEMO'; }
export interface Loan { id: string; title: string; due_at: string; state: 'active' | 'returned'; renewal_count: number; renewable: boolean; revision: number; source_kind: 'DEMO'; }
export interface Wish { id: string; title: string; author: string; reason: string; state: 'requested' | 'reviewing' | 'completed' | 'cancelled'; created_at: string; source_kind: 'DEMO'; }
export interface Slot { id: string; space_id: string; space_name: string; starts_at: string; ends_at: string; available: boolean; revision: number; source_kind: 'DEMO'; }
export interface Booking { id: string; slot_id: string; space_name: string; starts_at: string; ends_at: string; state: 'reserved' | 'cancelled'; revision: number; source_kind: 'DEMO'; }
export interface Overview { loans: Loan[]; wishes: Wish[]; bookings: Booking[]; policy: { name: string; renewal_days: number; max_renewals: number; allow_overdue_renewal: boolean; renewal_base: 'due_at' | 'request_time'; max_active_bookings: number; source_kind: 'DEMO' }; source_kind: 'DEMO'; }

const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, max: number): value is string => typeof value === 'string' && value.length <= max;
const id = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const integer = (value: unknown, min = 0, max = 100000) => Number.isInteger(value) && Number(value) >= min && Number(value) <= max;
const date = (value: unknown): value is string => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
function array<T>(value: unknown, guard: (value: unknown) => value is T): value is T[] { return Array.isArray(value) && value.length <= 100 && value.every(guard); }
function demo(value: unknown): value is Record<string, unknown> { return object(value) && value.source_kind === 'DEMO' && !('owner_id' in value); }
export function safeReference(value: unknown): value is string { if (typeof value !== 'string') return false; try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash; } catch { return false; } }
export function isCatalog(value: unknown): value is Catalog {
  return demo(value) && integer(value.offset) && typeof value.has_more === 'boolean' && array(value.items, (row): row is Title => demo(row) && id(row.id) && text(row.title, 200) && text(row.author, 100) && integer(row.available_copies) && (row.public_reference_url === null || safeReference(row.public_reference_url)));
}
export function isLoan(value: unknown): value is Loan { return demo(value) && id(value.id) && text(value.title, 200) && date(value.due_at) && ['active', 'returned'].includes(String(value.state)) && integer(value.renewal_count) && integer(value.revision, 1) && typeof value.renewable === 'boolean'; }
export function isWish(value: unknown): value is Wish { return demo(value) && id(value.id) && text(value.title, 200) && text(value.author, 100) && text(value.reason, 500) && ['requested', 'reviewing', 'completed', 'cancelled'].includes(String(value.state)) && date(value.created_at); }
export function isSlot(value: unknown): value is Slot { return demo(value) && id(value.id) && id(value.space_id) && text(value.space_name, 100) && date(value.starts_at) && date(value.ends_at) && Date.parse(value.ends_at) > Date.parse(value.starts_at) && typeof value.available === 'boolean' && integer(value.revision, 1); }
export function isSlots(value: unknown): value is Slot[] { return array(value, isSlot); }
export function isBooking(value: unknown): value is Booking { return demo(value) && id(value.id) && id(value.slot_id) && text(value.space_name, 100) && date(value.starts_at) && date(value.ends_at) && ['reserved', 'cancelled'].includes(String(value.state)) && integer(value.revision, 1); }
export function isOverview(value: unknown): value is Overview {
  if (!demo(value) || !demo(value.policy)) return false;
  const p = value.policy;
  return text(p.name, 100) && integer(p.renewal_days, 1, 90) && integer(p.max_renewals, 0, 10) && typeof p.allow_overdue_renewal === 'boolean' && ['due_at', 'request_time'].includes(String(p.renewal_base)) && integer(p.max_active_bookings, 1, 10) && array(value.loans, isLoan) && array(value.wishes, isWish) && array(value.bookings, isBooking);
}
