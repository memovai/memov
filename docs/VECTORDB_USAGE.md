# VectorDB Usage Guide

This document explains how to use the VectorDB feature in Memov for semantic search of prompts and plans.

## Overview

Memov now includes a built-in vector database (powered by ChromaDB) that automatically stores all prompts, responses, and file changes with semantic embeddings. This enables:

- **Semantic search**: Find similar prompts/plans even if they use different words
- **Commit discovery**: Locate relevant commits by natural language queries
- **File tracking**: Find all commits that modified specific files

## Architecture

### Storage Structure

- **Location**: `.mem/vectordb/`
- **Chunking**: Text is automatically split into 768-character chunks with 100-character overlap
- **Embeddings**: Uses `all-MiniLM-L6-v2` sentence transformer model (local, no API required)

### Metadata Schema

Each chunk stored in VectorDB includes:

```python
{
    "operation_type": "track" | "snap" | "rename" | "remove",
    "source": "user" | "ai",
    "files": ["path/to/file1.py", "path/to/file2.py"],
    "commit_hash": "abc123...",
    "parent_hash": "def456...",
    "timestamp": "2025-10-23T10:30:00.123456",
    "chunk_index": 0,
    "total_chunks": 3,
    "chunk_text": "The actual text content..."
}
```

## Automatic Integration

VectorDB is **automatically integrated** into all Memov operations:

- `mem track` - Stores tracking information
- `mem snap` - Stores snapshot prompts and responses
- `mem rename` - Records rename operations
- `mem remove` - Records removal operations

No additional configuration needed!

## API Usage

### 1. Find Similar Prompts

```python
from memov.core.manager import MemovManager

manager = MemovManager(project_path="/path/to/project")

# Find prompts similar to a query
results = manager.find_similar_prompts(
    query_prompt="Add authentication to the API",
    n_results=5,
    operation_type="snap"  # Optional: filter by operation type
)

for result in results:
    print(f"Commit: {result['metadata']['commit_hash']}")
    print(f"Distance: {result['distance']}")  # Lower = more similar
    print(f"Text: {result['text']}")
    print(f"Files: {result['metadata']['files']}")
    print()
```

### 2. Find Commits by Prompt

```python
# Get just the commit IDs for similar prompts
commit_ids = manager.find_commits_by_prompt(
    query_prompt="refactor database queries",
    n_results=5
)

# Use these commits with other Memov commands
for commit_id in commit_ids:
    manager.show(commit_id)
```

### 3. Find Commits by Files

```python
# Find all commits that modified specific files
results = manager.find_commits_by_files(
    file_paths=["src/auth.py", "src/api.py"]
)

for result in results:
    print(f"Commit: {result['metadata']['commit_hash']}")
    print(f"Operation: {result['metadata']['operation_type']}")
    print(f"Files: {result['metadata']['files']}")
```

### 4. Get VectorDB Statistics

```python
# Get information about the collection
info = manager.get_vectordb_info()
print(f"Collection: {info['name']}")
print(f"Total chunks: {info['count']}")
print(f"Storage path: {info['persist_directory']}")
```

## Use Cases

### 1. Find Previous Similar Work

When starting a new feature, find similar past implementations:

```python
results = manager.find_similar_prompts(
    query_prompt="Add error handling to API endpoints",
    n_results=3
)
```

### 2. Track Feature Evolution

Find all commits related to a feature by semantic search:

```python
results = manager.find_similar_prompts(
    query_prompt="authentication middleware",
    n_results=10,
    operation_type="snap"
)
```

### 3. Code Archaeology

Find when and why specific files were modified:

```python
results = manager.find_commits_by_files(["config.py"])
for r in results:
    commit_id = r['metadata']['commit_hash']
    manager.show(commit_id)
```

## Configuration

### Custom Chunk Size

```python
from memov.storage.vectordb import VectorDB

# Create VectorDB with custom chunk size
vectordb = VectorDB(
    persist_directory=Path(".mem/vectordb"),
    collection_name="memov_memories",
    chunk_size=1024,  # Custom chunk size
    embedding_model="all-MiniLM-L6-v2"  # Or any sentence-transformers model
)
```

### Using Different Embedding Models

You can use any model from [sentence-transformers](https://www.sbert.net/docs/pretrained_models.html):

- `all-MiniLM-L6-v2` (default) - Fast, good quality, 384 dimensions
- `all-mpnet-base-v2` - Better quality, slower, 768 dimensions
- `multi-qa-mpnet-base-dot-v1` - Optimized for question-answering

## Performance Considerations

- **First run**: Downloads embedding model (~90MB for MiniLM)
- **Embedding speed**: ~1000 chunks/second on modern CPU
- **Storage**: ~1KB per chunk (text + embeddings + metadata)
- **Search speed**: Sub-millisecond for collections under 10K chunks

## Troubleshooting

### ChromaDB Import Error

```bash
# Install dependencies
uv pip install chromadb sentence-transformers
```

### Slow Initial Load

The first time you use VectorDB, it downloads the embedding model. Subsequent runs are fast.

### Reset VectorDB

```python
# Delete and recreate the collection
manager.vectordb.reset()  # Warning: deletes all data!
```

## Technical Details

### Text Chunking Algorithm

1. Split text into chunks of `chunk_size` characters
2. Add `overlap` characters between chunks for context
3. Break at word boundaries when possible
4. Store chunk metadata (index, total chunks)

### Similarity Search

- Uses **cosine similarity** on embedding vectors
- Returns results sorted by distance (lower = more similar)
- Distance range: 0.0 (identical) to 2.0 (opposite)

### Metadata Filtering

ChromaDB supports efficient metadata filtering:

```python
# Filter by operation type
results = vectordb.search(
    query_text="bug fix",
    where={"operation_type": "snap"}
)

# Filter by source
results = vectordb.search(
    query_text="refactor",
    where={"source": "ai"}
)
```

## Example Workflow

```python
from memov.core.manager import MemovManager

# Initialize manager
manager = MemovManager("/path/to/project")

# Normal Memov operations automatically populate VectorDB
manager.track(["src/auth.py"], prompt="Add JWT authentication", response="Implemented JWT middleware")
manager.snapshot(prompt="Fixed login bug", response="Updated token validation")

# Later, search for similar work
similar = manager.find_similar_prompts("authentication issues", n_results=5)
for result in similar:
    print(f"Found: {result['metadata']['commit_hash']}")
    print(f"Prompt: {result['text']}")
    print()

# Get commits that modified auth files
auth_commits = manager.find_commits_by_files(["src/auth.py"])
for commit in auth_commits:
    print(f"Commit: {commit['metadata']['commit_hash']}")
    print(f"Operation: {commit['metadata']['operation_type']}")
```

## Future Enhancements

Potential improvements:

1. **Multi-modal search**: Search by code snippets + natural language
2. **Temporal search**: Weight recent commits higher
3. **Graph-based search**: Use commit parent relationships
4. **Custom embeddings**: Fine-tune models on your codebase
5. **Cross-project search**: Search across multiple projects
