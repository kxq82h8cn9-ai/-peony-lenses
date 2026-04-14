"""
Database module for AI Educational Platform
SQLite-based storage for all platform data
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/platform.db")

def get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    -- Users table (students, teachers, parents, admins)
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );

    -- Student profiles with detailed cognitive data
    CREATE TABLE IF NOT EXISTS student_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        grade TEXT,
        subjects TEXT DEFAULT '[]',
        learning_style TEXT DEFAULT 'visual',
        cognitive_fingerprint TEXT DEFAULT '{}',
        intelligences_scores TEXT DEFAULT '{}',
        total_points INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        streak_days INTEGER DEFAULT 0,
        last_active TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Subject sessions
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        persona TEXT DEFAULT 'default',
        title TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Chat messages
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        content_type TEXT DEFAULT 'text',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    );

    -- Uploaded files
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        session_id INTEGER,
        filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_size INTEGER,
        extracted_text TEXT,
        claude_file_id TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Mind maps
    CREATE TABLE IF NOT EXISTS mind_maps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        session_id INTEGER,
        title TEXT NOT NULL,
        map_data TEXT NOT NULL,
        subject TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Quizzes
    CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        session_id INTEGER,
        subject TEXT NOT NULL,
        questions TEXT NOT NULL,
        difficulty TEXT DEFAULT 'medium',
        quiz_type TEXT DEFAULT 'mcq',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Quiz attempts
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        answers TEXT NOT NULL,
        score REAL,
        time_taken INTEGER,
        feedback TEXT,
        completed_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Assessments (pre/post tests)
    CREATE TABLE IF NOT EXISTS assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        assessment_type TEXT DEFAULT 'diagnostic',
        questions TEXT NOT NULL,
        answers TEXT,
        score REAL,
        report TEXT,
        completed_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Progress records
    CREATE TABLE IF NOT EXISTS progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        topic TEXT,
        skill_level REAL DEFAULT 0.0,
        mastery_percentage REAL DEFAULT 0.0,
        sessions_count INTEGER DEFAULT 0,
        last_score REAL,
        notes TEXT,
        recorded_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Rewards and badges
    CREATE TABLE IF NOT EXISTS rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        points INTEGER DEFAULT 0,
        badge_icon TEXT,
        awarded_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Learning paths (AI-suggested paths per student)
    CREATE TABLE IF NOT EXISTS learning_paths (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        path_data TEXT NOT NULL,
        current_step INTEGER DEFAULT 0,
        completed_steps TEXT DEFAULT '[]',
        generated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Reports
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        report_type TEXT NOT NULL,
        recipient_role TEXT DEFAULT 'student',
        content TEXT NOT NULL,
        period_start TEXT,
        period_end TEXT,
        generated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    -- Parent-student relationships
    CREATE TABLE IF NOT EXISTS parent_students (
        parent_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        PRIMARY KEY (parent_id, student_id),
        FOREIGN KEY (parent_id) REFERENCES users(id),
        FOREIGN KEY (student_id) REFERENCES users(id)
    );

    -- Teacher-student relationships
    CREATE TABLE IF NOT EXISTS teacher_students (
        teacher_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        subject TEXT,
        PRIMARY KEY (teacher_id, student_id),
        FOREIGN KEY (teacher_id) REFERENCES users(id),
        FOREIGN KEY (student_id) REFERENCES users(id)
    );
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")

def get_user_by_email(email: str):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id: int):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(name: str, email: str, password_hash: str, role: str = "student"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        (name, email, password_hash, role)
    )
    user_id = cursor.lastrowid
    if role == "student":
        cursor.execute(
            "INSERT INTO student_profiles (user_id) VALUES (?)",
            (user_id,)
        )
    conn.commit()
    conn.close()
    return user_id

def get_student_profile(user_id: int):
    conn = get_connection()
    profile = conn.execute(
        "SELECT * FROM student_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(profile) if profile else None

def update_student_profile(user_id: int, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [user_id]
    conn = get_connection()
    conn.execute(
        f"UPDATE student_profiles SET {fields} WHERE user_id = ?", values
    )
    conn.commit()
    conn.close()

def create_session(user_id: int, subject: str, persona: str, title: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (user_id, subject, persona, title) VALUES (?, ?, ?, ?)",
        (user_id, subject, persona, title or f"جلسة {subject}")
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def save_message(session_id: int, role: str, content: str, content_type: str = "text"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, content_type) VALUES (?, ?, ?, ?)",
        (session_id, role, content, content_type)
    )
    conn.commit()
    conn.close()

def get_session_messages(session_id: int, limit: int = 50):
    conn = get_connection()
    msgs = conn.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    conn.close()
    return [dict(m) for m in msgs]

def save_file_record(user_id: int, filename: str, file_path: str,
                     file_type: str, file_size: int, extracted_text: str = None,
                     session_id: int = None, claude_file_id: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO files (user_id, session_id, filename, file_path, file_type,
           file_size, extracted_text, claude_file_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, session_id, filename, file_path, file_type, file_size,
         extracted_text, claude_file_id)
    )
    file_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return file_id

def save_mind_map(user_id: int, title: str, map_data: dict, subject: str,
                  session_id: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mind_maps (user_id, session_id, title, map_data, subject) VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, title, json.dumps(map_data), subject)
    )
    map_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return map_id

def save_quiz(user_id: int, subject: str, questions: list, difficulty: str,
              quiz_type: str, session_id: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO quizzes (user_id, session_id, subject, questions, difficulty, quiz_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, session_id, subject, json.dumps(questions), difficulty, quiz_type)
    )
    quiz_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return quiz_id

def save_quiz_attempt(quiz_id: int, user_id: int, answers: list, score: float,
                      time_taken: int, feedback: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO quiz_attempts (quiz_id, user_id, answers, score, time_taken, feedback)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (quiz_id, user_id, json.dumps(answers), score, time_taken, feedback)
    )
    attempt_id = cursor.lastrowid
    # Award points
    points = int(score * 10)
    if score >= 80:
        award_reward(user_id, "achievement", "أداء متميز",
                    f"حصلت على {score:.0f}% في الاختبار", points, "🏆")
    conn.commit()
    conn.close()
    # Update progress
    update_progress(user_id, "general", score=score)
    return attempt_id

def award_reward(user_id: int, reward_type: str, name: str,
                 description: str, points: int, icon: str = "⭐"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO rewards (user_id, type, name, description, points, badge_icon)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, reward_type, name, description, points, icon)
    )
    # Update total points
    conn.execute(
        "UPDATE student_profiles SET total_points = total_points + ? WHERE user_id = ?",
        (points, user_id)
    )
    conn.commit()
    conn.close()

def update_progress(user_id: int, subject: str, score: float = None,
                    topic: str = None):
    conn = get_connection()
    existing = conn.execute(
        "SELECT * FROM progress WHERE user_id = ? AND subject = ?",
        (user_id, subject)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE progress SET sessions_count = sessions_count + 1,
               last_score = ?, mastery_percentage = (mastery_percentage * sessions_count + ?) / (sessions_count + 1)
               WHERE user_id = ? AND subject = ?""",
            (score, score or 0, user_id, subject)
        )
    else:
        conn.execute(
            """INSERT INTO progress (user_id, subject, topic, mastery_percentage,
               sessions_count, last_score) VALUES (?, ?, ?, ?, 1, ?)""",
            (user_id, subject, topic, score or 0, score)
        )
    conn.commit()
    conn.close()

def get_user_progress(user_id: int):
    conn = get_connection()
    progress = conn.execute(
        "SELECT * FROM progress WHERE user_id = ?", (user_id,)
    ).fetchall()
    rewards = conn.execute(
        "SELECT * FROM rewards WHERE user_id = ? ORDER BY awarded_at DESC LIMIT 20",
        (user_id,)
    ).fetchall()
    profile = conn.execute(
        "SELECT * FROM student_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    sessions_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()['cnt']
    conn.close()
    return {
        "progress": [dict(p) for p in progress],
        "rewards": [dict(r) for r in rewards],
        "profile": dict(profile) if profile else {},
        "sessions_count": sessions_count
    }

def get_user_sessions(user_id: int):
    conn = get_connection()
    sessions = conn.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(s) for s in sessions]

def get_user_mind_maps(user_id: int):
    conn = get_connection()
    maps = conn.execute(
        "SELECT * FROM mind_maps WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(m) for m in maps]
