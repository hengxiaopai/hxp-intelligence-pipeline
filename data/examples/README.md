# Example Data

This directory contains deterministic fixtures for validating the HXP Intelligence Pipeline without making network requests.

## Files

- `briefing.example.json`: daily briefing structure.
- `source.example.json`: synthetic source used by the briefing example.
- `manifest.example.json`: generated asset manifest.
- `candidate.example.json`: real-world candidate event structure.
- `candidate-source.example.json`: source record referenced by the candidate event.

## Validate

```bash
python scripts/validate.py --examples
python scripts/validate.py \
  --schema schemas/candidate.schema.json \
  --data data/examples/candidate.example.json
python scripts/validate.py \
  --schema schemas/source.schema.json \
  --data data/examples/candidate-source.example.json
python scripts/source_registry.py --validate
python scripts/validate_candidate.py
```

Examples are test fixtures. They are not automatically approved for public publication.
