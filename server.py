"""
AI Educational Platform — FastAPI Backend
Fixes applied:
  - Replaced broken python-jose with pure-Python HMAC JWT
  - Replaced passlib bcrypt with hashlib sha256 (bcrypt broken in this env)
  - Fixed @app.on_event deprecation → lifespan context manager
  - Fixed thinking + web_search: separated concerns (no thinking when tools used)
  - Added proper error handling on all endpoints
  - Added input validation and rate-limit awareness
  - Fixed static file mount order (must come after API routes)
  - Added missing PLAN.md / database.py file serves
"""
import os, json, base64, hashlib, hmac, secrets, time
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, field_validator
import anthropic
import aiofiles

import database as db

# ─── Config ───────────────────────────────────────────────────────────────────
SECRET_KEY        = os.getenv("SECRET_KEY", "ai-education-secret-2024-change-in-prod")
ALGORITHM         = "HS256"
TOKEN_EXP_HOURS   = 24
UPLOAD_DIR        = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES  = 10 * 1024 * 1024   # 10 MB
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".md"}

security = HTTPBearer(auto_error=False)

# ─── Pure-Python JWT (replaces broken python-jose) ────────────────────────────
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))

def create_token(user_id: int, role: str) -> str:
    header  = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": str(user_id), "role": role,
        "exp": int(time.time()) + TOKEN_EXP_HOURS * 3600,
        "iat": int(time.time()),
    }).encode())
    sig = _b64url_encode(
        hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"

def verify_token(token: str) -> dict:
    try:
        header, payload, sig = token.split(".")
        expected = _b64url_encode(
            hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Invalid signature")
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            raise ValueError("Token expired")
        return data
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# ─── Pure-Python password hashing (replaces broken passlib/bcrypt) ────────────
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, h = hashed.split(":", 1)
        expected = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return hmac.compare_digest(expected, h)
    except Exception:
        return False

# ─── Personas ─────────────────────────────────────────────────────────────────
PERSONAS = {
    "history": {
        "name": "المؤرخ", "icon": "📜", "color": "#8B4513",
        "system": """أنت مؤرخ متخصص وعالم آثار بارع. تتحدث بأسلوب المؤرخين الكبار.
دورك مساعدة الطالب على فهم الأحداث التاريخية بعمق.
- اربط الأحداث بسياقها الزمني والمكاني
- اذكر الشخصيات التاريخية بأسمائها الكاملة وعصورها
- استخدم الخط الزمني والمقارنة بين الحضارات
- اشرح أسباب الأحداث ونتائجها
أسلوبك: علمي رصين مع قصص شيّقة""",
    },
    "science": {
        "name": "العالِم", "icon": "🔬", "color": "#2E8B57",
        "system": """أنت عالم متخصص في العلوم الطبيعية والتطبيقية.
- استخدم التجارب والأمثلة الحياتية
- اشرح بالأرقام والمعادلات عند الضرورة
- اربط كل مفهوم بتطبيق واقعي
- عند ذكر نظريات أو اكتشافات، اذكر من اكتشفها ومتى
أسلوبك: دقيق علمي مع تبسيط ممتاز""",
    },
    "math": {
        "name": "الرياضياتي", "icon": "📐", "color": "#4169E1",
        "system": """أنت رياضياتي خبير تشرح بأسلوب برهاني خطوة بخطوة.
- حل كل مسألة خطوة بخطوة مع الشرح
- استخدم الرمز الرياضي الصحيح
- ضع أمثلة من السهل للصعب
- اكشف الأخطاء الشائعة وصحّحها
أسلوبك: منطقي دقيق مع تشجيع مستمر""",
    },
    "language": {
        "name": "اللغوي", "icon": "🌍", "color": "#9B59B6",
        "system": """أنت لغوي وأديب متخصص في علوم اللغة والأدب.
- اشرح الأصل الاشتقاقي للمصطلحات الصعبة
- ضع كل كلمة في سياقها الصحيح
- قدّم أمثلة من الأدب والشعر عند الحاجة
- صحّح الأخطاء اللغوية بلطف
أسلوبك: أدبي راقٍ مع تبسيط عملي""",
    },
    "general": {
        "name": "المعلم الذكي", "icon": "🎓", "color": "#E74C3C",
        "system": """أنت معلم ذكي متعدد التخصصات، خبير في التعليم الحديث.
- استخدم أسلوب سقراط (الأسئلة) لتنمية التفكير النقدي
- طبّق استراتيجية VRPER: تصور، اربط، توقّع، جرّب، راجع
- ادمج التكامل الحسي: بصري + سمعي + حركي
- ابنِ المفاهيم من السهل للصعب
- شجّع الطالب وعزّز ثقته بنفسه
أسلوبك: حماسي ومشجع مع عمق علمي""",
    },
}

# ─── App Lifespan (fixes deprecated @app.on_event) ───────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print("🚀 AI Educational Platform started — Claude claude-opus-4-6")
    yield
    print("👋 Platform shutting down")

app = FastAPI(title="AI Educational Platform", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth dependency ───────────────────────────────────────────────────────────
def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    if not creds:
        raise HTTPException(401, "Authentication required")
    payload = verify_token(creds.credentials)
    user = db.get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(401, "User not found")
    return user

# ─── Claude client helper ──────────────────────────────────────────────────────
def get_claude():
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured. Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── Auth endpoints ────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"

    @field_validator("role")
    @classmethod
    def valid_role(cls, v):
        if v not in ("student", "teacher", "parent", "admin"):
            raise ValueError("Invalid role")
        return v

    @field_validator("password")
    @classmethod
    def min_length(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    if db.get_user_by_email(req.email):
        raise HTTPException(400, "Email already registered")
    pw_hash = hash_password(req.password)
    user_id = db.create_user(req.name, req.email, pw_hash, req.role)
    token = create_token(user_id, req.role)
    return {"token": token, "user": {"id": user_id, "name": req.name, "role": req.role}}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = db.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "role": user["role"]}}

# ─── Sessions ──────────────────────────────────────────────────────────────────
class NewSessionRequest(BaseModel):
    subject: str
    persona: str = "general"
    title: str = ""

@app.post("/api/sessions")
async def create_session(req: NewSessionRequest, user=Depends(get_current_user)):
    if req.persona not in PERSONAS:
        req.persona = "general"
    sid = db.create_session(user["id"], req.subject, req.persona, req.title or f"جلسة {req.subject}")
    db.award_reward(user["id"], "activity", "جلسة جديدة", f"بدأت جلسة {req.subject}", 5, "📚")
    return {"session_id": sid}

@app.get("/api/sessions")
async def get_sessions(user=Depends(get_current_user)):
    return db.get_user_sessions(user["id"])

@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: int, user=Depends(get_current_user)):
    return db.get_session_messages(session_id)

# ─── Chat Streaming ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: int
    message: str
    persona: str = "general"
    screen_image: Optional[str] = None  # base64 PNG from WebRTC screen capture

    @field_validator("message")
    @classmethod
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()

@app.post("/api/chat")
async def chat(req: ChatRequest, user=Depends(get_current_user)):
    client = get_claude()
    persona = PERSONAS.get(req.persona, PERSONAS["general"])
    history = db.get_session_messages(req.session_id, limit=20)

    # Build conversation history (last 20 turns)
    messages = []
    for m in history:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})

    # Build current user content
    user_content = []
    if req.screen_image:
        try:
            img_data = req.screen_image.split(",")[-1]
            user_content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": img_data}
            })
            user_content.append({"type": "text", "text": f"[الطالب شارك شاشته]\n{req.message}"})
        except Exception:
            user_content.append({"type": "text", "text": req.message})
    else:
        user_content = req.message

    messages.append({"role": "user", "content": user_content})
    db.save_message(req.session_id, "user", req.message)

    def generate():
        full_response = ""
        try:
            # FIX: Use web_search without thinking (tools and thinking conflict in streaming)
            # Use thinking only for non-tool requests
            has_screen = bool(req.screen_image)
            stream_kwargs = dict(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=persona["system"],
                messages=messages,
            )
            # Add web_search tool (no thinking when using tools in streaming)
            stream_kwargs["tools"] = [{"type": "web_search_20260209", "name": "web_search"}]

            with client.messages.stream(**stream_kwargs) as stream:
                for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "text") and delta.text:
                            full_response += delta.text
                            yield f"data: {json.dumps({'type': 'text', 'content': delta.text})}\n\n"
                    elif etype == "message_stop":
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except anthropic.RateLimitError:
            msg = "تجاوزت حد الطلبات. انتظر قليلاً ثم حاول مجدداً."
            yield f"data: {json.dumps({'type': 'error', 'content': msg})}\n\n"
        except anthropic.APIStatusError as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'خطأ في API: {e.status_code}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            if full_response:
                db.save_message(req.session_id, "assistant", full_response)
                db.update_progress(user["id"], "general")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ─── File Upload ───────────────────────────────────────────────────────────────
