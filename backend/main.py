import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hospitality.db")
SECRET_KEY = os.getenv("JWT_SECRET", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

staff_skills = Table("staff_skills", Base.metadata,
    Column("staff_id", ForeignKey("staff.id"), primary_key=True),
    Column("skill_id", ForeignKey("skills.id"), primary_key=True),
)

class Role(str, Enum):
    guest = "guest"
    staff = "staff"
    manager = "manager"

class RequestStatus(str, Enum):
    submitted = "Submitted"
    assigned = "Assigned"
    accepted = "Accepted"
    in_progress = "In Progress"
    completed = "Completed"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    room_number = Column(String, nullable=True)

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

class Skill(Base):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    department = relationship("Department")

class Staff(Base):
    __tablename__ = "staff"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    available = Column(Boolean, default=True)
    current_task_count = Column(Integer, default=0)
    user = relationship("User")
    department = relationship("Department")
    skills = relationship("Skill", secondary=staff_skills)

class ServiceRequest(Base):
    __tablename__ = "service_requests"
    id = Column(Integer, primary_key=True)
    guest_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)
    category = Column(String, nullable=False)
    description = Column(String, nullable=False)
    room_number = Column(String, nullable=False)
    status = Column(String, default=RequestStatus.submitted.value)
    assigned_staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    department = relationship("Department")
    skill = relationship("Skill")
    assigned_staff = relationship("Staff")
    guest = relationship("User")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=True)
    message = Column(String, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("service_requests.id"), unique=True, nullable=False)
    guest_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class RequestCreate(BaseModel):
    category: str = Field(min_length=2)
    description: str = Field(min_length=2)
    room_number: Optional[str] = None

class StatusUpdate(BaseModel):
    status: RequestStatus

class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None

app = FastAPI(title="Havenly Hospitality API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("FRONTEND_URL", "http://localhost:5173").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

CATEGORY_RULES = {
    "ac": ("Maintenance", "HVAC"), "fan": ("Maintenance", "HVAC"), "air conditioning": ("Maintenance", "HVAC"),
    "electrical": ("Electrical", "Electrical"), "power": ("Electrical", "Electrical"), "switch": ("Electrical", "Electrical"),
    "water bottle": ("Hotel Service", "Guest amenities"), "bottled water": ("Hotel Service", "Guest amenities"),
    "water": ("Plumbing", "Plumbing"), "plumbing": ("Plumbing", "Plumbing"),
    "cleaning": ("Housekeeping", "Cleaning"), "room cleaning": ("Housekeeping", "Cleaning"),
    "food": ("Room Service", "Food service"), "drink": ("Room Service", "Food service"), "dinner": ("Room Service", "Food service"),
    "wi-fi": ("IT Support", "IT support"), "wifi": ("IT Support", "IT support"), "tv": ("IT Support", "IT support"),
    "towel": ("Hotel Service", "Guest amenities"), "amenities": ("Hotel Service", "Guest amenities"),
}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_token(user: User):
    expires = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)

def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc
    user = db.get(User, int(user_id))
    if not user:
        raise credentials_error
    return user

def require_roles(*roles):
    def dependency(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have access to this resource")
        return user
    return dependency

def public_user(user: User):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "room_number": user.room_number}

def serialize_request(item: ServiceRequest):
    return {"id": item.id, "category": item.category, "description": item.description, "department": item.department.name, "skill": item.skill.name, "room_number": item.room_number, "status": item.status, "assigned_staff": item.assigned_staff.user.name if item.assigned_staff else None, "created_at": item.created_at.isoformat() if item.created_at else None}

