"""Informational reconciliation only. Never migrate historical copy logs to v2."""


def reconcile(records, observed):
    """Caller adapts legacy records to path/size, preserving the raw evidence.

    `observed` is a mapping of current relative paths to sizes. Same path/size is
    still not identity without trusted hashes. SNAP/camera/time/session_id from
    historical logs never supply scientific game, role or independent session.
    """
    rows = []
    for record in records:
        path, size = record.get('path'), record.get('size')
        matches = sorted(p for p, n in observed.items() if type(size) is int and n == size)
        rows.append(dict(evidence=dict(record), current_path_present=path in observed,
                         size_candidates=matches, identity_demonstrated=False,
                         status='NeedsReview', reason='HistoricalRecordWithoutTrustedHash'))
    return dict(schema='rg2019.historical-reconciliation.v1', status='NeedsReview',
                historical_count=len(records), observed_count=len(observed), records=rows,
                qc_status='NotApproved', processing_authorized=False,
                session_identity_verified=False, delivery_complete=False)
