# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.orm import Session
# from passlib.context import CryptContext
# from app.database import get_db
# from app.models import models
# from app.schemas import user as schemas
# from fastapi.security import OAuth2PasswordRequestForm

# router = APIRouter(prefix="/user", tags=["User"])

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# def get_password_hash(password: str) -> str:
#     return pwd_context.hash(password)

# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     return pwd_context.verify(plain_password, hashed_password)

# @router.post("/register", response_model=schemas.UserOut)
# def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
#     existing_user = db.query(models.User).filter(models.User.username == user.username).first()
#     if existing_user:
#         raise HTTPException(status_code=400, detail="이미 존재하는 사용자입니다.")

#     new_user = models.User(
#         username=user.username,
#         password=get_password_hash(user.password),
#         name=user.name,
#         email=user.email
#     )
#     db.add(new_user)
#     db.commit()
#     db.refresh(new_user)
#     return new_user

# @router.post("/login")
# def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
#     user = db.query(models.User).filter(models.User.username == form_data.username).first()
#     if not user or not verify_password(form_data.password, user.password):
#         raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
#     return {"message": "로그인 성공", "user_id": user.user_id, "username": user.username}