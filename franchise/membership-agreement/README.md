# ULC membership agreement generator

Fills the center fields of ULC's Sample California Membership Agreement from a data file, so each center's version comes from the same template.

`los-gatos.yaml` lists the center's legal name, DBA, address, email, phone and URLs, each with a status and where the value came from. `generate.py` replaces those placeholders in the template and leaves everything else alone. That covers the member fields, the Kite merge fields, the contract dates and the signature blocks, which Kite fills at signing. A null value keeps its placeholder, and the summary lists every field still unfilled or not yet committed.

```bash
franchise/milestones/.venv/bin/python franchise/membership-agreement/generate.py
```

The default template is the Sample California ULC Membership Agreement in the franchisor Drive under `Operations/Presale/`, and the output goes to `out/`, which git ignores. Pass `--template`, `--data` or `--out` to change any of them. For another center, copy `los-gatos.yaml` and pass it with `--data`.

```bash
cd franchise/membership-agreement && ../milestones/.venv/bin/python -m unittest discover -s tests
```