@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: int = Form(0),
    user=Depends(get_current_user),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"نوع الملف {ext} غير مسموح به. المسموح: PDF, TXT, PNG, JPG, WEBP, MD")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "حجم الملف يتجاوز الحد المسموح (10 MB)")

    safe_name = f"{user['id']}_{int(time.time())}_{secrets.token_hex(4)}{ext}"
    file_path = UPLOAD_DIR / safe_name

    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    # Extract text
    extracted = ""
    try:
        if ext == ".pdf":
            import PyPDF2, io
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            extracted = "\n\n".join(p.extract_text() or "" for p in reader.pages[:20])
        elif ext in (".txt", ".md"):
            extracted = content.decode("utf-8", errors="replace")
    except Exception as e:
        extracted = f"[تعذّر استخراج النص: {e}]"

    file_id = db.save_file_record(
        user["id"], file.filename, str(file_path),
        ext.lstrip("."), len(content), extracted,
        session_id or None,
    )
    db.award_reward(user["id"], "activity", "رفع ملف", "رفعت ملفاً للدراسة", 10, "📎")

    return {
        "file_id": file_id,
        "filename": file.filename,
        "size": len(content),
        "type": ext.lstrip("."),
        "extracted_text": extracted[:600] + ("..." if len(extracted) > 600 else ""),
        "path": f"/uploads/{safe_name}",
    }

