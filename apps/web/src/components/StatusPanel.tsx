import type { ReactNode } from 'react';

export function StatusPanel({ title, children, tone = 'pending', onRetry }: {
  title: string; children?: ReactNode; tone?: 'pending' | 'loading' | 'error' | 'empty'; onRetry?: () => void;
}) {
  return <div className={`status-panel status-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
    <span className="status-symbol" aria-hidden="true">{tone === 'error' ? '!' : tone === 'loading' ? '…' : '↗'}</span>
    <div><strong>{title}</strong>{children && <p>{children}</p>}
      {onRetry && <button className="text-button" onClick={onRetry}>다시 확인</button>}</div>
  </div>;
}