def seed_database():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(User).first():
            electrical = db.query(Department).filter(Department.name == "Electrical").first()
            if not electrical:
                electrical = Department(name="Electrical")
                db.add(electrical)
                db.flush()
            electrical_skill = db.query(Skill).filter(Skill.name == "Electrical").first()
            if not electrical_skill:
                electrical_skill = Skill(name="Electrical", department_id=electrical.id)
                db.add(electrical_skill)
                db.flush()
            electrical_user = db.query(User).filter(User.email == "neha@havenly.demo").first()
            if not electrical_user:
                electrical_user = User(email="neha@havenly.demo", name="Neha Iyer", password_hash=pwd_context.hash("demo123"), role=Role.staff.value)
                db.add(electrical_user)
                db.flush()
            electrical_staff = db.query(Staff).filter(Staff.user_id == electrical_user.id).first()
            if not electrical_staff:
                db.add(Staff(user_id=electrical_user.id, department_id=electrical.id, skills=[electrical_skill], available=True, current_task_count=0))
            db.commit()
            return
        departments = {name: Department(name=name) for name in ["Maintenance", "Electrical", "Housekeeping", "Room Service", "Plumbing", "IT Support", "Hotel Service"]}
        db.add_all(departments.values())
        db.flush()
        skill_names = {"HVAC": "Maintenance", "Electrical": "Electrical", "Cleaning": "Housekeeping", "Food service": "Room Service", "Plumbing": "Plumbing", "IT support": "IT Support", "Guest amenities": "Hotel Service"}
        skills = {name: Skill(name=name, department=departments[department]) for name, department in skill_names.items()}
        db.add_all(skills.values())
        manager = User(email="manager@havenly.demo", name="Aditya Kapoor", password_hash=pwd_context.hash("demo123"), role=Role.manager.value)
        guest = User(email="guest@havenly.demo", name="Ananya Mehta", password_hash=pwd_context.hash("demo123"), role=Role.guest.value, room_number="204")
        staff_users = [User(email="ravi@havenly.demo", name="Ravi Kumar", password_hash=pwd_context.hash("demo123"), role=Role.staff.value), User(email="priya@havenly.demo", name="Priya Nair", password_hash=pwd_context.hash("demo123"), role=Role.staff.value), User(email="arun@havenly.demo", name="Arun Das", password_hash=pwd_context.hash("demo123"), role=Role.staff.value), User(email="suresh@havenly.demo", name="Suresh Rao", password_hash=pwd_context.hash("demo123"), role=Role.staff.value), User(email="neha@havenly.demo", name="Neha Iyer", password_hash=pwd_context.hash("demo123"), role=Role.staff.value)]
        db.add_all([manager, guest, *staff_users])
        db.flush()
        for user, department, skill in zip(staff_users, ["Maintenance", "Housekeeping", "Room Service", "Plumbing", "Electrical"], ["HVAC", "Cleaning", "Food service", "Plumbing", "Electrical"]):
            db.add(Staff(user_id=user.id, department_id=departments[department].id, skills=[skills[skill]], current_task_count=1 if user.name == "Ravi Kumar" else 0, available=True))
        db.commit()
    finally:
        db.close()

@app.on_event("startup")
def startup():
    seed_database()

@app.get("/health")
def health():
    return {"status": "ok", "service": "havenly-api"}