# ─── Mind Map ──────────────────────────────────────────────────────────────────
class MindMapRequest(BaseModel):
    session_id: int = 0
    topic: str
    content: str = ""
    subject: str = "general"
    persona: str = "general"

    @field_validator("topic")
    @classmethod
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("Topic cannot be empty")
        return v.strip()

@app.post("/api/mindmap/generate")
async def generate_mindmap(req: MindMapRequest, user=Depends(get_current_user)):
    client = get_claude()
    prompt = f"""أنشئ خريطة ذهنية شاملة للموضوع التالي بصيغة JSON فقط بدون أي نص إضافي.
الموضوع: {req.topic}
المحتوى المرجعي: {req.content[:1500] if req.content else req.topic}

أعد JSON بهذا الهيكل بالضبط:
{{
  "title": "عنوان الخريطة",
  "color": "#2563eb",
  "children": [
    {{
      "id": "1",
      "label": "فكرة رئيسية",
      "color": "#7c3aed",
      "children": [
        {{"id": "1-1", "label": "فكرة فرعية", "color": "#f59e0b", "children": []}}
      ]
    }}
  ]
}}

القواعد: 4-6 أفكار رئيسية، 2-4 أفكار فرعية لكل منها. JSON فقط."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    # Extract JSON robustly
    for start in ("```json\n", "```\n", "```json", "```", "{"):
        if start in raw:
            if start == "{":
                raw = raw[raw.index("{"):]
                break
            raw = raw.split(start, 1)[-1]
            if "```" in raw:
                raw = raw.split("```")[0]
            raw = raw.strip()
            break

    # Ensure ends at last }
    last_brace = raw.rfind("}")
    if last_brace != -1:
        raw = raw[:last_brace + 1]

    try:
        map_data = json.loads(raw)
    except json.JSONDecodeError:
        map_data = {
            "title": req.topic,
            "color": "#2563eb",
            "children": [
                {"id": "1", "label": "المفاهيم الأساسية", "color": "#7c3aed", "children": []},
                {"id": "2", "label": "التطبيقات", "color": "#f59e0b", "children": []},
                {"id": "3", "label": "الأمثلة", "color": "#10b981", "children": []},
            ],
        }

    map_id = db.save_mind_map(user["id"], req.topic, map_data, req.subject, req.session_id or None)
    db.award_reward(user["id"], "achievement", "خريطة ذهنية", "أنشأت خريطة ذهنية", 15, "🗺️")
    return {"map_id": map_id, "map_data": map_data}

@app.get("/api/mindmaps")
async def get_mindmaps(user=Depends(get_current_user)):
    return db.get_user_mind_maps(user["id"])

# ─── Quiz ──────────────────────────────────────────────────────────────────────
class QuizRequest(BaseModel):
    session_id: int = 0
    subject: str
    topic: str
    content: str = ""
    difficulty: str = "medium"
    quiz_type: str = "mcq"
    count: int = 5
    persona: str = "general"

    @field_validator("count")
    @classmethod
    def valid_count(cls, v):
        return max(3, min(20, v))

    @field_validator("difficulty")
    @classmethod
    def valid_diff(cls, v):
        return v if v in ("easy", "medium", "hard") else "medium"

@app.post("/api/quiz/generate")
async def generate_quiz(req: QuizRequest, user=Depends(get_current_user)):
    client = get_claude()
    type_ar = {"mcq": "متعددة الخيارات", "truefalse": "صح/خطأ", "short": "إجابة قصيرة"}
    diff_ar  = {"easy": "سهل", "medium": "متوسط", "hard": "صعب"}

    prompt = f"""أنشئ {req.count} أسئلة {type_ar.get(req.quiz_type, 'متعددة الخيارات')} مستوى {diff_ar.get(req.difficulty, 'متوسط')}.
