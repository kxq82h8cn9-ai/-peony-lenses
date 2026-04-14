"""
AI Educational Platform — FastAPI Backend
Uses Claude claude-opus-4-6 with adaptive thinking, web search, file analysis
"""
import os, json, base64, hashlib, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import anthropic
from passlib.context import CryptContext
from jose import JWTError, jwt
import aiofiles

import database as db

# ─── Config ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "ai-education-secret-2024")
ALGORITHM  = "HS256"
TOKEN_EXP  = 24  # hours
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# ─── Personas ─────────────────────────────────────────────────────────────────
PERSONAS = {
    "history": {
        "name": "المؤرخ",
        "icon": "📜",
        "color": "#8B4513",
        "system": """أنت مؤرخ متخصص وعالم آثار بارع. تتحدث بأسلوب المؤرخين الكبار.
دورك هو مساعدة الطالب على فهم الأحداث التاريخية بعمق.
- اربط الأحداث بسياقها الزمني والمكاني
- اذكر الشخصيات التاريخية بأسمائها الكاملة وعصورها
- استخدم الخط الزمني والمقارنة بين الحضارات
- اشرح أسباب الأحداث ونتائجها
- ابحث في الويب عن معلومات تاريخية محدّثة عند الحاجة
أسلوبك: علمي ورصين مع قصص شيّقة توضح الحدث""",
    },
    "science": {
        "name": "العالِم",
        "icon": "🔬",
        "color": "#2E8B57",
        "system": """أنت عالم متخصص في العلوم الطبيعية والتطبيقية.
دورك هو شرح المفاهيم العلمية بأسلوب تجريبي واضح.
- استخدم التجارب والأمثلة الحياتية
- اشرح بالأرقام والمعادلات عند الضرورة
- اربط كل مفهوم بتطبيق واقعي
- عند ذكر نظريات أو اكتشافات، اذكر من اكتشفها ومتى
- ابحث في الويب عن أحدث الأبحاث والاكتشافات العلمية
أسلوبك: دقيق علمي مع تبسيط ممتاز للمبتدئين""",
    },
    "math": {
        "name": "الرياضياتي",
        "icon": "📐",
        "color": "#4169E1",
        "system": """أنت رياضياتي خبير تشرح بأسلوب برهاني خطوة بخطوة.
دورك هو بناء الفهم الرياضي العميق لدى الطالب.
- حل كل مسألة خطوة بخطوة مع الشرح
- استخدم الرمز الرياضي الصحيح
- ضع أمثلة من السهل للصعب
- اكشف الأخطاء الشائعة وصحّحها
- اربط المفاهيم ببعضها لبناء صورة متكاملة
أسلوبك: منطقي دقيق مع تشجيع مستمر للطالب""",
    },
    "language": {
        "name": "اللغوي",
        "icon": "🌍",
        "color": "#9B59B6",
        "system": """أنت لغوي وأديب متخصص في علوم اللغة والأدب.
دورك هو تطوير مهارات القراءة والكتابة والفهم اللغوي.
- اشرح الأصل الاشتقاقي للمصطلحات الصعبة
- ضع كل كلمة في سياقها الصحيح
- قدّم أمثلة من الأدب والشعر عند الحاجة
- صحّح الأخطاء اللغوية بلطف
- ابحث في الويب عن استخدامات المصطلحات في مصادر موثوقة
أسلوبك: أدبي راقٍ مع تبسيط عملي للقواعد""",
    },
    "general": {
        "name": "المعلم الذكي",
        "icon": "🎓",
        "color": "#E74C3C",
        "system": """أنت معلم ذكي متعدد التخصصات، خبير في التعليم الحديث.
دورك هو مساعدة الطالب بأي مادة أو سؤال.
- استخدم أسلوب سقراط (الأسئلة) لتنمية التفكير النقدي
- طبّق استراتيجية VRPER: تصور، اربط، توقّع، جرّب، راجع
- ادمج التكامل الحسي: بصري + سمعي + حركي
- ابنِ المفاهيم من السهل للصعب
- شجّع الطالب وعزّز ثقته بنفسه
- ابحث في الويب عند الحاجة لمعلومات محدّثة
أسلوبك: حماسي ومشجع مع عمق علمي""",
    },
}

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="AI Educational Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    db.init_db()
    print("🚀 AI Educational Platform started")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ─── Auth ─────────────────────────────────────────────────────────────────────