@app.post("/auth/login", response_model=LoginResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": create_token(user), "user": public_user(user)}

@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return public_user(user)

@app.get("/requests")
def list_requests(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(ServiceRequest)
    if user.role == Role.guest.value:
        query = query.filter(ServiceRequest.guest_id == user.id)
    elif user.role == Role.staff.value:
        staff = db.query(Staff).filter(Staff.user_id == user.id).first()
        query = query.filter(ServiceRequest.assigned_staff_id == staff.id if staff else False)
    return [serialize_request(item) for item in query.order_by(ServiceRequest.created_at.desc()).all()]

@app.post("/requests", status_code=201)
def create_request(payload: RequestCreate, user: User = Depends(require_roles(Role.guest.value)), db: Session = Depends(get_db)):
    combined = f"{payload.category} {payload.description}".lower()
    match = next(((department, skill) for key, (department, skill) in CATEGORY_RULES.items() if key in combined), ("Hotel Service", "Guest amenities"))
    department = db.query(Department).filter(Department.name == match[0]).first()
    skill = db.query(Skill).filter(Skill.name == match[1]).first()
    candidate = db.query(Staff).filter(Staff.department_id == department.id, Staff.available.is_(True), Staff.skills.any(Skill.id == skill.id)).order_by(Staff.current_task_count.asc()).first()
    item = ServiceRequest(guest_id=user.id, department_id=department.id, skill_id=skill.id, category=payload.category, description=payload.description, room_number=payload.room_number or user.room_number or "Unassigned", status=RequestStatus.assigned.value if candidate else RequestStatus.submitted.value, assigned_staff_id=candidate.id if candidate else None)
    db.add(item)
    db.flush()
    if candidate:
        candidate.current_task_count += 1
        db.add(Notification(user_id=user.id, request_id=item.id, message=f"Your request was assigned to {candidate.user.name}."))
        db.add(Notification(user_id=candidate.user_id, request_id=item.id, message=f"New Service Request | Room: {item.room_number} | Problem: {item.description} | Department: {department.name} | Status: New"))
    else:
        db.add(Notification(user_id=user.id, request_id=item.id, message="Your request is queued. The manager has been notified."))
        for manager in db.query(User).filter(User.role == Role.manager.value).all():
            db.add(Notification(user_id=manager.id, request_id=item.id, message=f"Request #{item.id} is waiting for an available {department.name} team member."))
    db.commit()
    db.refresh(item)
    return serialize_request(item)

@app.patch("/requests/{request_id}/status")
def update_status(request_id: int, payload: StatusUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(ServiceRequest, request_id)
    if not item:
        raise HTTPException(404, "Request not found")
    if user.role == Role.guest.value:
        raise HTTPException(403, "Guests cannot change request status")
    staff = db.query(Staff).filter(Staff.user_id == user.id).first()
    if user.role == Role.staff.value and (not staff or item.assigned_staff_id != staff.id):
        raise HTTPException(403, "This request is not assigned to you")
    allowed_transitions = {
        RequestStatus.assigned.value: {RequestStatus.accepted.value, RequestStatus.in_progress.value},
        RequestStatus.accepted.value: {RequestStatus.in_progress.value},
        RequestStatus.in_progress.value: {RequestStatus.completed.value},
    }
    if user.role == Role.staff.value and payload.status.value not in allowed_transitions.get(item.status, set()):
        raise HTTPException(400, f"Cannot move request from {item.status} to {payload.status.value}")
    item.status = payload.status.value
    if payload.status == RequestStatus.completed:
        item.completed_at = datetime.utcnow()
        if item.assigned_staff:
            item.assigned_staff.current_task_count = max(0, item.assigned_staff.current_task_count - 1)
        db.add(Notification(user_id=item.guest_id, request_id=item.id, message=f"Request #{item.id} is complete. How did we do?"))
    else:
        db.add(Notification(user_id=item.guest_id, request_id=item.id, message=f"Request #{item.id} is now {item.status}."))
    db.commit()
    db.refresh(item)
    return serialize_request(item)

@app.post("/requests/{request_id}/feedback")
def add_feedback(request_id: int, payload: FeedbackCreate, user: User = Depends(require_roles(Role.guest.value)), db: Session = Depends(get_db)):
    item = db.get(ServiceRequest, request_id)
    if not item or item.guest_id != user.id or item.status != RequestStatus.completed.value:
        raise HTTPException(400, "Feedback is only available for your completed requests")
    feedback = Feedback(request_id=request_id, guest_id=user.id, rating=payload.rating, comment=payload.comment)
    db.add(feedback)
    db.commit()
    return {"message": "Thank you for your feedback", "rating": payload.rating}

@app.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": item.id, "request_id": item.request_id, "message": item.message, "read": item.read, "created_at": item.created_at.isoformat()} for item in db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).all()]

@app.patch("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if not item:
        raise HTTPException(404, "Notification not found")
    item.read = True
    db.commit()
    return {"id": item.id, "read": item.read}

@app.get("/staff")
def list_staff(user: User = Depends(require_roles(Role.manager.value)), db: Session = Depends(get_db)):
    return [{"id": item.id, "name": item.user.name, "initials": "".join(part[0] for part in item.user.name.split()), "department": item.department.name, "skill": ", ".join(skill.name for skill in item.skills), "tasks": item.current_task_count, "available": item.available, "status": "Available" if item.available and item.current_task_count == 0 else "On task"} for item in db.query(Staff).all()]

@app.get("/dashboard")
def dashboard(user: User = Depends(require_roles(Role.manager.value)), db: Session = Depends(get_db)):
    requests = db.query(ServiceRequest).all()
    staff = db.query(Staff).all()
    return {"total_requests": len(requests), "pending": sum(item.status in [RequestStatus.submitted.value, RequestStatus.assigned.value, RequestStatus.accepted.value] for item in requests), "in_progress": sum(item.status == RequestStatus.in_progress.value for item in requests), "completed": sum(item.status == RequestStatus.completed.value for item in requests), "unassigned": sum(item.assigned_staff_id is None for item in requests), "available_staff": sum(item.available and item.current_task_count == 0 for item in staff), "busy_staff": sum(item.current_task_count > 0 for item in staff), "staff_workload": [{"name": item.user.name, "department": item.department.name, "tasks": item.current_task_count, "available": item.available} for item in staff]}
