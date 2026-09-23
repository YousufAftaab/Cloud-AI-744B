"""Memory manager for preferences, project records, task history, and fast keyword retrieval."""

import re
from typing import Optional
from pc_insider.memory.db import db

class MemoryManager:
    # ----------------- PREFERENCES -----------------
    def set_preference(self, key: str, value: str):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO preferences (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                (key.strip(), value.strip())
            )
            conn.commit()

    def get_preference(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM preferences WHERE key = ?", (key.strip(),))
            row = cursor.fetchone()
            return row["value"] if row else default

    def list_preferences(self) -> dict[str, str]:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM preferences ORDER BY key")
            return {r["key"]: r["value"] for r in cursor.fetchall()}

    # ----------------- FACTS -----------------
    def add_fact(self, category: str, fact: str):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO facts (category, fact) VALUES (?, ?)", (category.strip(), fact.strip()))
            conn.commit()

    def list_facts(self, category: Optional[str] = None) -> list[dict]:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT id, category, fact, created_at FROM facts WHERE category = ?", (category.strip(),))
            else:
                cursor.execute("SELECT id, category, fact, created_at FROM facts ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    # ----------------- TASK HISTORY -----------------
    def record_task(self, goal: str, status: str, steps_count: int, summary: str):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO task_history (goal, status, steps_count, summary) VALUES (?, ?, ?, ?)",
                (goal[:250], status, steps_count, summary[:500])
            )
            conn.commit()

    def get_recent_tasks(self, limit: int = 5) -> list[dict]:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, goal, status, summary, created_at FROM task_history ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    # ----------------- RETRIEVAL (Phase 11) -----------------
    def search_relevant_memories(self, query: str, limit: int = 4) -> list[str]:
        """Lightweight keyword-based memory retrieval using SQLite LIKE queries."""
        words = re.findall(r'[a-zA-Z0-9_]{3,}', query.lower())
        if not words:
            return []

        results = []
        with db.get_connection() as conn:
            cursor = conn.cursor()
            for w in words[:4]:
                pattern = f"%{w}%"
                # Search preferences
                cursor.execute("SELECT key, value FROM preferences WHERE key LIKE ? OR value LIKE ? LIMIT ?", (pattern, pattern, limit))
                for r in cursor.fetchall():
                    item = f"Preference: {r['key']} = {r['value']}"
                    if item not in results:
                        results.append(item)
                # Search facts
                cursor.execute("SELECT category, fact FROM facts WHERE fact LIKE ? OR category LIKE ? LIMIT ?", (pattern, pattern, limit))
                for r in cursor.fetchall():
                    item = f"Fact [{r['category']}]: {r['fact']}"
                    if item not in results:
                        results.append(item)

        return results[:limit]

memory_manager = MemoryManager()