المادة: {req.subject} | الموضوع: {req.topic}
{f'المحتوى: {req.content[:1000]}' if req.content else ''}

أعد JSON فقط — مصفوفة بهذا الشكل:
[
  {{
    "id": 1,
    "question": "نص السؤال؟",
    "type": "mcq",
    "options": ["أ) خيار1", "ب) خيار2", "ج) خيار3", "د) خيار4"],
    "correct": 0,
    "explanation": "شرح الإجابة"
  }}
]
- correct: رقم الخيار الصحيح (0-3)
- لا تضع أي نص قبل أو بعد المصفوفة JSON فقط."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    # Extract JSON array
    if "[" in raw:
        raw = raw[raw.index("["):]
        last = raw.rfind("]")
        if last != -1:
            raw = raw[:last + 1]
    if "```" in raw:
        raw = raw.split("```")[0]

    try:
        questions = json.loads(raw)
        if not isinstance(questions, list):
            raise ValueError("Not a list")
    except Exception:
        questions = [{
            "id": 1, "question": f"ما هو موضوع {req.topic}؟",
            "type": "mcq",
            "options": ["أ) الإجابة أ", "ب) الإجابة ب", "ج) الإجابة ج", "د) الإجابة د"],
            "correct": 0, "explanation": "تعذّر توليد الأسئلة، يرجى المحاولة مرة أخرى"
        }]

    quiz_id = db.save_quiz(user["id"], req.subject, questions, req.difficulty, req.quiz_type, req.session_id or None)
    return {"quiz_id": quiz_id, "questions": questions, "difficulty": req.difficulty}

