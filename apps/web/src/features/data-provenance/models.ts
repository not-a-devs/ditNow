export const provenanceLabels = ['DEMO', 'OFFICIAL_PUBLIC', 'PLATFORM', 'UNKNOWN'] as const;
export type ProvenanceLabel = typeof provenanceLabels[number];

export interface ProvenanceLabelInfo { label: ProvenanceLabel; title: string; description: string; user_guidance: string }
export interface ProvenanceStatus {
  school_sso_connected: false; financial_effect: 'NONE';
  persistence: 'IN_PROCESS_FIXED'; content_administration: 'NOT_IMPLEMENTED';
}
export interface ProvenanceOverview {
  catalog_version: string; feature_ids: string[]; notice: string;
  status: ProvenanceStatus; labels: ProvenanceLabelInfo[];
}

/** Local fallback text so the shared badge never depends on a network call. */
export const labelText: Record<ProvenanceLabel, string> = {
  DEMO: '시연용 가상 데이터',
  OFFICIAL_PUBLIC: '공개 자료 참고 요약',
  PLATFORM: '플랫폼 자체 데이터',
  UNKNOWN: '출처 미확인',
};

export function toProvenanceLabel(value: unknown): ProvenanceLabel {
  return provenanceLabels.find((label) => label === value) ?? 'UNKNOWN';
}

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const text = (value: unknown, max: number) => typeof value === 'string' && value.length > 0 && value.length <= max;

export function isLabelInfo(value: unknown): value is ProvenanceLabelInfo {
  return record(value) && provenanceLabels.some((label) => label === value.label)
    && text(value.title, 40) && text(value.description, 300) && text(value.user_guidance, 300);
}

export function isOverview(value: unknown): value is ProvenanceOverview {
  if (!record(value) || !record(value.status) || !Array.isArray(value.labels) || !Array.isArray(value.feature_ids)) return false;
  const status = value.status;
  return text(value.catalog_version, 60) && text(value.notice, 400)
    && value.feature_ids.every((id) => typeof id === 'string')
    && status.school_sso_connected === false && status.financial_effect === 'NONE'
    && status.persistence === 'IN_PROCESS_FIXED' && status.content_administration === 'NOT_IMPLEMENTED'
    && value.labels.length === provenanceLabels.length
    && value.labels.every((item, index) => isLabelInfo(item) && item.label === provenanceLabels[index]);
}
