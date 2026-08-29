# Visual storage map

Use a Mermaid `flowchart LR` for a broad audit with several important items. Keep it small enough to read.

## Raw scanner map

The scanner creates `storage-map.mmd`. It shows the largest measured folders and their closest visible parent. Blue means measured storage only. It does not mean safe to remove.

## Final decision map

After the safety review, update or recreate the graph with these decision classes:

```mermaid
flowchart LR
  root["This computer"] --> keep["Active projects<br/>KEEP · 12 GiB"]
  root --> move["Archive<br/>MOVE · 8 GiB"]
  root --> remove["Old cache<br/>REMOVE · 4 GiB"]
  root --> rebuild["Dependencies<br/>REBUILD · 3 GiB"]
  root --> review["Virtual disk<br/>REVIEW · 18 GiB"]
  classDef keep fill:#dcfce7,color:#14532d,stroke:#16a34a;
  classDef move fill:#dbeafe,color:#172554,stroke:#2563eb;
  classDef remove fill:#fee2e2,color:#7f1d1d,stroke:#dc2626;
  classDef rebuild fill:#f3e8ff,color:#581c87,stroke:#9333ea;
  classDef review fill:#fef3c7,color:#78350f,stroke:#d97706;
  class keep keep;
  class move move;
  class remove remove;
  class rebuild rebuild;
  class review review;
```

Apply these rules:

- Keep the graph to about 20 important nodes. Split it by category if it becomes crowded.
- Put the measured size and decision in every item label.
- Connect a child to the closest parent shown in the graph.
- Use the five words exactly: `KEEP`, `MOVE`, `REMOVE`, `REBUILD`, and `REVIEW`.
- Add a plain-text list or tree when Mermaid cannot render.
- Treat colours as scanning aids. Keep the decision words for accessibility.
- Do not put secret filenames or sensitive full paths in a shared graph.
- Do not imply that a recommendation is approved. Record approval separately.