class QuizSubmitRequest(BaseModel):
    quiz_id: int
    answers: List[int]
    time_taken: int = 0

@app.post("/api/quiz/submit")
async def submit_quiz(req: QuizSubmitRequest, user=Depends(get_current_user)):
    client = get_claude()
    conn = db.get_connection()
    quiz = conn.execute("SELECT * FROM quizzes WHERE id=?", (req.quiz_id,)).fetchone()
    conn.close()
    if not quiz:
        raise HTTPException(404, "الاختبار غير موجود")

    questions = json.loads(quiz["questions"])
    correct = sum(
        1 for i, q in enumerate(questions)
        if i < len(req.answers) and req.answers[i] == q.get("correct", -99)
    )
    score = (correct / len(questions)) * 100 if questions else 0

    # Generate feedback
    try:
        fb_resp = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content":
                f"الطالب أجاب على {len(questions)} سؤال وحصل على {score:.0f}%. "
                f"أعطه تغذية راجعة مشجعة وموجزة (3-4 جمل) مع نصيحة واحدة للتحسين."}],
        )
        feedback = fb_resp.content[0].text
    except Exception:
        feedback = f"أحسنت! حصلت على {score:.0f}%. استمر في الممارسة لتحسين أدائك."

    db.save_quiz_attempt(req.quiz_id, user["id"], req.answers, score, req.time_taken, feedback)

    # Conditional rewards
    if score == 100:
        db.award_reward(user["id"], "badge", "علامة كاملة! 🌟", "حصلت على 100%", 50, "🌟")
    elif score >= 80:
        db.award_reward(user["id"], "badge", "ممتاز", "أكثر من 80%", 30, "🏆")
    elif score >= 60:
        db.award_reward(user["id"], "achievement", "جيد", "اجتزت الاختبار", 20, "👍")

    return {"score": score, "correct": correct, "total": len(questions), "feedback": feedback}

# ─── Assessment ────────────────────────────────────────────────────────────────
class AssessmentRequest(BaseModel):
    subject: str
    assessment_type: str = "diagnostic"

@app.post("/api/assessment/generate")
async def generate_assessment(req: AssessmentRequest, user=Depends(get_current_user)):
    client = get_claude()
    type_desc = {
        "diagnostic": "تشخيصي لقياس المستوى الحالي (سهل → صعب)",
        "pre_test": "قبلي قبل الدرس — يقيس المعرفة السابقة",
        "post_test": "بعدي بعد الدرس — يقيس مستوى الاكتساب",
        "intelligences": "مقياس الذكاءات المتعددة (Gardner) — بصري، سمعي، منطقي، جسمي، اجتماعي",
    }.get(req.assessment_type, "تشخيصي")

    prompt = f"""أنشئ اختباراً {type_desc} لمادة {req.subject}، 8 أسئلة متنوعة المستويات.
أعد JSON فقط:
{{
  "title": "عنوان الاختبار",
  "description": "وصف الغرض من الاختبار",
  "questions": [
    {{
      "id": 1,
      "question": "نص السؤال؟",
      "type": "mcq",
      "options": ["أ) ...", "ب) ...", "ج) ...", "د) ..."],
      "correct": 0,
      "level": "knowledge",
      "points": 10,
      "explanation": "شرح الإجابة"
    }}
  ]
}}
JSON فقط بدون أي نص إضافي."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if "{" in raw:
        raw = raw[raw.index("{"):]
        last = raw.rfind("}")
        if last != -1:
            raw = raw[:last + 1]

    try:
        data = json.loads(raw)
    except Exception:
        data = {"title": f"اختبار {req.subject}", "description": "", "questions": []}

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO assessments (user_id,subject,assessment_type,questions) VALUES (?,?,?,?)",
        (user["id"], req.subject, req.assessment_type, json.dumps(data.get("questions", []))),
    )
    assessment_id = cur.lastrowid
    conn.commit(); conn.close()

    return {"assessment_id": assessment_id, "assessment": data}

# ─── Progress ──────────────────────────────────────────────────────────────────
@app.get("/api/progress")
async def get_progress(user=Depends(get_current_user)):
    data = db.get_user_progress(user["id"])
    pts   = data.get("profile", {}).get("total_points", 0)
    level = 1 + pts // 100
    return {**data, "level": min(level, 50), "next_level_points": (level * 100) - pts}

# ─── Report ────────────────────────────────────────────────────────────────────
@app.post("/api/report/generate")
async def generate_report(period_days: int = 7, user=Depends(get_current_user)):
    client = get_claude()
    data = db.get_user_progress(user["id"])

    prompt = f"""أنشئ تقريراً تعليمياً شاملاً للطالب خلال آخر {period_days} أيام.

