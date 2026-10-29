const symbols: Record<string, string> = {
  login: 'M9 3H3v18h6m5-15 6 6-6 6m-8-6h14',
  home: 'M3 10 12 3l9 7v11h-6v-7H9v7H3Z',
  discovery: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  academic: 'M3 5h18v16H3Zm0 5h18M8 3v4m8-4v4',
  department: 'M3 4h18v12H9l-6 5Zm5 5h8m-8 3h5',
  community: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-1a3 3 0 1 0 0-6m-15 16v-3a5 5 0 0 1 10 0v3m4-7a5 5 0 0 1 6 5v2',
  recruitments: 'M12 3 3 8l9 5 9-5Zm-9 9 9 5 9-5m-18 5 9 5 9-5',
  opportunities: 'M12 3v18M3 12h18M6 6l12 12M6 18 18 6',
  classrooms: 'M3 4h18v14H3Zm5 18 4-4 4 4M8 9h8m-8 4h5',
  support: 'M12 21S3 15 3 9a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6-9 12-9 12Z',
  information: 'M3 21V9l9-6 9 6v12M3 21h18M8 10v7m4-7v7m4-7v7',
  ai: 'm12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z',
};
export function Icon({ name, size = 21 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={symbols[name] ?? symbols.home} /></svg>;
}
