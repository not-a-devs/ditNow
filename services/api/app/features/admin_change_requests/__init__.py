"""DEMO-only admin change *proposal* workflow (FR-ADM-001/003 first pass).

Not mounted. DRAFT -> SUBMITTED -> WITHDRAWN only; no approval, no execution, no role grant.
Data lives in bounded PROCESS_MEMORY and resets on restart; ``official_effect`` is always false.
"""