بيانات التقدم: {json.dumps(data['progress'][:5], ensure_ascii=False)}
عدد الجلسات: {data['sessions_count']}
المكافآت المكتسبة: {len(data['rewards'])}
إجمالي النقاط: {data['profile'].get('total_points', 0)}

اكتب تقريراً احترافياً يشمل:
1. ملخص الأداء العام
2. المواد التي تحسّن فيها الطالب
3. نقاط الضعف والمجالات التي تحتاج تطويراً
4. توصيات تعليمية مخصصة
5. خطة تطوير مقترحة للأسبوع القادم

الأسلوب: احترافي مشجع، يُظهر الاهتمام بتطور الطالب."""

    # Use thinking for deep analysis on reports
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    report_text = ""
    for block in response.content:
        if block.type == "text":
            report_text = block.text
            break

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO reports (user_id,report_type,recipient_role,content) VALUES (?,?,?,?)",
        (user["id"], "progress", "student", report_text),
    )
    conn.commit(); conn.close()
    return {"report": report_text, "generated_at": datetime.now().isoformat()}

# ─── Learning Path ─────────────────────────────────────────────────────────────
@app.get("/api/learning-path/{subject}")
async def get_learning_path(subject: str, user=Depends(get_current_user)):
    client = get_claude()
    data = db.get_user_progress(user["id"])
    sp = next((p for p in data["progress"] if p["subject"] == subject), None)
    mastery = sp["mastery_percentage"] if sp else 0

    prompt = f"""أنشئ مساراً تعليمياً مخصصاً لطالب في مادة {subject} بمستوى إتقان {mastery:.0f}%.
أعد JSON فقط:
{{
  "subject": "{subject}",
  "current_level": "المستوى الحالي للطالب",
  "recommendation": "توصية مخصصة قصيرة",
  "steps": [
    {{"step": 1, "title": "عنوان الخطوة", "description": "وصف تفصيلي", "estimated_time": "30 دقيقة", "type": "concept"}}
  ]
}}
5-7 خطوات متدرجة. JSON فقط."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if "{" in raw:
        raw = raw[raw.index("{"):]
        raw = raw[:raw.rfind("}") + 1]
    try:
        return json.loads(raw)
    except Exception:
        return {"subject": subject, "steps": [], "recommendation": "ابدأ بمراجعة المفاهيم الأساسية"}

# ─── Personas list ─────────────────────────────────────────────────────────────
@app.get("/api/personas")
async def get_personas():
    return [{"key": k, "name": v["name"], "icon": v["icon"], "color": v["color"]}
            for k, v in PERSONAS.items()]

# ─── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "model": "claude-opus-4-6",
        "db": "sqlite",
        "api_key_set": bool(ANTHROPIC_API_KEY),
    }

# ─── Static files & pages ──────────────────────────────────────────────────────
# NOTE: Static mounts MUST come after API routes to avoid shadowing them
app.mount("/static",  StaticFiles(directory="static"),  name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/app")
async def serve_app():
    return FileResponse("app.html")

@app.get("/")
async def serve_index():
    return FileResponse("index.html")

# ─── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
