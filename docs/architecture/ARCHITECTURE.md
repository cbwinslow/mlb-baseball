
# Baseball Platform Architecture

Date: 2026-05-09
Version: 2.0.0

## Overview

This document describes the refactored architecture of the baseball analytics platform following the Phase 1 foundation and Phase 2 MLB migration.

### Core Principles

1. **Clear Separation of Concerns**
   - Sources: Fetch raw data from external APIs/files
   - Services: Orchestrate workflows
   - CLI: User interface via Typer commands
   - Database: SQL schema in sql/ directory

2. **No Base Classes Unless Useful**
   - Protocol-based interfaces instead
   - Source-specific optimizations
   - Avoid forced inheritance hierarchies

3. **Reusable Building Blocks**
   - Common utilities in sources/common/
   - Shared result objects in core/results.py
   - Centralized logging and exceptions

4. **Type Safety**
   - Pydantic models for validation
   - Full type hints
   - Protocol-based contracts

## Directory Structure