def create_token(user_id: int, role: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_EXP)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, SECRET_KEY, ALGORITHM)

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    if not creds:
        raise HTTPException(401, "Authentication required")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        user = db.get_user_by_id(user_id)
        if not user:
            raise HTTPException(401, "User not found")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid token")

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    if db.get_user_by_email(req.email):
        raise HTTPException(400, "Email already registered")
    pw_hash = pwd_ctx.hash(req.password)
    user_id = db.create_user(req.name, req.email, pw_hash, req.role)
    token = create_token(user_id, req.role)
    return {"token": token, "user": {"id": user_id, "name": req.name, "role": req.role}}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = db.get_user_by_email(req.email)
    if not user or not pwd_ctx.verify(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "role": user["role"]}}

# ─── Sessions ─────────────────────────────────────────────────────────────────
class NewSessionRequest(BaseModel):
    subject: str
    persona: str = "general"
    title: str = ""

@app.post("/api/sessions")
async def create_session(req: NewSessionRequest, user=Depends(get_current_user)):
    session_id = db.create_session(user["id"], req.subject, req.persona, req.title)
    db.award_reward(user["id"], "activity", "جلسة جديدة", f"بدأت جلسة {req.subject}", 5, "📚")
    return {"session_id": session_id}

@app.get("/api/sessions")
async def get_sessions(user=Depends(get_current_user)):
    return db.get_user_sessions(user["id"])

@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: int, user=Depends(get_current_user)):
    return db.get_session_messages(session_id)

# ─── Chat (Streaming) ─────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: int
    message: str
    persona: str = "general"
    file_id: Optional[int] = None
    screen_image: Optional[str] = None  # base64 PNG from screen share

@app.post("/api/chat")
async def chat(req: ChatRequest, user=Depends(get_current_user)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    persona = PERSONAS.get(req.persona, PERSONAS["general"])
    history = db.get_session_messages(req.session_id, limit=30)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build messages
    messages = []
    for m in history:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})

    # Build current user message content
    user_content = []

    # Add screen image if provided
    if req.screen_image:
        try:
            img_data = req.screen_image.split(",")[-1]
            user_content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": img_data}
            })
            user_content.append({"type": "text", "text": f"[الطالب شارك شاشته] {req.message}"})
        except Exception:
            user_content.append({"type": "text", "text": req.message})
    else:
        user_content.append({"type": "text", "text": req.message})

    messages.append({"role": "user", "content": user_content})

    # Save user message
    db.save_message(req.session_id, "user", req.message)

    def generate():
        full_response = ""
        try:
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=persona["system"],
                tools=[{"type": "web_search_20260209", "name": "web_search"}],
                messages=messages,
            ) as stream:
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta":
                            delta = event.delta
                            if hasattr(delta, "text"):
                                chunk = delta.text
                                full_response += chunk
                                yield f"data: {json.dumps({'type':'text','content':chunk})}\n\n"
                        elif event.type == "message_stop":
                            yield f"data: {json.dumps({'type':'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','content':str(e)})}\n\n"
        finally:
            if full_response:
                db.save_message(req.session_id, "assistant", full_response)
                db.update_progress(user["id"], "general")

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ─── File Upload ──────────────────────────────────────────────────────────────
@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: int = Form(0),
    user=Depends(get_current_user)
):
    ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".md"}
    if ext not in allowed:
        raise HTTPException(400, f"File type {ext} not allowed")

    safe_name = f"{user['id']}_{int(time.time())}{ext}"
    file_path = UPLOAD_DIR / safe_name
    content = await file.read()

    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    # Extract text
    extracted = ""
    try:
        if ext == ".pdf":
            import PyPDF2, io
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            extracted = "\n".join(p.extract_text() or "" for p in reader.pages)
        elif ext == ".txt":
            extracted = content.decode("utf-8", errors="ignore")
    except Exception as e:
        extracted = f"[خطأ في استخراج النص: {e}]"

    file_id = db.save_file_record(
        user["id"], file.filename, str(file_path),
        ext.lstrip("."), len(content), extracted,
        session_id if session_id else None
    )
    db.award_reward(user["id"], "activity", "رفع ملف", "رفعت ملفاً للدراسة", 10, "📎")

    return {
        "file_id": file_id,
        "filename": file.filename,
        "size": len(content),
        "type": ext.lstrip("."),
        "extracted_text": extracted[:500] + ("..." if len(extracted) > 500 else ""),
        "path": f"/uploads/{safe_name}"
    }

# ─── Mind Map ─────────────────────────────────────────────────────────────────
class MindMapRequest(BaseModel):
    session_id: int
    topic: str
    content: str
    subject: str = "general"
    persona: str = "general"

