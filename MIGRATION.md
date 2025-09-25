# SlackWire Migration Guide

## Overview
This document tracks the modernization of SlackWire components and what will be deprecated.

## Phase 1: Async Slack SDK Migration

### Components to be Deprecated
- **slack_bot.py** - Synchronous Slack bot using threading
- **Threading in main.py** - Mixed sync/async architecture

### New Components
- **async_slack_bot.py** - Fully async Slack implementation
- Unified async event loop in main.py

### Migration Benefits
- Eliminates thread management complexity
- Better resource utilization
- Consistent async/await pattern throughout

## Phase 2: Database Migration (SQLite)

### Components to be Deprecated
- **feed_cache.json** - JSON file for feed cache
- **article_feedback.json** - JSON file for feedback data
- **digest_config.json** - JSON file for digest settings
- **utils/file_lock.py** - File locking mechanisms (no longer needed with DB)
- Parts of **utils/cache_manager.py** - JSON-based caching

### New Components
- **database/models.py** - SQLAlchemy ORM models
- **database/manager.py** - Database connection and query management
- **migrations/** - Database migration scripts

### Migration Benefits
- ACID transactions
- Concurrent access without file locks
- Better query capabilities
- Data integrity constraints

## Phase 3: REST API

### New Components
- **api/app.py** - FastAPI application
- **api/routes/** - API endpoint definitions
- **api/schemas/** - Request/response models

### API Endpoints
- Health checks and status
- Feed management
- Article retrieval
- Configuration updates
- Metrics endpoint

## Phase 4: Metrics Collection

### New Components
- **metrics/collector.py** - Prometheus metrics
- **metrics/middleware.py** - Request tracking

### Metrics to Track
- Feed fetch success/failure rates
- Article processing times
- Slack API latency
- Cache hit rates

## Deprecation Timeline

1. **Immediate** - Start using new components alongside old ones
2. **After Testing** - Switch primary operations to new components
3. **Final** - Remove deprecated components after verification

## Backward Compatibility

During migration:
- Keep both systems running in parallel
- Sync data between old and new storage
- Gradual cutover with feature flags
- Rollback plan for each phase