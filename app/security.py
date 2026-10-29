from passlib.context import CryptContext

# passlib 1.7.4 与 bcrypt>=4.1 不兼容，requirements.txt 已把 bcrypt 钉在 4.0.1
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
