import { labelText, toProvenanceLabel } from './models';
import styles from './styles.module.css';

/** Shared, read-only source badge. Unrecognised input is shown as UNKNOWN, never as official. */
export function SourceLabel({ label }: { label: unknown }) {
  const safe = toProvenanceLabel(label);
  return <span className={`${styles.badge} ${styles[safe]}`} data-provenance={safe}>
    <span className={styles.badgePrefix}>출처</span> {labelText[safe]}
  </span>;
}

export default SourceLabel;
