from app.db import engine, Base
from app import models  # noqa: F401  (нужно для регистрации моделей)

def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("DB: tables created/checked")

if __name__ == "__main__":
    main()