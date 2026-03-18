# Code Intelligence — Layer 4

Layer 4 provides AST-based code analysis with optional GitNexus integration for advanced metrics.

## Architecture

```
Source Code
    ↓
┌──────────────────┐
│ openclaw-brain-  │
│ code analyze     │
├──────────────────┤
│ Symbol Extraction│ → symbols.json
│ Call Graphs      │ → call-chains.json
│ Clusters         │ → clusters.json
│ Execution Flows  │ → execution-flows.json
│ Impact Analysis  │ → impact-analysis.json
└──────────────────┘
    ↓ (optional)
┌──────────────────┐
│ GitNexus         │
│ --with-gitnexus  │
└──────────────────┘
```

## Commands

### Analyze Project

```bash
openclaw-brain-code analyze --project ~/repos/easy-api --output json
```

Runs full AST analysis: symbols, call graphs, clusters, execution flows.

### Extract Symbols

```bash
openclaw-brain-code symbols --project ~/repos/easy-api --pattern "*.py"
```

Lists all functions, classes, types, and exports.

### Call Graph

```bash
openclaw-brain-code calls --project ~/repos/easy-api --symbol "process_payment" --depth 3
```

Traces call chains from a given symbol.

### Impact Analysis

```bash
openclaw-brain-code impact --project ~/repos/easy-api --file "src/payments.py"
```

Determines what breaks if a file changes. Shows:
- Direct dependents
- Transitive dependents
- Test coverage for affected code

### Find Usages

```bash
openclaw-brain-code find-usages --project ~/repos/easy-api --symbol "PaymentSession"
```

Finds all references to a symbol across the codebase.

### Export Graph

```bash
openclaw-brain-code export --project ~/repos/easy-api --output graph.json
```

Exports the complete code graph as JSON.

## Supported Languages

| Language | Symbols | Call Graphs | AST Parsing |
|----------|---------|-------------|-------------|
| Python   | ✓       | ✓           | ✓           |
| TypeScript | ✓     | ✓           | ✓           |
| JavaScript | ✓     | ✓           | ✓           |
| Go       | ✓       | Basic       | Basic       |
| Rust     | ✓       | Basic       | Basic       |

## Storage

```
~/.openclaw/projects/<slug>/code-graph/
├── symbols.json           # All extracted symbols
├── call-chains.json       # Function call relationships
├── clusters.json          # Logical code groupings
├── execution-flows.json   # Entry points and paths
└── impact-analysis.json   # Change impact data
```

## Configuration

Set in `.openclaw-lacp.env`:

```bash
CODE_GRAPH_ENABLED=false              # Enable code analysis
CODE_GRAPH_WITH_GITNEXUS=false        # Use GitNexus for advanced metrics
CODE_GRAPH_LANGUAGES=py,ts,js,go,rust # Languages to analyze
CODE_GRAPH_INCLUDE_PATTERNS=src/**,lib/**
CODE_GRAPH_EXCLUDE_PATTERNS=test/**,node_modules
CODE_GRAPH_UPDATE_ON_COMMIT=false     # Auto-analyze on commit
```

## GitNexus Integration (Optional)

GitNexus provides advanced code intelligence features:

```bash
# Install GitNexus
npm install -g gitnexus

# Analyze with GitNexus
openclaw-brain-code analyze --project ~/repos/easy-api --gitnexus
```

GitNexus adds:
- **Complexity metrics**: Cyclomatic complexity, cognitive complexity
- **Coupling analysis**: Module coupling and cohesion scores
- **Change frequency**: Hot spots based on git history
- **Architectural layers**: Auto-detected layer boundaries

### Enabling GitNexus

```bash
# In .openclaw-lacp.env
CODE_GRAPH_WITH_GITNEXUS=true

# Or via CLI flag
openclaw-brain-stack init --project . --with-gitnexus
```

## Initialization

```bash
# Initialize with code intelligence
openclaw-brain-stack init --project ~/repos/easy-api --with-gitnexus

# Or standalone
openclaw-brain-code analyze --project ~/repos/easy-api
```

## Integration

### With Layer 1 (Session Memory)
Code intelligence results inform `patterns.md` and `architecture.md` seed files.

### With Layer 2 (Knowledge Graph)
Symbol data can be indexed into the Obsidian vault for cross-referencing.

### With Layer 5 (Provenance)
Impact analysis results are attached to provenance receipts for change tracking.

## Doctor Check

```bash
openclaw-brain-doctor --project ~/repos/easy-api --layer 4
```

Checks:
- Code graph directory exists
- All 5 output files present
- GitNexus availability (if enabled)

## Troubleshooting

**No symbols found**: Check `CODE_GRAPH_INCLUDE_PATTERNS` matches your source layout.

**GitNexus not found**: Install with `npm install -g gitnexus`. Layer 4 works without it.

**Analysis too slow**: Narrow `CODE_GRAPH_INCLUDE_PATTERNS` or exclude test files.