@app.post("/api/mindmap/generate")
async def generate_mindmap(req: MindMapRequest, user=Depends(get_current_user)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""أنشئ خريطة ذهنية شاملة للموضوع التالي بصيغة JSON.
الموضوع: {req.topic}
المحتوى: {req.content[:2000]}

أعد JSON فقط بهذا الشكل:
{{
  "title": "عنوان الخريطة",
  "color": "#2563eb",
  "children": [
    {{
      "id": "1",
      "label": "فكرة رئيسية 1",
      "color": "#7c3aed",
      "children": [
        {{"id": "1.1", "label": "فكرة فرعية", "color": "#f59e0b", "children": []}}
      ]
    }}
  ]
}}
أنشئ 4-6 أفكار رئيسية مع 2-4 أفكار فرعية لكل منها. أجب بـ JSON فقط."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Extract JSON from response
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        map_data = json.loads(raw)
    except Exception:
        map_data = {"title": req.topic, "color": "#2563eb", "children": [
            {"id": "1", "label": "المفاهيم الأساسية", "color": "#7c3aed", "children": []},
            {"id": "2", "label": "التطبيقات", "color": "#f59e0b", "children": []},
        ]}

    map_id = db.save_mind_map(user["id"], req.topic, map_data, req.subject,
                               req.session_id if req.session_id else None)
    db.award_reward(user["id"], "achievement", "خريطة ذهنية", "أنشأت خريطة ذهنية", 15, "🗺️")
    return {"map_id": map_id, "map_data": map_data}

@app.get("/api/mindmaps")
async def get_mindmaps(user=Depends(get_current_user)):
    return db.get_user_mind_maps(user["id"])

# ─── Quiz ─────────────────────────────────────────────────────────────────────
class QuizRequest(BaseModel):
    session_id: int
    subject: str
    topic: str
    content: str
    difficulty: str = "medium"
    quiz_type: str = "mcq"
    count: int = 5
    persona: str = "general"

@app.post("/api/quiz/generate")
async def generate_quiz(req: QuizRequest, user=Depends(get_current_user)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    type_map = {"mcq": "متعددة الخيارات", "truefalse": "صح/خطأ", "short": "إجابة قصيرة"}
    diff_map = {"easy": "سهل", "medium": "متوسط", "hard": "صعب"}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""أنشئ {req.count} أسئلة {type_map.get(req.quiz_type,'متعددة الخيارات')} مستوى {diff_map.get(req.difficulty,'متوسط')} عن:
الموضوع: {req.topic}
المادة: {req.subject}
المحتوى: {req.content[:1500]}

أعد JSON فقط بهذا الشكل:
[
  {{
    "id": 1,
    "question": "نص السؤال؟",
    "type": "mcq",
    "options": ["أ) خيار1", "ب) خيار2", "ج) خيار3", "د) خيار4"],
    "correct": 0,
    "explanation": "شرح الإجابة الصحيحة"
  }}
]
أجب بـ JSON فقط."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        questions = json.loads(raw)
    except Exception:
        questions = [{"id": 1, "question": "خطأ في توليد السؤال", "options": [], "correct": 0, "explanation": ""}]

    quiz_id = db.save_quiz(user["id"], req.subject, questions, req.difficulty,
                            req.quiz_type, req.session_id if req.session_id else None)
    return {"quiz_id": quiz_id, "questions": questions, "difficulty": req.difficulty}

class QuizSubmitRequest(BaseModel):
    quiz_id: int
    answers: List[int]
    time_taken: int = 0

@app.post("/api/quiz/submit")
async def submit_quiz(req: QuizSubmitRequest, user=Depends(get_current_user)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    import sqlite3
    conn = db.get_connection()
    quiz = conn.execute("SELECT * FROM quizzes WHERE id=?", (req.quiz_id,)).fetchone()
    conn.close()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    questions = json.loads(quiz["questions"])
    correct = sum(1 for i, q in enumerate(questions)
                  if i < len(req.answers) and req.answers[i] == q.get("correct", -1))
    score = (correct / len(questions)) * 100 if questions else 0

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    feedback_prompt = f"""الطالب أجاب على {len(questions)} سؤالاً وحصل على {score:.0f}%.
الأسئلة: {json.dumps(questions[:3], ensure_ascii=False)}
الإجابات: {req.answers[:3]}
أعطه تغذية راجعة مشجعة وموجزة (3-4 جمل) مع نصيحة للتحسين."""

    feedback_resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": feedback_prompt}]
    )
    feedback = feedback_resp.content[0].text

    db.save_quiz_attempt(req.quiz_id, user["id"], req.answers, score, req.time_taken, feedback)

    # Award based on score
    if score == 100:
        db.award_reward(user["id"], "badge", "علامة كاملة! 🌟", "حصلت على 100%", 50, "🌟")
    elif score >= 80:
        db.award_reward(user["id"], "badge", "ممتاز!", "حصلت على أكثر من 80%", 30, "🏆")
    elif score >= 60:
        db.award_reward(user["id"], "achievement", "جيد", "اجتزت الاختبار", 20, "👍")

    return {"score": score, "correct": correct, "total": len(questions), "feedback": feedback}

# ─── Assessment ───────────────────────────────────────────────────────────────
class AssessmentRequest(BaseModel):
    subject: str
    assessment_type: str = "diagnostic"

@app.post("/api/assessment/generate")
async def generate_assessment(req: AssessmentRequest, user=Depends(get_current_user)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    type_descriptions = {
        "diagnostic": "تشخيصي لقياس المستوى الحالي",
        "pre_test": "قبلي قبل الدرس",
        "post_test": "بعدي بعد الدرس",
        "intelligences": "مقياس الذكاءات المتعددة (Gardner)"
    }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""أنشئ اختباراً {type_descriptions.get(req.assessment_type, 'تشخيصياً')} لمادة {req.subject}.
يجب أن يكون 8 أسئلة متنوعة المستويات (معرفة، فهم، تطبيق، تحليل).
أعد JSON فقط:
{{
  "title": "عنوان الاختبار",
  "description": "وصف الاختبار",
  "questions": [
    {{
      "id": 1,
      "question": "نص السؤال؟",
      "type": "mcq",
      "options": ["أ) ...", "ب) ...", "ج) ...", "د) ..."],
      "correct": 0,
      "level": "knowledge",
      "points": 10
    }}
  ]
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        assessment_data = json.loads(raw)
    except Exception:
        assessment_data = {"title": f"اختبار {req.subject}", "questions": []}

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO assessments (user_id,subject,assessment_type,questions) VALUES (?,?,?,?)",
        (user["id"], req.subject, req.assessment_type, json.dumps(assessment_data.get("questions", [])))
    )
    assessment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {"assessment_id": assessment_id, "assessment": assessment_data}

# ─── Progress & Reports ───────────────────────────────────────────────────────
@app.get("/api/progress")
async def get_progress(user=Depends(get_current_user)):
    data = db.get_user_progress(user["id"])
    profile = data.get("profile", {})
    level = 1 + (profile.get("total_points", 0) // 100)
    return {**data, "level": min(level, 50),
            "next_level_points": (level * 100) - profile.get("total_points", 0)}

@app.post("/api/report/generate")
async def generate_report(
    period_days: int = 7,
    user=Depends(get_current_user)
):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    data = db.get_user_progress(user["id"])
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    summary_prompt = f"""أنشئ تقريراً تعليمياً شاملاً للطالب خلال آخر {period_days} أيام.
بيانات التقدم: {json.dumps(data['progress'], ensure_ascii=False)}
عدد الجلسات: {data['sessions_count']}
المكافآت: {len(data['rewards'])} مكافأة
النقاط الكلية: {data['profile'].get('total_points', 0)}

التقرير يجب أن يشمل:
1. ملخص الأداء العام
2. المواد التي تحسّن فيها
3. المواد التي تحتاج تحسيناً
4. توصيات مخصصة
5. نقاط القوة
6. خطة التطوير المقترحة

اكتب التقرير بأسلوب احترافي ومشجع."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": summary_prompt}]
    )

    report_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            report_text = block.text
            break

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reports (user_id,report_type,recipient_role,content) VALUES (?,?,?,?)",
        (user["id"], "progress", "student", report_text)
    )
    conn.commit()
    conn.close()

    return {"report": report_text, "generated_at": datetime.now().isoformat()}

@app.get("/api/learning-path/{subject}")
async def get_learning_path(subject: str, user=Depends(get_current_user)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    data = db.get_user_progress(user["id"])
    subject_progress = next((p for p in data["progress"] if p["subject"] == subject), None)
    mastery = subject_progress["mastery_percentage"] if subject_progress else 0

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""أنشئ مساراً تعليمياً مخصصاً لطالب في مادة {subject}.
مستوى الإتقان الحالي: {mastery:.0f}%
أعد JSON:
{{
  "subject": "{subject}",
  "current_level": "المستوى الحالي",
  "steps": [
    {{"step": 1, "title": "عنوان الخطوة", "description": "وصف", "estimated_time": "30 دقيقة", "completed": false}}
  ],
  "recommendation": "توصية مخصصة"
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        path_data = json.loads(raw)
    except Exception:
        path_data = {"subject": subject, "steps": [], "recommendation": ""}

    return path_data

# ─── Personas & Subjects ──────────────────────────────────────────────────────
@app.get("/api/personas")
async def get_personas():
    return [{"key": k, "name": v["name"], "icon": v["icon"], "color": v["color"]}
            for k, v in PERSONAS.items()]

# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat(),
            "ai": "claude-opus-4-6", "db": "sqlite"}

# ─── Serve Pages ──────────────────────────────────────────────────────────────
@app.get("/app")
async def serve_app():
    return FileResponse("app.html")

@app.get("/")
async def serve_index():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
