# Tesco Flatmate Billing MVP

This package implements the local MVP described in `../PLAN.md`:

- receipt ingestion
- receipt parsing
- chat triage
- ledger settlement generation
- QA reconciliation
- reminder jobs

## Quick start

```bash
cd receipt-processor
python -m unittest discover -s tests -p 'test_*.py'
python -m receipt_processor.demo
```

The legacy Groq receipt extractor remains in `scripts/process_receipt.py`.

