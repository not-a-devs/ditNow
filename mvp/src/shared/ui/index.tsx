import { useEffect, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { ApiError } from '../data/api';
import { ChevronLeft } from './icons';

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(' ');
}

// ───────── Button ─────────
type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'navy';
const variants: Record<Variant, string> = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-300',
  navy: 'bg-navy-800 text-white hover:bg-navy-900 disabled:bg-navy-300',
  secondary: 'bg-white text-navy-800 ring-1 ring-inset ring-navy-200 hover:bg-navy-50 disabled:text-navy-300',
  ghost: 'text-navy-600 hover:bg-navy-50 disabled:text-navy-300',
  danger: 'bg-white text-brand-700 ring-1 ring-inset ring-brand-200 hover:bg-brand-50 disabled:text-brand-300',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md'; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-xl font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed',
        size === 'md' ? 'min-h-[44px] px-4 text-sm' : 'min-h-[36px] px-3 text-xs',
        variants[variant],
        className,
      )}
    >
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Spinner({ className = 'h-5 w-5' }: { className?: string }) {
  return <span className={cx('inline-block animate-spin rounded-full border-2 border-current border-r-transparent', className)} aria-hidden />;
}

// ───────── Card / Badge ─────────
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx('rounded-2xl bg-white p-4 shadow-sm ring-1 ring-navy-100 sm:p-5', className)}>{children}</div>;
}

type Tone = 'brand' | 'navy' | 'sky' | 'accent' | 'gray' | 'green';
const tones: Record<Tone, string> = {
  brand: 'bg-brand-50 text-brand-700 ring-brand-200',
  navy: 'bg-navy-50 text-navy-700 ring-navy-200',
  sky: 'bg-sky-100 text-[#04779b] ring-[#9adcf0]',
  accent: 'bg-accent-100 text-[#a4520f] ring-[#f7c597]',
  gray: 'bg-gray-50 text-gray-600 ring-gray-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
};
export function Badge({ tone = 'navy', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset', tones[tone], className)}>
      {children}
    </span>
  );
}

// ───────── Page header ─────────
export function PageHeader({ title, subtitle, back, action }: { title: string; subtitle?: ReactNode; back?: string; action?: ReactNode }) {
  return (
    <div className="mb-5 flex items-start justify-between gap-3">
      <div className="min-w-0">
        {back && (
          <Link to={back} className="mb-1 inline-flex min-h-[32px] items-center gap-0.5 text-sm text-navy-500 hover:text-navy-800">
            <ChevronLeft className="h-4 w-4" /> 뒤로
          </Link>
        )}
        <h1 className="text-xl font-bold text-navy-900 sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-navy-500">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

// ───────── 상태 표시: loading / empty / error / permission / session-expired ─────────
export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="불러오는 중">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-20 animate-pulse rounded-2xl bg-navy-100/60" />
      ))}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-navy-200 bg-white/60 px-6 py-10 text-center">
      <p className="font-semibold text-navy-800">{title}</p>
      {description && <p className="mt-1 text-sm text-navy-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const navigate = useNavigate();
  const title =
    error.code === 'UNAUTHORIZED' ? '로그인이 필요합니다' : error.code === 'FORBIDDEN' ? '접근 권한이 없습니다' : error.code === 'NOT_FOUND' ? '찾을 수 없습니다' : '문제가 발생했습니다';
  return (
    <div role="alert" className="rounded-2xl bg-brand-50 px-6 py-8 text-center ring-1 ring-brand-100">
      <p className="font-semibold text-brand-800">{title}</p>
      <p className="mt-1 text-sm text-brand-700">{error.message}</p>
      <div className="mt-4 flex justify-center gap-2">
        {error.code === 'UNAUTHORIZED' ? (
          <Button onClick={() => navigate('/login')}>다시 로그인</Button>
        ) : (
          <>
            {onRetry && error.code !== 'FORBIDDEN' && error.code !== 'NOT_FOUND' && (
              <Button variant="secondary" onClick={onRetry}>다시 시도</Button>
            )}
            <Button variant="secondary" onClick={() => navigate(-1)}>이전으로</Button>
          </>
        )}
      </div>
    </div>
  );
}

export function InlineError({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-xl bg-brand-50 px-3 py-2 text-sm text-brand-700 ring-1 ring-brand-100">
      {error.message}
    </p>
  );
}

// ───────── Form fields ─────────
const inputCls =
  'w-full rounded-xl border-0 bg-white px-3 py-2.5 text-[15px] text-navy-900 ring-1 ring-inset ring-navy-200 placeholder:text-navy-300 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-navy-50';

export function Field({
  label,
  error,
  hint,
  counter,
  children,
  htmlFor,
}: {
  label: string;
  error?: string;
  hint?: string;
  counter?: { value: string; max: number };
  children: ReactNode;
  htmlFor: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label htmlFor={htmlFor} className="text-sm font-semibold text-navy-800">{label}</label>
        {counter && (
          <span className={cx('text-xs', counter.value.length > counter.max ? 'text-brand-600' : 'text-navy-400')}>
            {counter.value.length}/{counter.max}
          </span>
        )}
      </div>
      {children}
      {error ? <p className="mt-1 text-xs font-medium text-brand-600">{error}</p> : hint ? <p className="mt-1 text-xs text-navy-400">{hint}</p> : null}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  const { invalid, className, ...rest } = props;
  return <input {...rest} aria-invalid={invalid || undefined} className={cx(inputCls, invalid && 'ring-brand-400', className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  const { invalid, className, ...rest } = props;
  return <textarea {...rest} aria-invalid={invalid || undefined} className={cx(inputCls, 'min-h-[120px] resize-y', invalid && 'ring-brand-400', className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  const { invalid, className, ...rest } = props;
  return <select {...rest} aria-invalid={invalid || undefined} className={cx(inputCls, invalid && 'ring-brand-400', className)} />;
}

// ───────── Confirm dialog ─────────
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '확인',
  danger,
  loading,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="w-[calc(100%-32px)] max-w-sm rounded-2xl p-0 backdrop:bg-navy-900/40"
    >
      <div className="p-5">
        <h2 className="text-lg font-bold text-navy-900">{title}</h2>
        {description && <p className="mt-2 text-sm text-navy-600">{description}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>취소</Button>
          <Button variant={danger ? 'primary' : 'navy'} onClick={onConfirm} loading={loading}>{confirmLabel}</Button>
        </div>
      </div>
    </dialog>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-base font-bold text-navy-900">{children}</h2>
      {action}
    </div>
  );
}
